"""Feature compute + shape classify TDD."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_shape_audit import features


def _make_bars(prices: list[float], start: datetime | None = None) -> pd.DataFrame:
    """Build a minute-bar DF where each bar has open=close=prev close,
    high=close*1.001, low=close*0.999, volume=1000."""
    if start is None:
        start = datetime(2026, 4, 22, 9, 15)
    rows = []
    prev = prices[0]
    for i, p in enumerate(prices):
        rows.append({
            "timestamp_ist": start + pd.Timedelta(minutes=i),
            "open": prev,
            "high": max(prev, p) * 1.001,
            "low": min(prev, p) * 0.999,
            "close": p,
            "volume": 1000,
        })
        prev = p
    return pd.DataFrame(rows)


def test_compute_features_returns_bars_insufficient_for_short_session() -> None:
    short_bars = _make_bars([100.0] * 100)  # only 100 bars, need >= 350
    feats = features.compute_shape_features(short_bars)
    assert feats["validation"] == "BARS_INSUFFICIENT"


def test_classify_reverse_v_high() -> None:
    """Open at 100, peak at minute 5 (102), drift down to close at 100.5.
    peak_pct = 2%, close_pct = 0.5%, close_pct <= peak_pct/2 = 1.0 -> REVERSE_V_HIGH."""
    prices = [100.0] * 5 + [102.0] + [101.5] * 100 + [101.0] * 100 + [100.7] * 100 + [100.5] * 70
    bars = _make_bars(prices)
    feats = features.compute_shape_features(bars)
    assert feats["validation"] == "OK"
    assert feats["peak_in_first_15min"] is True
    assert feats["peak_pct"] == pytest.approx(2.0, abs=0.05)
    assert feats["close_pct"] == pytest.approx(0.5, abs=0.05)
    assert features.classify_shape(feats) == "REVERSE_V_HIGH"


def test_classify_v_low_recovery() -> None:
    """Open at 100, trough at minute 5 (98), drift up to close at 99.5.
    trough_pct = -2%, close_pct = -0.5%, close_pct >= trough_pct/2 = -1.0 -> V_LOW_RECOVERY."""
    prices = [100.0] * 5 + [98.0] + [98.5] * 100 + [99.0] * 100 + [99.3] * 100 + [99.5] * 70
    bars = _make_bars(prices)
    feats = features.compute_shape_features(bars)
    assert features.classify_shape(feats) == "V_LOW_RECOVERY"
