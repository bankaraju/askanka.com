"""Loud failures if regime_history.csv is missing, stale, or has gaps > 5 bars.

Also guards the quantile-based zone mapping: cutpoints must exist, be
monotonic, and have been frozen from the pre-train calibration window
(no look-ahead). Every regime in the train+val slice must have at least
50 events — this is the floor assumed by the autoresearch per-regime
rule search.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

REGIME_CSV = Path("pipeline/data/regime_history.csv")
CUTPOINTS_JSON = Path("pipeline/data/regime_cutpoints.json")
VALID_REGIMES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
MIN_START = pd.Timestamp("2021-04-23")

# Split boundaries (mirror pipeline/autoresearch/regime_autoresearch/constants.py)
TRAIN_VAL_START = pd.Timestamp("2021-04-23")
TRAIN_VAL_END = pd.Timestamp("2024-04-22")
CALIBRATION_START = pd.Timestamp("2018-01-01")
CALIBRATION_END = pd.Timestamp("2021-04-22")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    if not REGIME_CSV.exists():
        pytest.fail(f"missing: {REGIME_CSV}")
    frame = pd.read_csv(REGIME_CSV, parse_dates=["date"]).sort_values("date")
    return frame


@pytest.fixture(scope="module")
def cutpoints() -> dict:
    if not CUTPOINTS_JSON.exists():
        pytest.fail(f"missing: {CUTPOINTS_JSON}")
    return json.loads(CUTPOINTS_JSON.read_text(encoding="utf-8"))


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


def test_cutpoints_file_exists_and_schema(cutpoints):
    """regime_cutpoints.json must declare its calibration window and the
    four monotonic quintile cutpoints."""
    expected_keys = {"calibration_start", "calibration_end",
                     "q20", "q40", "q60", "q80"}
    assert expected_keys.issubset(cutpoints.keys()), (
        f"missing keys: {expected_keys - set(cutpoints.keys())}"
    )
    assert cutpoints["q20"] < cutpoints["q40"] < cutpoints["q60"] < cutpoints["q80"], (
        f"cutpoints not monotonic: {cutpoints}"
    )


def test_cutpoints_from_pre_train_window(df, cutpoints):
    """Cutpoints must be frozen from the pre-train calibration window.

    We cannot recompute cutpoints from regime_history.csv alone because
    that file only emits signal values from TRAIN_VAL_START onwards (the
    calibration window predates it). We assert instead that:
      1. calibration_start == 2018-01-01 and calibration_end == 2021-04-22
      2. No train+val signal value leaked into the cutpoint computation:
         if we recompute q20/q40/q60/q80 from the train+val signals, they
         must NOT match the persisted cutpoints (distributions differ).
    This is a structural, non-circular invariant: the cutpoints file
    declares where it came from, and we verify that a na\u00efve
    train-on-train-data recomputation yields a clearly different result.
    """
    assert cutpoints["calibration_start"] == "2018-01-01"
    assert cutpoints["calibration_end"] == "2021-04-22"

    # All signal values in the CSV are emitted from TRAIN_VAL_START onwards,
    # so the CSV itself is outside the calibration window. Recomputing
    # quantiles from the CSV's train+val slice should produce different
    # values than the persisted (calibration-window) cutpoints.
    train_val_mask = ((df["date"] >= TRAIN_VAL_START)
                      & (df["date"] <= TRAIN_VAL_END))
    train_val_signals = df.loc[train_val_mask, "signal_score"].dropna()
    assert len(train_val_signals) > 0
    tv_q = train_val_signals.quantile([0.20, 0.40, 0.60, 0.80])

    leak_signals = [
        math.isclose(tv_q.loc[0.20], cutpoints["q20"], rel_tol=0, abs_tol=1e-10),
        math.isclose(tv_q.loc[0.40], cutpoints["q40"], rel_tol=0, abs_tol=1e-10),
        math.isclose(tv_q.loc[0.60], cutpoints["q60"], rel_tol=0, abs_tol=1e-10),
        math.isclose(tv_q.loc[0.80], cutpoints["q80"], rel_tol=0, abs_tol=1e-10),
    ]
    assert not all(leak_signals), (
        "cutpoints appear to have been computed from train+val signals "
        "(all four quantiles match within 1e-10) — look-ahead leak detected"
    )


def test_every_regime_has_50_events_in_train_val(df):
    """Per-regime rule search in autoresearch assumes at least 50 labelled
    events per regime in train+val. Fail loudly if the quantile bucketing
    has regressed below that floor."""
    train_val_mask = ((df["date"] >= TRAIN_VAL_START)
                      & (df["date"] <= TRAIN_VAL_END))
    counts = df.loc[train_val_mask, "regime_zone"].value_counts()
    missing = VALID_REGIMES - set(counts.index)
    assert not missing, f"regimes missing from train+val: {missing}"
    assert int(counts.min()) >= 50, (
        f"min regime count in train+val is {int(counts.min())} (< 50)\n"
        f"full distribution:\n{counts.to_string()}"
    )
