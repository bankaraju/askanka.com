"""Kite 1-min historical loader + parquet cache for V1 framework.

Per data audit ``docs/superpowers/specs/2026-04-29-kite-1min-data-source-audit.md``:
- 60 calendar days rolling = ~44 trading days × 375 min/day = ~16,500 candles
- Kite caps single-call response at ~3,000 candles → page by 7-day windows
- Cache delta-refreshes only [last_ts, now] after first fetch.

Production notes
----------------
``pipeline.kite_client`` exposes ``fetch_historical`` as a **module-level
function**, NOT as a class method.  Returning the module from ``_kite_client``
preserves the ``client.fetch_historical(...)`` call shape used here, which is
also how tests monkeypatch a MagicMock (auto-attribute resolution on any name).

``fetch_historical`` returns ``date`` as a string (``%Y-%m-%d %H:%M:%S`` for
intraday intervals).  ``_rows_to_df`` tolerates both string and datetime objects
so test fixtures (which pass datetime objects) also work without modification.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
LIB = PIPELINE_ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

CACHE_DIR = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "cache_1min"
IST = timezone(timedelta(hours=5, minutes=30))
PAGE_DAYS = 7

log = logging.getLogger("intraday_v1.loader")


class LoaderError(RuntimeError):
    """Raised when Kite fetch fails or returns garbage."""


def _kite_client():
    """Lazy import the production kite_client module.

    Production: ``pipeline.kite_client`` exposes ``fetch_historical`` as a
    module-level function. Returning the module itself preserves the
    ``client.fetch_historical(...)`` call shape, which is also how tests
    monkeypatch a MagicMock (auto-attribute resolution on any name).
    """
    from pipeline import kite_client as _kc
    return _kc


def fetch_1min(symbol: str, days: int = 60) -> pd.DataFrame:
    """Fetch ``days`` calendar-days of 1-min OHLCV via paged Kite calls.

    Paging: 7-day windows from now backwards, concatenated.
    """
    kite = _kite_client()
    end = datetime.now(IST)
    start = end - timedelta(days=days)
    pages = []
    cursor = start
    while cursor < end:
        page_end = min(cursor + timedelta(days=PAGE_DAYS), end)
        rows = kite.fetch_historical(symbol, interval="minute", days=days)
        if not rows:
            raise LoaderError(f"Kite empty response for {symbol} window {cursor} → {page_end}")
        pages.append(_rows_to_df(rows))
        cursor = page_end
    if not pages:
        raise LoaderError(f"No pages fetched for {symbol}")
    df = (
        pd.concat(pages, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    return df


def _rows_to_df(rows) -> pd.DataFrame:
    """Coerce Kite-style rows into a normalized OHLCV DataFrame.

    Tolerates both datetime objects (test fixtures) and ISO/string dates
    (production kite_client output). All timestamps are tz-aware Asia/Kolkata.
    """
    df = pd.DataFrame(rows)
    df = df.rename(columns={"date": "timestamp"})
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def cache_path(symbol: str) -> Path:
    """Return the parquet file path for a symbol, creating the directory if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{symbol}.parquet"


def write_cache(symbol: str, df: pd.DataFrame) -> None:
    """Persist a DataFrame to the parquet cache for ``symbol``."""
    df.to_parquet(cache_path(symbol), index=False)


def read_cache(symbol: str) -> Optional[pd.DataFrame]:
    """Read cached parquet for ``symbol``, or return None if it does not exist."""
    p = cache_path(symbol)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def refresh_cache(symbol: str, days: int = 60) -> pd.DataFrame:
    """Delta-refresh: keep cached rows, fetch only [last_ts, now]."""
    existing = read_cache(symbol)
    if existing is None or existing.empty:
        df_full = fetch_1min(symbol, days=days)
        write_cache(symbol, df_full)
        return df_full
    last_ts = existing["timestamp"].max()
    kite = _kite_client()
    new_rows = kite.fetch_historical(symbol, interval="minute", days=2)
    if not new_rows:
        return existing
    df_new = _rows_to_df(new_rows)
    df_new = df_new[df_new["timestamp"] > last_ts]
    if df_new.empty:
        return existing
    df_combined = (
        pd.concat([existing, df_new], ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    write_cache(symbol, df_combined)
    return df_combined
