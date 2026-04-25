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
