"""Feature-vector builder for TA Coincidence Scorer v1. Point-in-time features
computed from OHLCV up to `as_of` (inclusive). Uses pipeline.ta_scorer.patterns
for candlestick flags.
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd

from pipeline.ta_scorer import patterns


_REGIME_VALUES = ("RISK_OFF", "NEUTRAL", "RISK_ON", "EUPHORIA", "CRISIS")
_MIN_HISTORY = 200  # 200DMA requires 200 rows


def _slice_up_to(df: pd.DataFrame, as_of: str) -> pd.DataFrame:
    return df[df["date"] <= as_of].copy()


def _rsi(closes: pd.Series, window: int = 14) -> float:
    if len(closes) < window + 1:
        return 50.0
    delta = closes.diff()
    up = delta.clip(lower=0).rolling(window).mean().iloc[-1]
    down = (-delta.clip(upper=0)).rolling(window).mean().iloc[-1]
    rs = up / max(1e-9, down)
    return float(100 - 100 / (1 + rs))


def _macd_hist(closes: pd.Series) -> tuple[float, float]:
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    if len(hist) < 2:
        return 0.0, 0.0
    return float(hist.iloc[-1]), float(hist.iloc[-1] - hist.iloc[-2])


def _atr(df: pd.DataFrame, window: int = 20) -> float:
    if len(df) < window + 1:
        return 0.0
    tr = np.maximum.reduce([
        (df["high"] - df["low"]).values,
        (df["high"] - df["close"].shift(1)).abs().values,
        (df["low"] - df["close"].shift(1)).abs().values,
    ])
    return float(pd.Series(tr).rolling(window).mean().iloc[-1])


def build_feature_vector(*, prices: pd.DataFrame, sector: pd.DataFrame,
                          nifty: pd.DataFrame, as_of: str, regime: str,
                          sector_breadth: float) -> Optional[dict]:
    prices = _slice_up_to(prices, as_of).sort_values("date").reset_index(drop=True)
    if len(prices) < _MIN_HISTORY:
        return None
    sector = _slice_up_to(sector, as_of).sort_values("date").reset_index(drop=True)
    nifty = _slice_up_to(nifty, as_of).sort_values("date").reset_index(drop=True)

    row = prices.iloc[-1].to_dict()
    prev = prices.iloc[-2].to_dict()

    close = float(row["close"])
    closes = prices["close"]

    ma20 = closes.rolling(20).mean().iloc[-1]
    ma50 = closes.rolling(50).mean().iloc[-1]
    ma200 = closes.rolling(200).mean().iloc[-1]
    bb_std = closes.rolling(20).std().iloc[-1]
    upper_bb = ma20 + 2 * bb_std
    lower_bb = ma20 - 2 * bb_std
    bb_pos_raw = (close - lower_bb) / max(1e-9, upper_bb - lower_bb)

    rsi = _rsi(closes, 14)
    macd_hist, macd_slope = _macd_hist(closes)
    atr = _atr(prices, 20)

    vol_rel20 = float(row["volume"]) / max(1e-9, prices["volume"].tail(20).mean())

    sector_closes = sector["close"]
    sector_ret_5d = float(np.log(sector_closes.iloc[-1] / sector_closes.iloc[-6])) if len(sector_closes) >= 6 else 0.0
    sector_ma20 = sector_closes.rolling(20).mean().iloc[-1] if len(sector_closes) >= 20 else sector_closes.iloc[-1]
    sector_ma50 = sector_closes.rolling(50).mean().iloc[-1] if len(sector_closes) >= 50 else sector_closes.iloc[-1]
    sector_trend = 1 if sector_ma20 > sector_ma50 else 0

    nifty_closes = nifty["close"]
    nifty_ret_5d = float(np.log(nifty_closes.iloc[-1] / nifty_closes.iloc[-6])) if len(nifty_closes) >= 6 else 0.0

    vec: dict = {
        "doji_flag": 1 if patterns.is_doji(row) else 0,
        "hammer_flag": 1 if patterns.is_hammer(row) else 0,
        "shooting_star_flag": 1 if patterns.is_shooting_star(row) else 0,
        "bullish_engulfing_flag": 1 if patterns.is_bullish_engulfing(prev, row) else 0,
        "bearish_engulfing_flag": 1 if patterns.is_bearish_engulfing(prev, row) else 0,
        "dist_20dma_pct": (close - ma20) / close,
        "dist_50dma_pct": (close - ma50) / close,
        "dist_200dma_pct": (close - ma200) / close,
        "bb_pos": float(np.clip(bb_pos_raw, -0.5, 1.5)),
        "rsi14": rsi,
        "rsi_oversold": 1 if rsi < 30 else 0,
        "rsi_neutral": 1 if 30 <= rsi <= 70 else 0,
        "rsi_overbought": 1 if rsi > 70 else 0,
        "ret_3d": float(np.log(closes.iloc[-1] / closes.iloc[-4])) if len(closes) >= 4 else 0.0,
        "ret_10d": float(np.log(closes.iloc[-1] / closes.iloc[-11])) if len(closes) >= 11 else 0.0,
        "macd_hist": macd_hist,
        "macd_hist_slope": macd_slope,
        "atr20_pct": atr / close,
        "range_pct": (float(row["high"]) - float(row["low"])) / close,
        "vol_rel20": vol_rel20,
        "vol_spike_flag": 1 if vol_rel20 >= 1.5 else 0,
        "sector_ret_5d": sector_ret_5d,
        "sector_trend_flag": sector_trend,
        "sector_breadth_estimate": float(sector_breadth),
        "nifty_ret_5d": nifty_ret_5d,
    }
    for r in _REGIME_VALUES:
        vec[f"regime_{r}"] = 1 if regime == r else 0
    return vec
