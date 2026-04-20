"""Historical bar fetcher with parquet cache.

Wraps pipeline.kite_client.fetch_historical for the backtest. Cache layout:
  daily_bars/<SYMBOL>.parquet                   - one file per symbol, all history
  minute_bars/<SYMBOL>_<YYYY-MM-DD>.parquet     - one file per symbol per trade day

On cache hit, no API call. On miss, calls Kite, writes cache, returns.
"""
from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

from . import paths

paths.ensure_cache()

_DAILY_DIR = paths.DAILY_BARS_DIR
_MINUTE_DIR = paths.MINUTE_BARS_DIR

log = logging.getLogger(__name__)


def _kite_fetch(symbol: str, interval: str, days: int) -> list[dict]:
    """Thin wrapper around the existing pipeline kite_client. Imported lazily
    so unit tests can patch it without triggering kite SDK import on collection."""
    from pipeline.kite_client import fetch_historical
    return fetch_historical(symbol, interval=interval, days=days)


def _to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_daily(symbol: str, days: int = 1500) -> pd.DataFrame:
    """Fetch daily OHLCV for `symbol` covering the last `days` calendar days.

    Cached at daily_bars/<symbol>.parquet. The cache is permanent (never expires
    on time alone) but is refetched if existing coverage spans fewer than ~90%
    of the requested `days`. To force a refetch, delete the cache file.
    """
    cache_path = Path(_DAILY_DIR) / f"{symbol}.parquet"
    if cache_path.is_file():
        try:
            df = pd.read_parquet(cache_path)
        except Exception as exc:
            log.warning("corrupt cache, re-fetching %s: %s", cache_path.name, exc)
            cache_path.unlink(missing_ok=True)
            df = None
        if df is not None:
            # Cache-coverage check: refetch if cache spans fewer business days
            # than requested. We compare against `days * 5/7` business-day estimate.
            if not df.empty:
                cache_span_days = (pd.Timestamp.now().normalize() - df["date"].min()).days
                requested_span_days = days
                # Allow 10% slack for weekends/holidays
                if cache_span_days < requested_span_days * 0.9:
                    log.info("cache coverage too short for %s (%d < %d days), refetching",
                             symbol, cache_span_days, requested_span_days)
                    cache_path.unlink(missing_ok=True)
                else:
                    log.debug("cache hit: %s daily (%d rows)", symbol, len(df))
                    return df
            else:
                log.debug("cache hit (empty): %s", symbol)
                return df
    rows = _kite_fetch(symbol, interval="day", days=days)
    df = _to_df(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    log.info("fetched + cached: %s daily (%d rows)", symbol, len(df))
    return df


def fetch_minute(symbol: str, trade_date: str) -> pd.DataFrame:
    """Fetch 1-minute bars for `symbol` on `trade_date` (YYYY-MM-DD).

    Cached at minute_bars/<symbol>_<trade_date>.parquet. Permanent cache.
    Empty results (e.g. Kite minute-bar retention exceeded) are still cached
    to avoid repeated retries; check len(df) on the caller side.
    """
    cache_path = Path(_MINUTE_DIR) / f"{symbol}_{trade_date}.parquet"
    if cache_path.is_file():
        try:
            df = pd.read_parquet(cache_path)
            log.debug("cache hit: %s minute %s (%d rows)", symbol, trade_date, len(df))
            return df
        except Exception as exc:
            log.warning("corrupt cache, re-fetching %s: %s", cache_path.name, exc)
            cache_path.unlink(missing_ok=True)
    # Days back from today to cover trade_date
    days_back = max(1, (pd.Timestamp.now().normalize() - pd.Timestamp(trade_date)).days + 2)
    rows = _kite_fetch(symbol, interval="minute", days=days_back)
    df = _to_df(rows)
    df = df[df["date"].dt.strftime("%Y-%m-%d") == trade_date].copy()
    if df.empty:
        log.warning("no minute bars returned for %s on %s — possible Kite retention limit or delisted",
                    symbol, trade_date)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    log.info("fetched + cached: %s minute %s (%d rows)", symbol, trade_date, len(df))
    return df
