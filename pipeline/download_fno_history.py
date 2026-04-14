"""
Anka Research — Download Historical Prices for Full F&O Universe
One-time backfill: 213 F&O stocks × 1 year via yfinance ($0).

Saves to pipeline/data/fno_historical/<SYMBOL>.csv
Can be re-run safely — skips stocks with fresh cache (<12h old).

Usage:
    python download_fno_history.py          # all 213 stocks
    python download_fno_history.py --days 730   # 2 years
    python download_fno_history.py --force      # ignore cache
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fno_download")

PIPELINE_DIR = Path(__file__).parent
FNO_FILE = PIPELINE_DIR.parent / "opus" / "config" / "fno_stocks.json"
HIST_DIR = PIPELINE_DIR / "data" / "fno_historical"
HIST_DIR.mkdir(parents=True, exist_ok=True)

# Stocks with known yfinance ticker mismatches
TICKER_OVERRIDES = {
    "360ONE": "360ONE.NS",
    "M&M": "M&M.NS",
    "M&MFIN": "M&MFIN.NS",
    "NAM-INDIA": "NAM-INDIA.NS",
    "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
}


def yf_ticker(symbol: str) -> str:
    """Convert NSE symbol to yfinance ticker."""
    if symbol in TICKER_OVERRIDES:
        return TICKER_OVERRIDES[symbol]
    return f"{symbol}.NS"


def load_fno_universe() -> list[str]:
    """Load the F&O stock list."""
    data = json.loads(FNO_FILE.read_text(encoding="utf-8"))
    return data["symbols"]


def download_stock(symbol: str, days: int = 400, force: bool = False) -> int:
    """Download history for one stock. Returns row count or 0 on failure."""
    csv_path = HIST_DIR / f"{symbol}.csv"

    # Skip if cache is fresh
    if not force and csv_path.exists():
        mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
        if (datetime.now() - mtime) < timedelta(hours=12):
            df = pd.read_csv(csv_path)
            return len(df)

    ticker = yf_ticker(symbol)
    end = datetime.now()
    start = end - timedelta(days=days)

    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or len(df) < 10:
            log.warning("Insufficient data for %s (%s): %d rows",
                        symbol, ticker, len(df) if df is not None else 0)
            return 0

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.to_csv(csv_path)
        return len(df)

    except Exception as exc:
        log.warning("Failed %s (%s): %s", symbol, ticker, exc)
        return 0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=400, help="Days of history")
    parser.add_argument("--force", action="store_true", help="Ignore cache")
    args = parser.parse_args()

    symbols = load_fno_universe()
    log.info("F&O universe: %d stocks, fetching %d days of history", len(symbols), args.days)

    success = 0
    failed = []
    cached = 0
    total_rows = 0

    for i, sym in enumerate(symbols, 1):
        csv_path = HIST_DIR / f"{sym}.csv"
        if not args.force and csv_path.exists():
            mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
            if (datetime.now() - mtime) < timedelta(hours=12):
                cached += 1
                rows = len(pd.read_csv(csv_path))
                total_rows += rows
                continue

        rows = download_stock(sym, days=args.days, force=args.force)
        if rows > 0:
            success += 1
            total_rows += rows
            log.info("[%d/%d] %s: %d rows", i, len(symbols), sym, rows)
        else:
            failed.append(sym)
            log.warning("[%d/%d] %s: FAILED", i, len(symbols), sym)

        # Courtesy pause to avoid yfinance rate limiting
        if i % 20 == 0:
            time.sleep(1)

    log.info("=" * 60)
    log.info("DOWNLOAD COMPLETE")
    log.info("  Success: %d | Cached: %d | Failed: %d | Total: %d",
             success, cached, len(failed), len(symbols))
    log.info("  Total rows: %d", total_rows)
    if failed:
        log.info("  Failed symbols: %s", ", ".join(failed))
    log.info("  Data directory: %s", HIST_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
