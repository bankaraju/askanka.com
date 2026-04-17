"""
Pattern Event Detector — scans indicator output for 15 actionable pattern types.

Takes an OHLCV DataFrame, computes all indicators, returns a list of event dicts.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from ta_indicators import sma, ema, bollinger, macd, rsi, atr, volume_spike, detect_candles

PATTERN_DIRECTION = {
    "BB_SQUEEZE": "LONG", "BB_BREAKOUT_UP": "LONG", "BB_BREAKOUT_DN": "SHORT",
    "DMA200_CROSS_UP": "LONG", "DMA200_CROSS_DN": "SHORT",
    "MACD_CROSS_UP": "LONG", "MACD_CROSS_DN": "SHORT",
    "RSI_OVERSOLD_BOUNCE": "LONG", "RSI_OVERBOUGHT_REV": "SHORT",
    "VOL_BREAKOUT": "LONG",
    "ATR_COMPRESSION": "NEUTRAL",
    "CANDLE_HAMMER": "LONG", "CANDLE_ENGULF_BULL": "LONG",
    "CANDLE_ENGULF_BEAR": "SHORT", "CANDLE_DOJI": "NEUTRAL",
}


def _crosses_above(series: pd.Series, level: pd.Series) -> pd.Series:
    return (series > level) & (series.shift(1) <= level.shift(1))


def _crosses_below(series: pd.Series, level: pd.Series) -> pd.Series:
    return (series < level) & (series.shift(1) >= level.shift(1))


def detect_all_events(df: pd.DataFrame) -> list[dict]:
    """Detect all 15 pattern types in an OHLCV DataFrame."""
    if len(df) < 20:
        return []

    close = df["Close"].astype(float)
    dates = df["Date"]
    events: list[dict] = []

    def _add(mask: pd.Series, pattern: str):
        for i in range(len(mask)):
            if mask.iloc[i]:
                date_val = dates.iloc[i]
                date_str = str(date_val) if isinstance(date_val, str) else date_val.strftime("%Y-%m-%d")
                events.append({
                    "date": date_str,
                    "pattern": pattern,
                    "direction": PATTERN_DIRECTION[pattern],
                    "price_at_event": float(close.iloc[i]),
                })

    # Bollinger Bands
    bb = bollinger(df)
    vol = volume_spike(df)
    bb_bw = bb["bandwidth"]
    bb_bw_min20 = bb_bw.rolling(20, min_periods=20).min()
    squeeze = (bb_bw <= bb_bw_min20.shift(1)) & (bb_bw > bb_bw.shift(1))
    _add(squeeze, "BB_SQUEEZE")
    _add((close > bb["upper"]) & vol, "BB_BREAKOUT_UP")
    _add((close < bb["lower"]) & vol, "BB_BREAKOUT_DN")

    # 200 EMA crossover
    ema200 = ema(close, 200)
    _add(_crosses_above(close, ema200), "DMA200_CROSS_UP")
    _add(_crosses_below(close, ema200), "DMA200_CROSS_DN")

    # MACD
    m = macd(df)
    _add(_crosses_above(m["macd_line"], m["signal_line"]), "MACD_CROSS_UP")
    _add(_crosses_below(m["macd_line"], m["signal_line"]), "MACD_CROSS_DN")

    # RSI
    r = rsi(df)
    _add(_crosses_above(r, pd.Series(30.0, index=r.index)), "RSI_OVERSOLD_BOUNCE")
    _add(_crosses_below(r, pd.Series(70.0, index=r.index)), "RSI_OVERBOUGHT_REV")

    # Volume breakout
    high_20 = close.rolling(20, min_periods=20).max().shift(1)
    _add(vol & (close > high_20), "VOL_BREAKOUT")

    # ATR compression
    a = atr(df)
    a_sma50 = sma(a, 50)
    _add(a < 0.5 * a_sma50, "ATR_COMPRESSION")

    # Candlesticks
    candles = detect_candles(df)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    near_ma = ((close - sma20).abs() / close < 0.02) | ((close - sma50).abs() / close < 0.02)
    _add(candles["hammer"] & near_ma, "CANDLE_HAMMER")

    prev_red_3 = (close.shift(1) < df["Open"].astype(float).shift(1)) & \
                 (close.shift(2) < df["Open"].astype(float).shift(2)) & \
                 (close.shift(3) < df["Open"].astype(float).shift(3))
    prev_green_3 = (close.shift(1) > df["Open"].astype(float).shift(1)) & \
                   (close.shift(2) > df["Open"].astype(float).shift(2)) & \
                   (close.shift(3) > df["Open"].astype(float).shift(3))
    _add(candles["engulfing_bull"] & prev_red_3, "CANDLE_ENGULF_BULL")
    _add(candles["engulfing_bear"] & prev_green_3, "CANDLE_ENGULF_BEAR")

    high_20d = close.rolling(20, min_periods=20).max()
    low_20d = close.rolling(20, min_periods=20).min()
    near_extreme = ((close - high_20d).abs() / close < 0.01) | ((close - low_20d).abs() / close < 0.01)
    _add(candles["doji"] & near_extreme, "CANDLE_DOJI")

    return sorted(events, key=lambda e: e["date"])
