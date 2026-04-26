from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.replay_extender import (
    aggregate_minute_to_event_returns,
)


def test_aggregate_minute_to_event_returns_emits_per_event_row(tmp_path):
    """For each (ticker, trade_date) in minute parquet, emit one event row with
    open_to_1430 return and open_to_close return."""
    df = pd.DataFrame({
        "ticker":["A"]*4,
        "trade_date":[date(2026,3,3)]*4,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 09:45",
            "2026-03-03 14:30", "2026-03-03 15:30",
        ]).tz_localize("Asia/Kolkata"),
        "open":[100.0,101.0,103.0,104.0],
        "high":[101.0,102.0,104.0,105.0],
        "low":[99.0,100.0,102.0,103.0],
        "close":[101.0,102.0,104.0,105.0],
        "volume":[1000]*4,
    })
    out = aggregate_minute_to_event_returns(df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["ticker"] == "A"
    assert row["trade_date"] == date(2026,3,3)
    assert row["open_to_1430_pct"] == pytest.approx((104.0 - 100.0)/100.0)
    assert row["open_to_close_pct"] == pytest.approx((105.0 - 100.0)/100.0)


def test_aggregate_missing_1430_bar_falls_back_and_flags_imputed():
    """If no 14:30 bar exists for a (ticker, date), TIME_STOP falls back to last
    close AND time_stop_imputed must be True so downstream can mark/filter."""
    df = pd.DataFrame({
        "ticker": ["A"]*2,
        "trade_date": [date(2026, 3, 3)]*2,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 13:00",
        ]).tz_localize("Asia/Kolkata"),
        "open": [100.0, 102.0],
        "high": [101.0, 103.0],
        "low": [99.0, 101.0],
        "close": [101.0, 103.0],
        "volume": [1000]*2,
    })
    out = aggregate_minute_to_event_returns(df)
    row = out.iloc[0]
    assert row["time_stop_imputed"] is True or row["time_stop_imputed"] == True  # noqa
    assert row["time_stop_px"] == 103.0  # fell back to last close
    assert row["open_to_1430_pct"] == row["open_to_close_pct"]


def test_aggregate_real_1430_bar_marks_imputed_false():
    """When a real 14:30 bar exists, time_stop_imputed must be False."""
    df = pd.DataFrame({
        "ticker": ["A"]*3,
        "trade_date": [date(2026, 3, 3)]*3,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 14:30", "2026-03-03 15:30",
        ]).tz_localize("Asia/Kolkata"),
        "open": [100.0, 103.0, 104.0],
        "high": [101.0, 104.0, 105.0],
        "low": [99.0, 102.0, 103.0],
        "close": [101.0, 104.0, 105.0],
        "volume": [1000]*3,
    })
    out = aggregate_minute_to_event_returns(df)
    assert out.iloc[0]["time_stop_imputed"] == False  # noqa


def test_aggregate_skips_zero_open_row(caplog):
    """Zero open_px would explode division; the row must be skipped with a warning,
    not abort the whole aggregation."""
    df = pd.DataFrame({
        "ticker": ["A", "B"]*1,
        "trade_date": [date(2026, 3, 3)]*2,
        "timestamp": pd.to_datetime([
            "2026-03-03 09:15", "2026-03-03 09:15",
        ]).tz_localize("Asia/Kolkata"),
        "open": [0.0, 100.0],
        "high": [0.0, 101.0],
        "low": [0.0, 99.0],
        "close": [0.0, 101.0],
        "volume": [0, 1000],
    })
    with caplog.at_level("WARNING"):
        out = aggregate_minute_to_event_returns(df)
    assert len(out) == 1  # only B survives
    assert out.iloc[0]["ticker"] == "B"
    assert any("Skipping zero-open" in r.message for r in caplog.records)
