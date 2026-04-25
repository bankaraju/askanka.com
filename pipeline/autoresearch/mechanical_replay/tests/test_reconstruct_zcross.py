"""TDD for reconstruct.zcross — per-minute peer-residual Z_CROSS exit time.

For each Phase C trade, walk the minute bars from 09:30 onward and find the
minute when the peer-relative z-score crosses zero (sign change from entry
sign). Returns the minute timestamp or None if no cross occurred before
hard close.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay.reconstruct import zcross


def _minute_bars(start_str: str, n: int, prices: list[float]) -> pd.DataFrame:
    times = pd.date_range(start_str, periods=n, freq="1min")
    return pd.DataFrame({
        "datetime": times, "open": prices, "high": prices,
        "low": prices, "close": prices, "volume": 1000,
    })


def test_zcross_returns_first_crossing_minute():
    """If sector flat and stock starts +z then crosses to -z, return the
    minute when sign flipped."""
    n = 60
    sector = _minute_bars("2026-04-20 09:30", n, [100.0] * n)
    # Stock starts at 102 (positive z), drifts to 99 (negative z).
    closes = list(np.linspace(102.0, 99.0, n))
    stock = _minute_bars("2026-04-20 09:30", n, closes)
    cross = zcross.find_zcross_minute(
        stock_minute_bars=stock,
        sector_minute_bars=sector,
        entry_sign=+1,
        rolling_window=20,
    )
    assert cross is not None
    # Crossing should land somewhere in the second half.
    assert cross > pd.Timestamp("2026-04-20 09:45")


def test_zcross_returns_none_when_no_cross():
    """When stock stays on the same side of sector mean, no cross."""
    n = 60
    sector = _minute_bars("2026-04-20 09:30", n, [100.0] * n)
    stock = _minute_bars("2026-04-20 09:30", n, [102.0] * n)
    cross = zcross.find_zcross_minute(
        stock_minute_bars=stock,
        sector_minute_bars=sector,
        entry_sign=+1,
        rolling_window=20,
    )
    assert cross is None


def test_zcross_handles_negative_entry_sign():
    """Mirror case: stock starts below sector mean (negative z), drifts up."""
    n = 60
    sector = _minute_bars("2026-04-20 09:30", n, [100.0] * n)
    closes = list(np.linspace(98.0, 101.0, n))
    stock = _minute_bars("2026-04-20 09:30", n, closes)
    cross = zcross.find_zcross_minute(
        stock_minute_bars=stock,
        sector_minute_bars=sector,
        entry_sign=-1,
        rolling_window=20,
    )
    assert cross is not None


def test_zcross_returns_none_when_too_few_bars():
    n = 5
    sector = _minute_bars("2026-04-20 09:30", n, [100.0] * n)
    stock = _minute_bars("2026-04-20 09:30", n, [101.0] * n)
    cross = zcross.find_zcross_minute(
        stock_minute_bars=stock,
        sector_minute_bars=sector,
        entry_sign=+1,
        rolling_window=20,
    )
    assert cross is None
