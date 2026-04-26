"""Tests for §8 schema contract validator."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.schema_validator import (
    SchemaViolation,
    validate_minute_bars_schema,
)


def _good_df() -> pd.DataFrame:
    ts = pd.Timestamp("2026-04-23 09:15:00", tz="Asia/Kolkata")
    return pd.DataFrame({
        "ticker": ["RELIANCE"],
        "trade_date": [date(2026, 4, 23)],
        "timestamp": [ts],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [1000],
    })


def test_validate_passes_on_good_dataframe() -> None:
    validate_minute_bars_schema(_good_df())  # should not raise


def test_validate_rejects_missing_column() -> None:
    df = _good_df().drop(columns=["volume"])
    with pytest.raises(SchemaViolation, match="missing columns"):
        validate_minute_bars_schema(df)


def test_validate_rejects_non_positive_price() -> None:
    df = _good_df()
    df["open"] = -1.0
    with pytest.raises(SchemaViolation, match="non-positive"):
        validate_minute_bars_schema(df)


def test_validate_rejects_high_below_low() -> None:
    df = _good_df()
    df.loc[0, "high"] = 50.0
    df.loc[0, "low"] = 100.0
    with pytest.raises(SchemaViolation, match="high < low"):
        validate_minute_bars_schema(df)


def test_validate_rejects_negative_volume() -> None:
    df = _good_df()
    df["volume"] = -1
    with pytest.raises(SchemaViolation, match="negative volume"):
        validate_minute_bars_schema(df)
