"""Tests for §13 cross-source reconciliation."""
from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.cross_source_reconciliation import (
    aggregate_minute_to_daily,
    compare_to_eod,
    ReconciliationFailure,
    MAX_DELTA_PCT,
)


def _minute_session(close_path: list[float]) -> pd.DataFrame:
    """Build a session of `len(close_path)` minutes; close prices follow the path."""
    rows = []
    for i, close in enumerate(close_path):
        ts = pd.Timestamp.combine(date(2026, 4, 23), time(9, 15)).tz_localize("Asia/Kolkata") + pd.Timedelta(minutes=i)
        rows.append({
            "ticker": "RELIANCE", "trade_date": date(2026, 4, 23), "timestamp": ts,
            "open": close, "high": close, "low": close, "close": close, "volume": 100,
        })
    return pd.DataFrame(rows)


def test_aggregate_yields_daily_ohlc() -> None:
    minute_df = _minute_session([100.0, 105.0, 95.0, 102.0])
    daily = aggregate_minute_to_daily(minute_df)
    assert len(daily) == 1
    row = daily.iloc[0]
    assert row["open"] == 100.0
    assert row["high"] == 105.0
    assert row["low"] == 95.0
    assert row["close"] == 102.0


def test_compare_passes_when_within_threshold() -> None:
    minute_df = _minute_session([100.0, 100.0, 100.0, 100.0])
    eod_df = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "close": [100.2],
    })
    report = compare_to_eod(minute_df, eod_df)
    assert report["max_delta_pct"] < MAX_DELTA_PCT


def test_compare_raises_when_above_threshold() -> None:
    minute_df = _minute_session([100.0])
    eod_df = pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "close": [105.0],  # 5% delta — way over 0.5%
    })
    with pytest.raises(ReconciliationFailure, match="exceeds"):
        compare_to_eod(minute_df, eod_df, raise_on_failure=True)
