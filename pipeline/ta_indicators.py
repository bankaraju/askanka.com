"""
Technical Analysis Indicator Library — pure math, no I/O.

All functions take pandas Series or DataFrame, return Series or DataFrame.
No side effects, no file reads, no API calls.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    close = df["Close"]
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    # When avg_loss is zero AND avg_gain > 0 (pure uptrend), RSI = 100.
    # When both are zero (flat series), return NaN — no directional information.
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    rsi_vals = np.where(
        both_zero,
        np.nan,
        np.where(
            avg_loss == 0,
            100.0,
            100.0 - (100.0 / (1.0 + avg_gain / avg_loss)),
        ),
    )
    return pd.Series(rsi_vals, index=close.index)
