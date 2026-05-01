"""Fetch NSE index constituent weights via the public live-equity-market API.

Pulls the JSON the NSE website itself uses for live index display. Each
constituent row carries `ffmc` (free float market cap in INR) — converting
to a per-stock free-float weight is `ffmc / sum(ffmc across constituents)`.

Saves snapshot to:
  pipeline/data/trendlyne/raw_exports/nifty500_weights/
    nifty500_weights_<YYYY-MM-DD>.csv

Schema:
  snapshot_date,index_name,nse_symbol,ffmc_inr,weight_pct,
  last_price,p_change_1d,p_change_30d,p_change_365d,
  year_high,year_low,total_traded_value_inr

Run via:
  python -m pipeline.scripts.fetch_nse_index_weights
  python -m pipeline.scripts.fetch_nse_index_weights --indices "NIFTY 500" "NIFTY 100" "NIFTY 50"

This is canonical TD-D1 source (Theme Detector spec §3.2 C2 cap_drift):
6-month delta in summed free-float weight per theme. Forward-only: history
accumulates from first run. Predecessor source: Trendlyne `nifty500_weights/`
folder (always-empty as of 2026-05-01).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "pipeline" / "data" / "trendlyne" / "raw_exports" / "nifty500_weights"

DEFAULT_INDICES = [
    "NIFTY 500",
    "NIFTY 100",
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY MIDCAP 100",
    "NIFTY SMALLCAP 100",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _build_opener() -> urllib.request.OpenerDirector:
    """Browser-flavoured opener: NSE rejects bare urllib without a cookie + UA."""
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "en-IN,en;q=0.9"),
        ("Accept-Encoding", "identity"),
        ("Connection", "keep-alive"),
    ]
    return opener


def _warm_cookies(opener: urllib.request.OpenerDirector) -> None:
    """Hit the NSE homepage first so the session cookie is set before the API call."""
    for url in (
        "https://www.nseindia.com/",
        "https://www.nseindia.com/market-data/live-equity-market",
    ):
        try:
            with opener.open(url, timeout=15) as r:
                r.read(1024)
        except Exception:
            pass
        time.sleep(0.5)


def fetch_index(opener: urllib.request.OpenerDirector, index_name: str) -> dict:
    """Fetch the equity-stockIndices JSON for one index."""
    qs = urllib.parse.urlencode({"index": index_name})
    url = f"https://www.nseindia.com/api/equity-stockIndices?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "Referer": "https://www.nseindia.com/market-data/live-equity-market",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with opener.open(req, timeout=30) as r:
        body = r.read()
    return json.loads(body.decode("utf-8"))


def to_rows(payload: dict, snapshot_d: date) -> list[dict]:
    """Convert NSE payload to canonical TD-D1 rows.

    Row 0 is the index meta (symbol == index name). Rows 1+ are constituents.
    Per-stock weight = ffmc / sum(constituent ffmc). The index's own ffmc field
    is a different (normalized) unit and is NOT used as the denominator.
    """
    name = payload.get("name") or ""
    data = payload.get("data") or []
    constituents = [r for r in data if r.get("priority", 1) != 1]
    ffmc_total = sum(float(r.get("ffmc") or 0) for r in constituents)
    if ffmc_total <= 0:
        return []

    rows: list[dict] = []
    for r in constituents:
        ffmc = float(r.get("ffmc") or 0)
        if ffmc <= 0:
            continue
        rows.append(
            {
                "snapshot_date": snapshot_d.isoformat(),
                "index_name": name,
                "nse_symbol": r.get("symbol"),
                "ffmc_inr": ffmc,
                "weight_pct": round(100.0 * ffmc / ffmc_total, 6),
                "last_price": r.get("lastPrice"),
                "p_change_1d": r.get("pChange"),
                "p_change_30d": r.get("perChange30d"),
                "p_change_365d": r.get("perChange365d"),
                "year_high": r.get("yearHigh"),
                "year_low": r.get("yearLow"),
                "total_traded_value_inr": r.get("totalTradedValue"),
            }
        )
    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--indices", nargs="+", default=DEFAULT_INDICES,
                    help="Index names to fetch (default: 500/100/50/Next50/Midcap100/Smallcap100)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--snapshot-date", default=None,
                    help="Override snapshot date (YYYY-MM-DD). Default: today.")
    args = ap.parse_args(argv)

    snapshot_d = date.fromisoformat(args.snapshot_date) if args.snapshot_date else date.today()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    opener = _build_opener()
    _warm_cookies(opener)

    overall_rows: list[dict] = []
    per_index_summary: list[dict] = []
    for ix in args.indices:
        try:
            payload = fetch_index(opener, ix)
        except Exception as e:
            print(f"[{ix}] FETCH FAIL: {e}", file=sys.stderr)
            continue
        rows = to_rows(payload, snapshot_d)
        if not rows:
            print(f"[{ix}] empty rows after parse — skipping", file=sys.stderr)
            continue

        slug = ix.lower().replace(" ", "_")
        out_path = out_dir / f"{slug}_weights_{snapshot_d.isoformat()}.csv"
        write_csv(rows, out_path)
        weight_sum = round(sum(r["weight_pct"] for r in rows), 4)
        per_index_summary.append({
            "index_name": ix,
            "n_constituents": len(rows),
            "weight_pct_sum": weight_sum,
            "out_path": str(out_path.relative_to(REPO)),
        })
        overall_rows.extend(rows)
        print(f"[{ix}] {len(rows)} rows  sum_weight={weight_sum}%  -> {out_path.name}")
        time.sleep(1.0)

    # Combined snapshot for downstream loaders
    combined_path = out_dir / f"all_indices_weights_{snapshot_d.isoformat()}.csv"
    write_csv(overall_rows, combined_path)
    summary_path = out_dir / f"summary_{snapshot_d.isoformat()}.json"
    summary_path.write_text(
        json.dumps(
            {
                "snapshot_date": snapshot_d.isoformat(),
                "indices_fetched": per_index_summary,
                "total_rows": len(overall_rows),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\ncombined: {combined_path.name}  ({len(overall_rows)} rows)")
    print(f"summary:  {summary_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
