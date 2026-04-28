"""Kite 1-min historical loader + parquet cache for V1 framework.

Per data audit `docs/superpowers/specs/2026-04-29-kite-1min-data-source-audit.md`:
- 60 calendar days rolling = ~44 trading days × 375 min/day = ~16,500 candles
- Kite caps single-call response at ~3,000 candles → real paging by 7-day windows
- Cache delta-refreshes only [last_ts, now] after first fetch.

Implementation note: ``pipeline.kite_client`` exposes ``fetch_historical`` as a
single-call function with no from/to-window parameters, which silently caps
minute-interval requests at ~3,000 candles. We bypass that and call the
underlying ``KiteConnect.historical_data(token, from_date, to_date, interval)``
directly through a thin adapter, with proper 7-day window paging.
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
DELTA_REFRESH_DAYS = 5  # covers a 4-day bridge-holiday gap

log = logging.getLogger("intraday_v1.loader")


class LoaderError(RuntimeError):
    """Raised when Kite fetch fails or returns garbage."""


class _KiteAdapter:
    """Thin wrapper over ``pipeline.kite_client`` that exposes the two
    primitives `loader.fetch_1min` actually needs:

    - ``resolve_token(symbol) -> int`` (or raise LoaderError)
    - ``historical_data(token, from_dt, to_dt, interval) -> list[dict]``

    Tests monkeypatch ``_kite_client`` to return a MagicMock with these
    same two attributes, sidestepping the real Kite session.
    """

    def resolve_token(self, symbol: str) -> int:
        from pipeline import kite_client as _kc
        token = _kc.resolve_token(symbol)
        if token is None:
            raise LoaderError(f"resolve_token returned None for {symbol}")
        return int(token)

    def historical_data(
        self,
        token: int,
        from_dt: datetime,
        to_dt: datetime,
        interval: str = "minute",
    ) -> list[dict]:
        from pipeline import kite_client as _kc
        kite = _kc.get_kite()
        return kite.historical_data(
            instrument_token=token,
            from_date=from_dt.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=to_dt.strftime("%Y-%m-%d %H:%M:%S"),
            interval=interval,
            continuous=False,
            oi=False,
        )


def _kite_client() -> _KiteAdapter:
    """Lazy adapter factory. Tests monkeypatch this to return a MagicMock."""
    return _KiteAdapter()


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


def fetch_1min(symbol: str, days: int = 60) -> pd.DataFrame:
    """Fetch ``days`` calendar-days of 1-min OHLCV via real 7-day paged calls.

    Each page covers a ``PAGE_DAYS``-day window; pages are concatenated, then
    deduplicated by timestamp (so an overlap at page boundaries is harmless).
    """
    kite = _kite_client()
    token = kite.resolve_token(symbol)
    end = datetime.now(IST)
    start = end - timedelta(days=days)
    pages: list[pd.DataFrame] = []
    cursor = start
    while cursor < end:
        page_end = min(cursor + timedelta(days=PAGE_DAYS), end)
        rows = kite.historical_data(token, cursor, page_end, "minute")
        if not rows:
            raise LoaderError(
                f"Kite empty response for {symbol} window {cursor} → {page_end}"
            )
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


def cache_path(symbol: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{symbol}.parquet"


def write_cache(symbol: str, df: pd.DataFrame) -> None:
    df.to_parquet(cache_path(symbol), index=False)


def read_cache(symbol: str) -> Optional[pd.DataFrame]:
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
    token = kite.resolve_token(symbol)
    end = datetime.now(IST)
    delta_start = end - timedelta(days=DELTA_REFRESH_DAYS)
    new_rows = kite.historical_data(token, delta_start, end, "minute")
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
