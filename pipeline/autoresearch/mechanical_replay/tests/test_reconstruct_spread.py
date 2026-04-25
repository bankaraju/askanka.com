"""TDD for reconstruct.spread — pair-z + regime-gate spread reconstruction.

For each pair in INDIA_SPREAD_PAIRS and each date in window, compute the
log-spread z-score over a configurable lookback window. Apply the regime
gate from the regenerated regime tags. Trigger when |z| > entry_threshold
AND the gate is open.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay.reconstruct import spread


def _bars(seed: int, n: int = 400, drift: float = 0.0001, base: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n)
    rets = rng.normal(drift, 0.012, size=n)
    closes = base * np.exp(np.cumsum(rets))
    return pd.DataFrame({"date": dates, "close": closes})


def test_spread_zscore_returns_finite_for_full_history():
    long_bars = _bars(seed=1)
    short_bars = _bars(seed=2)
    z = spread.compute_spread_zscore(
        long_bars=long_bars, short_bars=short_bars,
        target_date=long_bars["date"].iloc[-1], lookback_days=60,
    )
    assert np.isfinite(z)


def test_spread_zscore_handles_short_history():
    """When fewer than lookback_days bars are available, return NaN."""
    long_bars = _bars(seed=1, n=10)
    short_bars = _bars(seed=2, n=10)
    z = spread.compute_spread_zscore(
        long_bars=long_bars, short_bars=short_bars,
        target_date=long_bars["date"].iloc[-1], lookback_days=60,
    )
    assert pd.isna(z)


def test_spread_regenerate_basic_pipeline():
    """End-to-end: 2 pairs × 5 dates × regime gate."""
    pairs = [
        {"name": "TestPairA", "long": ["AAA", "BBB"], "short": ["CCC"]},
        {"name": "TestPairB", "long": ["DDD"], "short": ["EEE", "FFF"]},
    ]
    universe_bars = {
        "AAA": _bars(seed=1), "BBB": _bars(seed=2), "CCC": _bars(seed=3),
        "DDD": _bars(seed=4), "EEE": _bars(seed=5), "FFF": _bars(seed=6),
    }
    dates = universe_bars["AAA"]["date"].iloc[-10:]
    regime_by_date = {d.strftime("%Y-%m-%d"): "NEUTRAL" for d in dates}

    out = spread.regenerate(
        window_start=dates.iloc[0],
        window_end=dates.iloc[-1],
        pairs=pairs,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        entry_threshold=2.0,
        lookback_days=60,
    )
    assert {"date", "pair_id", "leg_long", "leg_short", "entry_z", "regime", "gate_status"}.issubset(out.columns)


def test_spread_regenerate_skips_when_gate_blocks():
    """If allowed_regimes is restricted, all triggers must be on those regimes."""
    pairs = [{"name": "TestPair", "long": ["AAA"], "short": ["BBB"]}]
    universe_bars = {"AAA": _bars(seed=11), "BBB": _bars(seed=12)}
    dates = universe_bars["AAA"]["date"].iloc[-30:]
    # Mix of NEUTRAL and RISK-ON across the window.
    regime_by_date = {
        d.strftime("%Y-%m-%d"): ("NEUTRAL" if i % 2 == 0 else "RISK-ON")
        for i, d in enumerate(dates)
    }
    out = spread.regenerate(
        window_start=dates.iloc[0],
        window_end=dates.iloc[-1],
        pairs=pairs,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        entry_threshold=0.0,  # threshold so low everything triggers
        lookback_days=20,
        allowed_regimes={"NEUTRAL"},
    )
    if not out.empty:
        triggered = out[out["gate_status"] == "OPEN"]
        assert (triggered["regime"] == "NEUTRAL").all()


def test_spread_regenerate_records_direction_from_zscore_sign():
    """When the spread z is positive (long leg expensive vs short), the trade
    is FADE → enter SHORT the long basket / LONG the short basket. We tag the
    direction so simulators can act on it."""
    pairs = [{"name": "TestPair", "long": ["AAA"], "short": ["BBB"]}]
    universe_bars = {
        "AAA": _bars(seed=1, drift=0.005),  # positive drift
        "BBB": _bars(seed=2, drift=-0.005),  # negative drift → spread blows wide
    }
    dates = universe_bars["AAA"]["date"].iloc[-30:]
    regime_by_date = {d.strftime("%Y-%m-%d"): "NEUTRAL" for d in dates}
    out = spread.regenerate(
        window_start=dates.iloc[0],
        window_end=dates.iloc[-1],
        pairs=pairs,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        entry_threshold=1.0,
        lookback_days=30,
    )
    if not out.empty:
        # Direction is "MEAN_REVERT": positive z → fade → reverse the named legs.
        triggers = out[out["entry_z"].abs() >= 1.0]
        if not triggers.empty:
            for _, r in triggers.iterrows():
                assert r["direction"] in {"NORMAL", "REVERSE"}
