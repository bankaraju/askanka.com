"""Tests for §9 cleanliness gates."""
from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.cleanliness_gates import (
    GateResult,
    run_cleanliness_gates,
    EXPECTED_MINUTES_PER_SESSION,
)


def _build_session(ticker: str, day: date, n_minutes: int) -> pd.DataFrame:
    """Build n_minutes consecutive 1-min bars starting at 09:15 IST."""
    rows = []
    for i in range(n_minutes):
        ts = pd.Timestamp.combine(day, time(9, 15)).tz_localize("Asia/Kolkata") + pd.Timedelta(minutes=i)
        rows.append({
            "ticker": ticker, "trade_date": day, "timestamp": ts,
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100,
        })
    return pd.DataFrame(rows)


def test_full_session_passes() -> None:
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION)
    result = run_cleanliness_gates(df)
    assert result.passed
    assert result.missing_pct == 0.0


def test_missing_above_threshold_fails() -> None:
    # 5% threshold = 18.75 minutes; 50 missing > threshold
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION - 50)
    result = run_cleanliness_gates(df)
    assert not result.passed
    assert "missing" in result.failures[0]


def test_after_hours_bar_fails() -> None:
    df = _build_session("RELIANCE", date(2026, 4, 23), EXPECTED_MINUTES_PER_SESSION)
    bad_ts = pd.Timestamp.combine(date(2026, 4, 23), time(16, 0)).tz_localize("Asia/Kolkata")
    bad_row = pd.DataFrame([{
        "ticker": "RELIANCE", "trade_date": date(2026, 4, 23), "timestamp": bad_ts,
        "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 100,
    }])
    df_bad = pd.concat([df, bad_row], ignore_index=True)
    result = run_cleanliness_gates(df_bad)
    assert not result.passed
    assert "after-hours" in result.failures[0]
