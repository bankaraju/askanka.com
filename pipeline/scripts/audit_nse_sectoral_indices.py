"""Audit script for nse_sectoral_indices_v1 (Task 0a #230 follow-up).

Reads the 10 sectoral-index CSVs at pipeline/data/sectoral_indices/,
computes cleanliness stats per policy §9, and pulls fresh yfinance
data for §13 reconciliation on 3 dates × 3 spot-check indices.

Output: pipeline/data/research/edb/sectoral_indices_audit_<date>.json
(gitignored — re-run to regenerate). Also prints a summary table.

Reproduces the numbers cited in
docs/superpowers/specs/2026-04-25-nse-sectoral-indices-data-source-audit.md
(§9.1 cleanliness baseline + §13 independent corroboration).
"""
from __future__ import annotations

import json
import logging
import random
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "pipeline" / "data" / "sectoral_indices"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "edb"

INDEX_MAP = {
    "BANKNIFTY": "^NSEBANK",
    "NIFTYIT": "^CNXIT",
    "NIFTYPHARMA": "^CNXPHARMA",
    "NIFTYAUTO": "^CNXAUTO",
    "NIFTYFMCG": "^CNXFMCG",
    "NIFTYMETAL": "^CNXMETAL",
    "NIFTYENERGY": "^CNXENERGY",
    "NIFTYPSUBANK": "^CNXPSUBANK",
    "NIFTYREALTY": "^CNXREALTY",
    "NIFTYMEDIA": "^CNXMEDIA",
}

SPOT_CHECK_INDICES = ["BANKNIFTY", "NIFTYIT", "NIFTYPHARMA"]
RECONCILIATION_PASS_THRESHOLD_PCT = 0.5
SAMPLE_SEED = 20260428

log = logging.getLogger(__name__)


def cleanliness_stats(csv_path: Path) -> dict:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)
    first = df["date"].min().date().isoformat() if n else None
    last = df["date"].max().date().isoformat() if n else None

    bdays = 0
    if n:
        bdays = len(pd.bdate_range(df["date"].min(), df["date"].max()))

    zero_or_neg = int(((df["close"] <= 0) | df["close"].isna()).sum())
    dup_dates = int(df["date"].duplicated().sum())
    missing_pct = (1 - n / bdays) * 100 if bdays else 0.0

    return {
        "n_rows": n,
        "first_date": first,
        "last_date": last,
        "business_days_in_range": bdays,
        "density_pct": round(n / bdays * 100, 2) if bdays else 0.0,
        "missing_pct": round(missing_pct, 2),
        "zero_or_neg_close_count": zero_or_neg,
        "duplicate_date_count": dup_dates,
    }


def pick_spot_check_dates(df: pd.DataFrame, n: int = 3) -> list[str]:
    """Random sample of dates from the most-recent 250 rows (~1y)."""
    recent = df.sort_values("date").tail(250)
    rng = random.Random(SAMPLE_SEED)
    chosen = rng.sample(list(recent["date"]), min(n, len(recent)))
    return sorted([pd.Timestamp(d).date().isoformat() for d in chosen])


def fetch_yf_close(ticker: str, dates: list[str]) -> dict[str, float]:
    if not dates:
        return {}
    start = (pd.Timestamp(min(dates)) - pd.Timedelta(days=2)).date()
    end = (pd.Timestamp(max(dates)) + pd.Timedelta(days=2)).date()
    try:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(), end=end.isoformat(),
            auto_adjust=False,
        )
    except Exception as exc:
        log.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return dict.fromkeys(dates, None)
    out: dict[str, float | None] = {}
    for d in dates:
        ts = pd.Timestamp(d)
        if ts in hist.index:
            out[d] = float(hist.loc[ts, "Close"])
        else:
            mask = hist.index.date == ts.date()
            if mask.any():
                out[d] = float(hist.loc[mask, "Close"].iloc[0])
            else:
                out[d] = None
    return out


def reconcile(csv_path: Path, yf_ticker: str, dates: list[str]) -> list[dict]:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df["date_iso"] = df["date"].dt.date.astype(str)
    yf_closes = fetch_yf_close(yf_ticker, dates)
    rows: list[dict] = []
    for d in dates:
        local_close = None
        match = df[df["date_iso"] == d]
        if not match.empty:
            local_close = float(match.iloc[0]["close"])
        yf_close = yf_closes.get(d)
        delta_pct = None
        if local_close and yf_close:
            delta_pct = round((yf_close - local_close) / local_close * 100, 4)
        rows.append({
            "date": d,
            "local_close": round(local_close, 4) if local_close else None,
            "yfinance_close": round(yf_close, 4) if yf_close else None,
            "delta_pct": delta_pct,
        })
    return rows


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"sectoral_indices_audit_{date.today().isoformat()}.json"

    audit: dict = {
        "audit_date": date.today().isoformat(),
        "task": "EDB T0a follow-up (#230)",
        "dataset_id": "nse_sectoral_indices_v1",
        "source_dir": "pipeline/data/sectoral_indices/",
        "cleanliness_per_index": {},
        "reconciliation": {
            "method": (
                f"yfinance close on 3 random recent dates per spot-check "
                f"index, compared to local CSV close. "
                f"PASS criterion: max |delta_pct| < "
                f"{RECONCILIATION_PASS_THRESHOLD_PCT}%."
            ),
            "indices": {},
        },
    }

    for index_key in INDEX_MAP:
        csv_path = SRC / f"{index_key}_daily.csv"
        audit["cleanliness_per_index"][index_key] = cleanliness_stats(csv_path)

    for index_key in SPOT_CHECK_INDICES:
        df = pd.read_csv(SRC / f"{index_key}_daily.csv", parse_dates=["date"])
        dates = pick_spot_check_dates(df, n=3)
        rows = reconcile(SRC / f"{index_key}_daily.csv", INDEX_MAP[index_key], dates)
        deltas = [r["delta_pct"] for r in rows if r["delta_pct"] is not None]
        max_abs = max((abs(d) for d in deltas), default=None)
        audit["reconciliation"]["indices"][index_key] = {
            "yfinance_ticker": INDEX_MAP[index_key],
            "spot_check_dates": dates,
            "rows": rows,
            "max_abs_delta_pct": max_abs,
            "verdict": (
                "PASS" if max_abs is not None and max_abs < RECONCILIATION_PASS_THRESHOLD_PCT
                else ("FAIL" if max_abs is not None else "NETWORK_FAIL")
            ),
        }

    out_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    log.info("wrote %s", out_path.relative_to(REPO))

    print("\nCleanliness summary:")
    for k, v in audit["cleanliness_per_index"].items():
        print(f"  {k:<14} n={v['n_rows']:>5} "
              f"range={v['first_date']}..{v['last_date']} "
              f"density={v['density_pct']}% zero/neg={v['zero_or_neg_close_count']} "
              f"dup={v['duplicate_date_count']}")

    print("\nReconciliation summary:")
    for k, v in audit["reconciliation"]["indices"].items():
        print(f"  {k}: dates={v['spot_check_dates']} "
              f"max|delta|={v['max_abs_delta_pct']}% verdict={v['verdict']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
