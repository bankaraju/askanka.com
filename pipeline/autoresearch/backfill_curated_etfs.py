"""Backfill yfinance daily bars for the curated ETF list expansion.

Source list: ``docs/superpowers/specs/cureated ETF.txt`` (2026-04-26).
Writes to: ``pipeline/data/research/phase_c/daily_bars/<friendly>.parquet``
in the same schema as existing files: ``[date, open, high, low, close, volume]``.

Skips any ticker whose parquet already exists with the curated start date
(2018-01-02) or earlier, so re-running is idempotent.

Usage:
    python -m pipeline.autoresearch.backfill_curated_etfs --start 2018-01-01 --end 2026-04-25
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_BARS = REPO_ROOT / "pipeline" / "data" / "research" / "phase_c" / "daily_bars"

# friendly_name → yfinance ticker. Friendly names match keys in
# pipeline/autoresearch/etf_v3_loader.py FOREIGN_ETFS dict.
CURATED_TICKERS: dict[str, str] = {
    "qqq":  "QQQ",
    "aiq":  "AIQ",
    "smh":  "SMH",
    "iwm":  "IWM",
    "xle":  "XLE",
    "xlv":  "XLV",
    "mchi": "MCHI",
    "dbb":  "DBB",
    "emb":  "EMB",
    "krbn": "KRBN",
    "lit":  "LIT",
    "kweb": "KWEB",
    "vixy": "VIXY",
    "ewg":  "EWG",
    "bito": "BITO",
}


def _yfinance_daily(yf_symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance, return DataFrame in canonical schema."""
    import yfinance as yf  # type: ignore
    raw = yf.download(yf_symbol, start=start, end=end, progress=False,
                      auto_adjust=True, threads=False)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index().rename(columns={"Date": "date", "Open": "open",
                                              "High": "high", "Low": "low",
                                              "Close": "close", "Volume": "volume"})
    raw["date"] = pd.to_datetime(raw["date"])
    cols = ["date", "open", "high", "low", "close", "volume"]
    for c in cols:
        if c not in raw.columns:
            raw[c] = pd.NA
    out = raw[cols].copy()
    out["volume"] = out["volume"].fillna(0).astype("int64")
    return out.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def _is_fresh(parquet_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """Return True if existing parquet already covers [start, end]."""
    if not parquet_path.exists():
        return False
    try:
        df = pd.read_parquet(parquet_path)
    except Exception:
        return False
    if "date" not in df.columns or len(df) == 0:
        return False
    df_start = pd.to_datetime(df["date"]).min()
    df_end = pd.to_datetime(df["date"]).max()
    # Allow up to 5 days of head/tail tolerance (weekends/holidays)
    return df_start <= start + pd.Timedelta(days=5) and df_end >= end - pd.Timedelta(days=5)


def backfill_one(friendly: str, yf_symbol: str, start: str, end: str,
                 *, force: bool = False) -> dict:
    """Fetch + write parquet for one curated ETF."""
    out_path = DAILY_BARS / f"{friendly}.parquet"
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    if not force and _is_fresh(out_path, start_ts, end_ts):
        return {"friendly": friendly, "yf_symbol": yf_symbol, "status": "skip_fresh",
                "rows": None, "first": None, "last": None, "path": str(out_path)}

    try:
        df = _yfinance_daily(yf_symbol, start, end)
    except Exception as exc:
        return {"friendly": friendly, "yf_symbol": yf_symbol, "status": "error",
                "error": str(exc), "rows": 0}

    if len(df) == 0:
        return {"friendly": friendly, "yf_symbol": yf_symbol, "status": "empty",
                "rows": 0}

    DAILY_BARS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return {"friendly": friendly, "yf_symbol": yf_symbol, "status": "written",
            "rows": int(len(df)),
            "first": str(df["date"].iloc[0].date()),
            "last": str(df["date"].iloc[-1].date()),
            "path": str(out_path)}


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill curated-list ETFs from yfinance")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2026-04-25")
    p.add_argument("--force", action="store_true", help="re-download even if fresh")
    p.add_argument("--only", default=None,
                   help="comma-separated friendly names to fetch (default: all)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    targets = CURATED_TICKERS
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        targets = {k: v for k, v in CURATED_TICKERS.items() if k in wanted}

    logger.info("backfilling %d ETFs from %s to %s", len(targets), args.start, args.end)
    results: list[dict] = []
    for i, (friendly, yf_sym) in enumerate(targets.items(), 1):
        logger.info("[%d/%d] %s (%s)", i, len(targets), friendly, yf_sym)
        r = backfill_one(friendly, yf_sym, args.start, args.end, force=args.force)
        results.append(r)
        logger.info("  -> %s rows=%s first=%s last=%s",
                    r["status"], r.get("rows"), r.get("first"), r.get("last"))
        time.sleep(0.5)  # be polite to yfinance

    print()
    print(f"{'friendly':<10} {'yf':<6} {'status':<12} {'rows':>5}  {'first':<11} {'last':<11}")
    print("-" * 70)
    for r in results:
        print(f"{r['friendly']:<10} {r['yf_symbol']:<6} {r['status']:<12} "
              f"{str(r.get('rows','-')):>5}  "
              f"{str(r.get('first','-')):<11} {str(r.get('last','-')):<11}")
    n_ok = sum(1 for r in results if r["status"] in ("written", "skip_fresh"))
    print(f"\n{n_ok}/{len(results)} OK ({n_ok-sum(1 for r in results if r['status']=='skip_fresh')} written, "
          f"{sum(1 for r in results if r['status']=='skip_fresh')} skipped)")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
