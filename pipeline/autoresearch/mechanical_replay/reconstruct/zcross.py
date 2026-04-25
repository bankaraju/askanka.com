"""Per-minute peer-relative Z_CROSS exit-time reconstruction.

For a single Phase C trade, this module walks the minute bars from 09:30
onward and returns the FIRST minute when the peer-relative z-score crosses
zero (changes sign from `entry_sign`).

The peer residual at minute t is defined as:

    residual_t = log(stock_price_t / stock_price_t0)
               - log(sector_price_t / sector_price_t0)

(equivalent to a 1×1 leverage relative-return spread). This residual is
z-scored against its own rolling history within the same trading session
using a `rolling_window` minute-bar lookback.

The simulator already accepts a `zcross_time` parameter (`pipeline/auto-
research/mechanical_replay/simulator.py`); v2 just populates it.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _normalise_minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Coerce input frame to columns [datetime, close], time-sorted."""
    df = bars.copy()
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif "timestamp" in df.columns:
        df = df.rename(columns={"timestamp": "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif "time" in df.columns:
        df = df.rename(columns={"time": "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif df.index.name in ("datetime", "timestamp", "time"):
        df = df.reset_index().rename(columns={df.index.name: "datetime"})
        df["datetime"] = pd.to_datetime(df["datetime"])
    else:
        raise ValueError("minute bars must have a datetime/timestamp/time column or index")
    if "close" not in df.columns:
        raise ValueError("minute bars must have a `close` column")
    return df[["datetime", "close"]].sort_values("datetime").reset_index(drop=True)


def _residual_series(
    stock_bars: pd.DataFrame, sector_bars: pd.DataFrame
) -> pd.DataFrame:
    """Inner-join on datetime, compute log-relative-return residual."""
    s = _normalise_minute_bars(stock_bars).rename(columns={"close": "stock_close"})
    p = _normalise_minute_bars(sector_bars).rename(columns={"close": "sector_close"})
    merged = s.merge(p, on="datetime", how="inner")
    if merged.empty:
        return merged
    s0 = float(merged["stock_close"].iloc[0])
    p0 = float(merged["sector_close"].iloc[0])
    merged["residual"] = (
        np.log(merged["stock_close"] / s0) - np.log(merged["sector_close"] / p0)
    )
    return merged


def find_zcross_minute(
    *,
    stock_minute_bars: pd.DataFrame,
    sector_minute_bars: pd.DataFrame,
    entry_sign: int,
    rolling_window: int = 30,
) -> Optional[pd.Timestamp]:
    """Return the first minute timestamp where the peer-relative z-score
    crosses zero (changes sign from entry_sign), or None if no cross.

    Parameters
    ----------
    stock_minute_bars, sector_minute_bars : pd.DataFrame
        Each frame has datetime + close columns.
    entry_sign : int
        +1 if entry was on a positive residual (stock above peer), -1 if
        negative.
    rolling_window : int
        Minute-bar lookback for the residual z-score. Default 30.

    Returns
    -------
    pd.Timestamp | None
        First crossing minute (sign change from entry_sign), or None.
    """
    if entry_sign not in (-1, +1):
        raise ValueError(f"entry_sign must be +1 or -1, got {entry_sign}")
    df = _residual_series(stock_minute_bars, sector_minute_bars)
    if len(df) <= rolling_window:
        return None
    rolling_mean = df["residual"].rolling(rolling_window, min_periods=rolling_window).mean()
    rolling_std = df["residual"].rolling(rolling_window, min_periods=rolling_window).std(ddof=1)
    z = (df["residual"] - rolling_mean) / rolling_std.replace(0, np.nan)
    df["z"] = z
    df = df.dropna(subset=["z"]).reset_index(drop=True)
    if df.empty:
        return None
    # First minute where sign(z) flips relative to entry_sign.
    if entry_sign > 0:
        crosses = df.index[df["z"] <= 0]
    else:
        crosses = df.index[df["z"] >= 0]
    if len(crosses) == 0:
        return None
    return pd.Timestamp(df.loc[crosses[0], "datetime"])
