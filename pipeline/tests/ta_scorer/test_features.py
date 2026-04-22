import pandas as pd
import numpy as np
import pytest
from pipeline.ta_scorer import features


def _synthetic_prices(n=260):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Gently rising with noise
    close = 100.0 + np.linspace(0, 20, n) + np.random.default_rng(42).normal(0, 1, n)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1_000_000,
    })


def _synthetic_sector(n=260):
    df = _synthetic_prices(n)
    df["close"] = df["close"] * 0.5 + 500
    return df


def test_vector_has_all_v1_keys():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    nifty = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=nifty,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.6,
    )
    expected = {
        "doji_flag", "hammer_flag", "shooting_star_flag",
        "bullish_engulfing_flag", "bearish_engulfing_flag",
        "dist_20dma_pct", "dist_50dma_pct", "dist_200dma_pct", "bb_pos",
        "rsi14", "rsi_oversold", "rsi_neutral", "rsi_overbought",
        "ret_3d", "ret_10d", "macd_hist", "macd_hist_slope",
        "atr20_pct", "range_pct",
        "vol_rel20", "vol_spike_flag",
        "sector_ret_5d", "sector_trend_flag", "sector_breadth_estimate",
        "nifty_ret_5d",
        "regime_RISK_OFF", "regime_NEUTRAL", "regime_RISK_ON",
        "regime_EUPHORIA", "regime_CRISIS",
    }
    assert expected.issubset(set(vec.keys()))


def test_regime_one_hots_sum_to_one():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    total = (vec["regime_RISK_OFF"] + vec["regime_NEUTRAL"] +
             vec["regime_RISK_ON"] + vec["regime_EUPHORIA"] + vec["regime_CRISIS"])
    assert total == 1


def test_rsi_buckets_mutually_exclusive():
    prices = _synthetic_prices()
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert vec["rsi_oversold"] + vec["rsi_neutral"] + vec["rsi_overbought"] == 1


def test_vol_spike_triggers_at_1_5x():
    prices = _synthetic_prices()
    # Amplify last volume
    prices.loc[prices.index[-1], "volume"] = 5_000_000  # 5x average
    sector = _synthetic_sector()
    vec = features.build_feature_vector(
        prices=prices, sector=sector, nifty=sector,
        as_of=prices["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert vec["vol_spike_flag"] == 1
    assert vec["vol_rel20"] >= 1.5


def test_insufficient_history_returns_none():
    # Less than 200 rows → 200DMA unavailable
    short = _synthetic_prices(n=50)
    sector = _synthetic_sector()
    res = features.build_feature_vector(
        prices=short, sector=sector, nifty=sector,
        as_of=short["date"].iloc[-1], regime="NEUTRAL",
        sector_breadth=0.5,
    )
    assert res is None
