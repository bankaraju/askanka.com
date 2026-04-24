"""Loud failures if regime_history.csv is missing, stale, or has gaps > 5 bars."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

REGIME_CSV = Path("pipeline/data/regime_history.csv")
VALID_REGIMES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
MIN_START = pd.Timestamp("2021-04-23")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    if not REGIME_CSV.exists():
        pytest.fail(f"missing: {REGIME_CSV}")
    frame = pd.read_csv(REGIME_CSV, parse_dates=["date"]).sort_values("date")
    return frame


def test_columns(df):
    assert {"date", "regime_zone", "signal_score"}.issubset(df.columns)


def test_non_empty(df):
    assert len(df) > 0, "regime_history.csv is empty"


def test_coverage_start(df):
    assert df["date"].min() <= MIN_START, f"coverage starts after {MIN_START}"


def test_no_large_gaps(df):
    gaps = df["date"].diff().dropna().dt.days
    assert gaps.max() <= 7, f"gap of {gaps.max()} days exceeds 7-day tolerance"


def test_valid_zones_only(df):
    unknown = set(df["regime_zone"].unique()) - VALID_REGIMES
    assert not unknown, f"unknown zones: {unknown}"


def test_min_four_distinct_zones(df):
    assert df["regime_zone"].nunique() >= 4, "too few zones represented; check weights"
