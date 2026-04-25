"""TDD for atr — 14-day ATR + intraday-capped percent stop, mirroring live intent."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import atr, canonical_loader, constants as C


@pytest.fixture(scope="module")
def loader():
    return canonical_loader.CanonicalLoader()


def _synth_bars(n: int = 30, base: float = 100.0, daily_range: float = 1.0) -> pd.DataFrame:
    """Predictable bars: each day has high=close+0.5, low=close-0.5 → TR ≈ 1.0."""
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    closes = np.full(n, base)
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes + daily_range / 2,
        "low": closes - daily_range / 2,
        "close": closes,
        "volume": [1_000_000] * n,
    })


def test_true_range_synthetic_constant():
    df = _synth_bars(n=30, base=100, daily_range=2.0)
    # TR for synthetic constant-range bars = high-low (no gap) = 2.0
    tr = atr._true_range(df)
    # First bar's TR is NaN (no prev_close). Subsequent should equal 2.0.
    assert pd.isna(tr.iloc[0]) or tr.iloc[0] == 2.0
    assert (tr.iloc[1:] == 2.0).all()


def test_atr_simple_mean():
    df = _synth_bars(n=30, base=100, daily_range=2.0)
    a = atr._atr(df, window=14)
    # 14-day SMA of TR=2.0 is 2.0
    assert a == pytest.approx(2.0)


def test_stop_pct_intraday_long_below_cap():
    # daily_range=2 on close=100 → ATR=2 → 1× ATR = 2% stop, below 3.5% cap
    df = _synth_bars(n=30, base=100, daily_range=2.0)
    res = atr.compute_stop(df, side="LONG", profile="intraday")
    assert res["atr_14"] == pytest.approx(2.0)
    assert res["stop_pct"] == pytest.approx(-2.0)
    assert res["stop_source"] == "atr_14_intraday"


def test_stop_pct_intraday_capped_when_atr_huge():
    # daily_range=10 on close=100 → ATR=10 → 1× ATR = 10% stop → capped at 3.5%
    df = _synth_bars(n=30, base=100, daily_range=10.0)
    res = atr.compute_stop(df, side="LONG", profile="intraday")
    assert res["atr_14"] == pytest.approx(10.0)
    assert res["stop_pct"] == pytest.approx(-3.5)
    assert res["stop_source"] == "atr_14_intraday_capped"


def test_stop_pct_short_intraday_uncapped():
    df = _synth_bars(n=30, base=100, daily_range=2.0)
    res = atr.compute_stop(df, side="SHORT", profile="intraday")
    # SHORT stop_pct is also negative (loss when price rises)
    assert res["stop_pct"] == pytest.approx(-2.0)


def test_stop_fallback_on_insufficient_bars():
    df = _synth_bars(n=10)  # < 15 bars → not enough for ATR_14
    res = atr.compute_stop(df, side="LONG", profile="intraday")
    assert res["stop_pct"] == C.ATR_FALLBACK_PCT
    assert res["stop_source"] == "fallback"


def test_stop_real_canonical_ticker_returns_negative_pct(loader):
    df = loader.daily_bars("ABB")
    cutoff = pd.Timestamp("2026-04-22").normalize()
    df_pre = df[df["date"] <= cutoff]
    res = atr.compute_stop(df_pre, side="LONG", profile="intraday")
    assert res["stop_source"].startswith("atr_14_intraday")
    assert res["stop_pct"] < 0
    assert res["stop_pct"] >= -C.ATR_MAX_ABS_PCT
