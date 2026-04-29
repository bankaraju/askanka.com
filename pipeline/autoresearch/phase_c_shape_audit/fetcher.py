"""Fetch minute bars for a (ticker, date) session from Kite, cached to parquet.

Spec §5.1. The fetch window is 09:15-15:35 IST. Cache key is
<TICKER>_<YYYYMMDD>.parquet. Re-running on a cached pair is a disk read only.
"""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Callable

import pandas as pd

from pipeline.autoresearch.phase_c_shape_audit import constants as C

CACHE_COLUMNS = ["timestamp_ist", "open", "high", "low", "close", "volume"]


def _cache_path(bars_dir: Path, ticker: str, trade_date: date) -> Path:
    return bars_dir / f"{ticker.upper()}_{trade_date.strftime('%Y%m%d')}.parquet"


def _default_kite_session():
    from pipeline.kite_auth import get_kite_client
    return get_kite_client()


def _default_token_resolver(ticker: str) -> int | None:
    from pipeline.kite_client import resolve_token
    return resolve_token(ticker)


def fetch_minute_bars(
    *,
    ticker: str,
    trade_date: date,
    bars_dir: Path = C.BARS_DIR,
    kite_session=None,
    token_resolver: Callable[[str], int | None] | None = None,
) -> pd.DataFrame:
    """Return minute bars for the IST session of trade_date.

    Cached to bars_dir/<TICKER>_<YYYYMMDD>.parquet. On cache miss, calls
    kite_session.historical_data with from=09:15 to=15:35 of trade_date and
    persists the result. Returns DataFrame with columns CACHE_COLUMNS.
    """
    bars_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(bars_dir, ticker, trade_date)
    if path.exists():
        return pd.read_parquet(path)

    session = kite_session if kite_session is not None else _default_kite_session()
    resolver = token_resolver if token_resolver is not None else _default_token_resolver
    token = resolver(ticker)
    if token is None:
        raise ValueError(f"No instrument token for {ticker}")

    from_dt = datetime.combine(trade_date, time(9, 15))
    to_dt = datetime.combine(trade_date, time(15, 35))

    candles = session.historical_data(
        instrument_token=token,
        from_date=from_dt.strftime("%Y-%m-%d %H:%M:%S"),
        to_date=to_dt.strftime("%Y-%m-%d %H:%M:%S"),
        interval="minute",
        continuous=False,
        oi=False,
    )
    rows: list[dict] = []
    for c in candles:
        ts = c["date"]
        if hasattr(ts, "strftime"):
            ts_value = pd.Timestamp(ts).tz_localize(None)
        else:
            ts_value = pd.Timestamp(str(ts)).tz_localize(None)
        rows.append({
            "timestamp_ist": ts_value,
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": int(c.get("volume", 0)),
        })
    df = pd.DataFrame(rows, columns=CACHE_COLUMNS)
    df.to_parquet(path, index=False)
    return df
