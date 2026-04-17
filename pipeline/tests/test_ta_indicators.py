"""Tests for technical analysis indicator library."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_df(closes: list[float], n: int = 0) -> pd.DataFrame:
    """Build minimal OHLCV DataFrame from close prices."""
    if not closes:
        closes = list(range(100, 100 + n))
    n = len(closes)
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def test_sma_basic():
    from ta_indicators import sma
    series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    result = sma(series, period=5)
    assert result.iloc[-1] == 30.0
    assert pd.isna(result.iloc[0])


def test_sma_constant_series():
    from ta_indicators import sma
    series = pd.Series([42.0] * 20)
    result = sma(series, period=10)
    assert result.iloc[-1] == 42.0


def test_ema_responds_faster_than_sma():
    from ta_indicators import sma, ema
    prices = pd.Series([10.0] * 19 + [20.0])
    sma_val = sma(prices, period=10).iloc[-1]
    ema_val = ema(prices, period=10).iloc[-1]
    assert ema_val > sma_val


def test_rsi_constant_series_is_50():
    from ta_indicators import rsi
    df = _make_df([100.0] * 30)
    result = rsi(df, period=14)
    valid = result.dropna()
    if len(valid) > 0:
        assert abs(valid.iloc[-1] - 50.0) < 5.0


def test_rsi_all_gains_near_100():
    from ta_indicators import rsi
    df = _make_df([float(i) for i in range(100, 130)])
    result = rsi(df, period=14)
    assert result.iloc[-1] > 90.0


def test_rsi_all_losses_near_0():
    from ta_indicators import rsi
    df = _make_df([float(i) for i in range(130, 100, -1)])
    result = rsi(df, period=14)
    assert result.iloc[-1] < 10.0
