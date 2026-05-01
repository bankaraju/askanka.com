"""IndianAPI nightly backfill: TD-D7 (FII shareholding history) + TD-D9 (EPS surprise).

Pulls per-stock data with rate-limit-aware backoff. Saves raw JSON + a flat
CSV summary suitable for theme detector signal consumption.

TD-D7 endpoint: /historical_stats?stats=shareholding_pattern_quarterly
  → returns full quarterly history per stock, ~8 quarters

TD-D9 endpoints:
  /stock_forecasts?measure_code=EPS&data_type=Estimates&period_type=Interim&age=ThirtyDaysAgo
  /stock_forecasts?measure_code=EPS&data_type=Actuals&period_type=Interim&age=Current

Run modes:
  --mode td_d7              # one-shot full TD-D7 backfill (213 calls)
  --mode td_d9_quarter      # one quarter both Estimates+Actuals (213 × 2 = 426 calls)
  --mode probe              # single stock, both endpoints

Rate-limit policy:
  - retry on 429 with exponential backoff (60s, 120s, 240s, max 600s)
  - every successful call sleeps 1.5s before next (gentle throttle)
  - emits progress every 25 stocks so a long run is monitor-able

Output:
  pipeline/data/research/theme_detector/td_d7/<symbol>.json (raw)
  pipeline/data/research/theme_detector/td_d7/_index_<date>.csv (flat summary)
  pipeline/data/research/theme_detector/td_d9/<symbol>_<dt>_<flavour>.json
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENV_PATH = REPO / "pipeline" / ".env"
OUT_BASE = REPO / "pipeline" / "data" / "research" / "theme_detector"

BASE = "https://stock.indianapi.in"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BACKOFF_LADDER = (60, 120, 240, 480, 600)  # seconds — caps at 10 min
MAX_RETRIES = 6
SUCCESS_SLEEP = 1.5  # seconds between successful calls


def _load_key() -> str:
    for ln in ENV_PATH.read_text().splitlines():
        if ln.startswith("INDIANAPI_KEY="):
            return ln.split("=", 1)[1].strip()
    raise SystemExit("INDIANAPI_KEY missing from pipeline/.env")


def _hit(path: str, params: dict, key: str) -> tuple[int, dict | str]:
    """Returns (status, parsed_body_or_err_str)."""
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "X-Api-Key": key,
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return -1, f"EXC: {type(e).__name__}: {e}"


def _retry_call(path: str, params: dict, key: str, label: str) -> dict | None:
    """Hit endpoint with backoff on 429; return parsed dict or None on terminal fail."""
    for attempt in range(MAX_RETRIES):
        status, body = _hit(path, params, key)
        if status == 200:
            return body if isinstance(body, dict) else {"data": body}
        if status == 429:
            wait_s = BACKOFF_LADDER[min(attempt, len(BACKOFF_LADDER) - 1)]
            print(f"  [{label}] 429 — backoff {wait_s}s (attempt {attempt+1}/{MAX_RETRIES})")
            time.sleep(wait_s)
            continue
        # Other terminal errors (404, 403, 500, EXC)
        print(f"  [{label}] {status} {str(body)[:150]}")
        return None
    print(f"  [{label}] EXHAUSTED {MAX_RETRIES} retries — giving up")
    return None


def _frozen_universe() -> list[str]:
    """Theme detector frozen universe: union of all rule_kind=A theme members."""
    themes_path = REPO / "pipeline" / "research" / "theme_detector" / "themes_frozen.json"
    data = json.loads(themes_path.read_text(encoding="utf-8"))
    members: set[str] = set()
    for t in data.get("themes", []):
        if t.get("rule_kind") == "A":
            members.update(t.get("rule_definition", {}).get("members", []))
    return sorted(members)


def _canonical_fno_universe() -> list[str]:
    """213-stock canonical F&O universe (preferred for backfill scope)."""
    p = REPO / "pipeline" / "config" / "canonical_fno_research_v3.json"
    if not p.exists():
        return _frozen_universe()
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("stocks", "tickers", "universe"):
            if k in data:
                return list(data[k])
    return _frozen_universe()


def fetch_td_d7(universe: list[str], key: str, snapshot_d: date, max_n: int) -> int:
    out_dir = OUT_BASE / "td_d7"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    summary_rows: list[dict] = []

    for i, sym in enumerate(universe[:max_n], 1):
        out_path = out_dir / f"{sym}.json"
        if out_path.exists():
            saved += 1
            continue
        data = _retry_call(
            "/historical_stats",
            {"stock_name": sym, "stats": "shareholding_pattern_quarterly"},
            key,
            f"TD-D7 {sym} ({i}/{min(max_n, len(universe))})",
        )
        if data is None:
            continue
        out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        saved += 1

        # Surface latest FII row to summary
        latest_fii = None
        latest_qtr = None
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if any("FII" in str(kk) or "fii" in str(kk).lower() for kk in v[0].keys()):
                    latest_fii = v[0]
                    latest_qtr = k
                    break
        summary_rows.append({
            "snapshot_date": snapshot_d.isoformat(),
            "nse_symbol": sym,
            "found_history": bool(data),
            "latest_qtr_key": latest_qtr,
            "json_path": str(out_path.relative_to(REPO)),
        })
        if i % 25 == 0:
            print(f"  TD-D7 progress: {i} done, {saved} on-disk")
        time.sleep(SUCCESS_SLEEP)

    if summary_rows:
        idx_path = out_dir / f"_index_{snapshot_d.isoformat()}.csv"
        with idx_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            w.writeheader()
            w.writerows(summary_rows)
        print(f"TD-D7 index: {idx_path.name}  ({len(summary_rows)} rows)")
    return saved


def fetch_td_d9_quarter(
    universe: list[str], key: str, snapshot_d: date, max_n: int,
    age: str = "ThirtyDaysAgo",
) -> int:
    out_dir = OUT_BASE / "td_d9"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for i, sym in enumerate(universe[:max_n], 1):
        for flavour, dt in [("estimates", "Estimates"), ("actuals", "Actuals")]:
            out_path = out_dir / f"{sym}_{age}_{flavour}.json"
            if out_path.exists():
                saved += 1
                continue
            params = {
                "stock_id": sym,
                "measure_code": "EPS",
                "period_type": "Interim",
                "data_type": dt,
                "age": age if flavour == "estimates" else "Current",
            }
            data = _retry_call(
                "/stock_forecasts",
                params,
                key,
                f"TD-D9 {sym} {flavour} ({i}/{min(max_n, len(universe))})",
            )
            if data is None:
                continue
            out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            saved += 1
            time.sleep(SUCCESS_SLEEP)
        if i % 25 == 0:
            print(f"  TD-D9 progress: {i} done, {saved} on-disk")
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["td_d7", "td_d9_quarter", "probe"], required=True)
    ap.add_argument("--universe", choices=["theme_members", "fno_canonical"],
                    default="theme_members")
    ap.add_argument("--max-n", type=int, default=300,
                    help="Cap on stocks per run (testing/throttling)")
    ap.add_argument("--age", default="ThirtyDaysAgo",
                    help="EPS estimate age window (TD-D9 only)")
    args = ap.parse_args(argv)

    key = _load_key()
    universe = (
        _frozen_universe() if args.universe == "theme_members"
        else _canonical_fno_universe()
    )
    snapshot_d = date.today()
    print(f"[{args.mode}] universe={args.universe} ({len(universe)} stocks), max_n={args.max_n}")
    print(f"output base: {OUT_BASE.relative_to(REPO)}")

    if args.mode == "probe":
        print("PROBE: TD-D7 HDFCBANK, then TD-D9 HDFCBANK estimates")
        d7 = _retry_call(
            "/historical_stats",
            {"stock_name": "HDFCBANK", "stats": "shareholding_pattern_quarterly"},
            key, "TD-D7 HDFCBANK",
        )
        print("TD-D7 HDFCBANK:", "OK" if d7 else "FAIL",
              f"keys={list(d7.keys())[:8]}" if isinstance(d7, dict) else "")
        d9 = _retry_call(
            "/stock_forecasts",
            {"stock_id": "HDFCBANK", "measure_code": "EPS",
             "period_type": "Interim", "data_type": "Estimates", "age": "ThirtyDaysAgo"},
            key, "TD-D9 HDFCBANK estimates",
        )
        print("TD-D9 HDFCBANK estimates:", "OK" if d9 else "FAIL",
              f"keys={list(d9.keys())[:8]}" if isinstance(d9, dict) else "")
        if d7:
            (OUT_BASE / "td_d7").mkdir(parents=True, exist_ok=True)
            (OUT_BASE / "td_d7" / "HDFCBANK.json").write_text(
                json.dumps(d7, indent=2, default=str), encoding="utf-8")
        if d9:
            (OUT_BASE / "td_d9").mkdir(parents=True, exist_ok=True)
            (OUT_BASE / "td_d9" / f"HDFCBANK_ThirtyDaysAgo_estimates.json").write_text(
                json.dumps(d9, indent=2, default=str), encoding="utf-8")
        return 0

    if args.mode == "td_d7":
        n = fetch_td_d7(universe, key, snapshot_d, args.max_n)
        print(f"\nTD-D7 saved {n} files")
        return 0

    if args.mode == "td_d9_quarter":
        n = fetch_td_d9_quarter(universe, key, snapshot_d, args.max_n, args.age)
        print(f"\nTD-D9 ({args.age}) saved {n} files")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
