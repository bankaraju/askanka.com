"""Tests for pattern event detector."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _trending_up_df(n: int = 60) -> pd.DataFrame:
    closes = [100.0 + (i * 100.0 / n) for i in range(n)]
    return pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=n, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 2.0 for c in closes],
        "Low": [c - 2.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def _with_dma200_crossover(n: int = 250) -> pd.DataFrame:
    closes = [100.0 - (i * 0.1) for i in range(230)]
    closes += [closes[-1] + (i * 1.5) for i in range(1, n - 230 + 1)]
    closes = closes[:n]
    return pd.DataFrame({
        "Date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "Open": [c - 0.3 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    })


def test_detect_events_returns_list():
    from ta_pattern_detector import detect_all_events
    df = _trending_up_df(60)
    events = detect_all_events(df)
    assert isinstance(events, list)
    if events:
        assert "date" in events[0]
        assert "pattern" in events[0]
        assert "direction" in events[0]


def test_rsi_overbought_detected_in_strong_uptrend():
    from ta_pattern_detector import detect_all_events
    closes = [100.0 + i * 3.0 for i in range(30)] + [190.0 - i * 2.0 for i in range(10)]
    df = pd.DataFrame({
        "Date": pd.date_range("2025-01-01", periods=40, freq="B"),
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [1000000] * 40,
    })
    events = detect_all_events(df)
    patterns = {e["pattern"] for e in events}
    assert "RSI_OVERBOUGHT_REV" in patterns or "MACD_CROSS_DN" in patterns


def test_dma200_crossover_detected():
    from ta_pattern_detector import detect_all_events
    df = _with_dma200_crossover(250)
    events = detect_all_events(df)
    patterns = {e["pattern"] for e in events}
    assert "DMA200_CROSS_UP" in patterns


def test_events_have_required_fields():
    from ta_pattern_detector import detect_all_events
    df = _with_dma200_crossover(250)
    events = detect_all_events(df)
    for e in events:
        assert "date" in e
        assert "pattern" in e
        assert "direction" in e
        assert "price_at_event" in e
        assert e["direction"] in ("LONG", "SHORT", "NEUTRAL")
