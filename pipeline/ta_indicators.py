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


def bollinger(df: pd.DataFrame, period: int = 20, std: int = 2) -> pd.DataFrame:
    """Bollinger Bands: upper, middle, lower, bandwidth, pct_b."""
    close = df["Close"]
    middle = sma(close, period)
    rolling_std = close.rolling(window=period, min_periods=period).std()
    upper = middle + std * rolling_std
    lower = middle - std * rolling_std
    bandwidth = (upper - lower) / middle
    pct_b = (close - lower) / (upper - lower)
    return pd.DataFrame({
        "upper": upper, "middle": middle, "lower": lower,
        "bandwidth": bandwidth, "pct_b": pct_b,
    }, index=df.index)


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD: macd_line, signal_line, histogram."""
    close = df["Close"]
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd_line": macd_line, "signal_line": signal_line, "histogram": histogram,
    }, index=df.index)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def volume_spike(df: pd.DataFrame, lookback: int = 20, threshold: float = 2.0) -> pd.Series:
    """Detect volume spikes: volume > threshold × lookback-period average."""
    vol = df["Volume"].astype(float)
    avg_vol = vol.rolling(window=lookback, min_periods=lookback).mean().shift(1)
    return vol > (threshold * avg_vol)


def detect_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Detect candlestick patterns: doji, hammer, shooting_star, engulfing_bull, engulfing_bear."""
    o, h, l, c = df["Open"].astype(float), df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
    body = (c - o).abs()
    full_range = h - l
    upper_shadow = h - pd.concat([o, c], axis=1).max(axis=1)
    lower_shadow = pd.concat([o, c], axis=1).min(axis=1) - l

    doji = (full_range > 0) & (body / full_range < 0.1)

    hammer = (lower_shadow >= 2 * body) & (upper_shadow <= body.clip(lower=0.01)) & (full_range > 0)

    shooting_star = (upper_shadow >= 2 * body) & (lower_shadow <= body.clip(lower=0.01)) & (full_range > 0)

    prev_o, prev_c = o.shift(1), c.shift(1)
    today_green = c > o
    prev_red = prev_c < prev_o
    engulfing_bull = today_green & prev_red & (o <= prev_c) & (c >= prev_o)

    today_red = c < o
    prev_green = prev_c > prev_o
    engulfing_bear = today_red & prev_green & (o >= prev_c) & (c <= prev_o)

    return pd.DataFrame({
        "doji": doji, "hammer": hammer, "shooting_star": shooting_star,
        "engulfing_bull": engulfing_bull, "engulfing_bear": engulfing_bear,
    }, index=df.index)
