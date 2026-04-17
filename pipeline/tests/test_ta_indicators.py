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


def test_bollinger_bands_shape():
    from ta_indicators import bollinger
    df = _make_df([float(100 + i % 5) for i in range(50)])
    result = bollinger(df, period=20, std=2)
    assert "upper" in result.columns
    assert "middle" in result.columns
    assert "lower" in result.columns
    assert "bandwidth" in result.columns
    assert "pct_b" in result.columns
    assert result["upper"].iloc[-1] > result["middle"].iloc[-1] > result["lower"].iloc[-1]


def test_bollinger_constant_series_narrow_bands():
    from ta_indicators import bollinger
    df = _make_df([100.0] * 30)
    result = bollinger(df, period=20, std=2)
    assert result["bandwidth"].iloc[-1] < 0.01


def test_macd_shape():
    from ta_indicators import macd
    df = _make_df([float(100 + i * 0.5) for i in range(50)])
    result = macd(df, fast=12, slow=26, signal=9)
    assert "macd_line" in result.columns
    assert "signal_line" in result.columns
    assert "histogram" in result.columns


def test_macd_trending_up_positive():
    from ta_indicators import macd
    df = _make_df([float(100 + i * 2) for i in range(50)])
    result = macd(df, fast=12, slow=26, signal=9)
    assert result["macd_line"].iloc[-1] > 0


def test_atr_constant_range():
    from ta_indicators import atr
    import pandas as pd
    n = 30
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [100.0] * n, "High": [105.0] * n,
        "Low": [95.0] * n, "Close": [100.0] * n,
        "Volume": [1000000] * n,
    })
    result = atr(df, period=14)
    assert abs(result.iloc[-1] - 10.0) < 0.5


def test_volume_spike_detects_2x():
    from ta_indicators import volume_spike
    import pandas as pd
    volumes = [1000000] * 25 + [3000000]
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=26, freq="B"),
        "Open": [100.0] * 26, "High": [101.0] * 26,
        "Low": [99.0] * 26, "Close": [100.0] * 26,
        "Volume": volumes,
    })
    result = volume_spike(df, lookback=20, threshold=2.0)
    assert result.iloc[-1] == True
    assert result.iloc[-2] == False


def test_detect_doji():
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [100.0, 100.0, 100.0, 100.0, 100.1],
        "High":  [101.0, 102.0, 103.0, 104.0, 105.0],
        "Low":   [99.0,  98.0,  97.0,  96.0,  95.0],
        "Close": [100.0, 100.0, 100.0, 100.0, 100.0],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["doji"].iloc[-1] == True


def test_detect_bullish_engulfing():
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [105, 104, 103, 102, 98],
        "High":  [106, 105, 104, 103, 104],
        "Low":   [104, 103, 102, 97,  97],
        "Close": [104, 103, 102, 98,  103],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["engulfing_bull"].iloc[-1] == True


def test_detect_hammer():
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=5, freq="B"),
        "Open":  [105, 104, 103, 102, 100.5],
        "High":  [106, 105, 104, 103, 101.0],
        "Low":   [104, 103, 102, 101, 97.0],
        "Close": [104, 103, 102, 101, 100.0],
        "Volume": [1e6] * 5,
    })
    result = detect_candles(df)
    assert result["hammer"].iloc[-1] == True


def test_no_false_doji_on_big_body():
    from ta_indicators import detect_candles
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=3, freq="B"),
        "Open":  [100, 100, 95],
        "High":  [101, 101, 106],
        "Low":   [99,  99,  94],
        "Close": [100, 100, 105],
        "Volume": [1e6] * 3,
    })
    result = detect_candles(df)
    assert result["doji"].iloc[-1] == False
