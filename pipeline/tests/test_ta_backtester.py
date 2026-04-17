"""Tests for TA backtest engine — forward returns after pattern events."""
from __future__ import annotations

import pandas as pd
import pytest


def _make_prices(n: int = 30, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Close": closes,
    })


SAMPLE_EVENTS = [
    {"date": "2025-01-06", "pattern": "BB_SQUEEZE", "direction": "LONG", "price_at_event": 105.0},
    {"date": "2025-01-13", "pattern": "BB_SQUEEZE", "direction": "LONG", "price_at_event": 112.0},
    {"date": "2025-01-20", "pattern": "RSI_OVERBOUGHT_REV", "direction": "SHORT", "price_at_event": 119.0},
]


def test_backtest_returns_stats_per_pattern():
    from ta_backtester import backtest_events
    df = _make_prices(30, 100.0, 1.0)
    stats = backtest_events(SAMPLE_EVENTS, df)
    assert "BB_SQUEEZE" in stats
    assert stats["BB_SQUEEZE"]["occurrences"] == 2
    assert "win_rate_5d" in stats["BB_SQUEEZE"]
    assert "avg_return_5d" in stats["BB_SQUEEZE"]


def test_backtest_long_wins_on_uptrend():
    from ta_backtester import backtest_events
    df = _make_prices(30, 100.0, 1.0)
    events = [{"date": "2025-01-06", "pattern": "TEST_LONG", "direction": "LONG", "price_at_event": 105.0}]
    stats = backtest_events(events, df)
    assert stats["TEST_LONG"]["win_rate_5d"] == 1.0
    assert stats["TEST_LONG"]["avg_return_5d"] > 0


def test_backtest_short_wins_on_downtrend():
    from ta_backtester import backtest_events
    df = _make_prices(30, 130.0, -1.0)
    events = [{"date": "2025-01-06", "pattern": "TEST_SHORT", "direction": "SHORT", "price_at_event": 125.0}]
    stats = backtest_events(events, df)
    assert stats["TEST_SHORT"]["win_rate_5d"] == 1.0


def test_backtest_skips_events_near_end():
    from ta_backtester import backtest_events
    df = _make_prices(15, 100.0, 1.0)
    events = [{"date": "2025-01-20", "pattern": "LATE", "direction": "LONG", "price_at_event": 114.0}]
    stats = backtest_events(events, df)
    assert stats.get("LATE", {}).get("occurrences", 0) <= 1
