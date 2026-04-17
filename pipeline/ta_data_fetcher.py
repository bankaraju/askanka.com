"""
TA Data Fetcher — 5 years of daily OHLCV from EODHD for F&O stocks.
"""
from __future__ import annotations

import os
import csv
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.ta_data")

EODHD_BASE = "https://eodhd.com/api"
DEFAULT_CACHE = Path(__file__).parent / "data" / "ta_historical"
YEARS_BACK = 5


def _api_key() -> Optional[str]:
    key = os.getenv("EODHD_API_KEY", "").strip()
    return key if key and key != "YOUR_KEY_HERE" else None


def fetch_stock_history(
    symbol: str,
    cache_dir: Path = DEFAULT_CACHE,
    force: bool = False,
) -> Optional[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cache_dir / f"{symbol}.csv"

    if csv_path.exists() and not force:
        return csv_path

    key = _api_key()
    if not key:
        log.debug("EODHD_API_KEY not set — skipping %s", symbol)
        return None

    try:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=YEARS_BACK * 365)).strftime("%Y-%m-%d")

        resp = requests.get(
            f"{EODHD_BASE}/eod/{symbol}.NSE",
            params={"api_token": key, "fmt": "json", "from": from_date, "to": to_date},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or not data:
            log.warning("EODHD returned empty for %s", symbol)
            return None

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for row in data:
                if "close" in row and row["close"]:
                    writer.writerow([
                        row["date"], row.get("open", 0), row.get("high", 0),
                        row.get("low", 0), row["close"], row.get("volume", 0),
                    ])

        log.info("  %s: %d days fetched", symbol, len(data))
        return csv_path
    except Exception as exc:
        log.warning("EODHD fetch failed for %s: %s", symbol, exc)
        return None


def fetch_batch(
    symbols: list[str],
    cache_dir: Path = DEFAULT_CACHE,
    delay: float = 0.2,
    force: bool = False,
) -> dict[str, Optional[Path]]:
    results = {}
    for i, sym in enumerate(symbols):
        results[sym] = fetch_stock_history(sym, cache_dir=cache_dir, force=force)
        if delay > 0 and i < len(symbols) - 1:
            time.sleep(delay)
        if (i + 1) % 50 == 0:
            log.info("  Progress: %d/%d", i + 1, len(symbols))
    return results
