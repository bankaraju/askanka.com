# pipeline/tests/autoresearch/etf_stock_tail/test_splits.py
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.splits import (
    InsufficientRegimeCoverage,
    check_regime_coverage,
    split_panel,
)


def test_split_partitions_by_date():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2020-05-01", "2025-01-15", "2025-06-15", "2026-04-01"]),
        "label": [0, 1, 2, 0],
    })
    train, val, holdout = split_panel(df)
    assert len(train) == 1 and train["date"].iloc[0] == pd.Timestamp("2020-05-01")
    assert len(val) == 1 and val["date"].iloc[0] == pd.Timestamp("2025-01-15")
    assert len(holdout) == 2


def test_regime_coverage_passes_when_all_regimes_present():
    # Fix: use modular cycling so len(regimes) == len(days) regardless of date-range length
    days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    base = (["DEEP_PAIN"] * 50 + ["PAIN"] * 50 + ["NEUTRAL"] * 50
            + ["EUPHORIA"] * 50 + ["MEGA_EUPHORIA"] * 50)
    regimes = [base[i % len(base)] for i in range(len(days))]
    df = pd.DataFrame({"date": days, "regime": regimes})
    check_regime_coverage(df)  # should not raise


def test_regime_coverage_raises_when_missing():
    days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    df = pd.DataFrame({"date": days, "regime": ["NEUTRAL"] * len(days)})
    with pytest.raises(InsufficientRegimeCoverage):
        check_regime_coverage(df)


def test_regime_coverage_train_aware_passes_when_holdout_covers_material_regimes():
    """Per Amendment A1.5 — material regimes are derived from train, not hardcoded."""
    train_days = pd.date_range("2022-01-01", periods=400, freq="D")
    train_regimes = (["CAUTION"] * 100 + ["NEUTRAL"] * 100
                     + ["RISK-ON"] * 100 + ["EUPHORIA"] * 50 + ["RISK-OFF"] * 50)
    train = pd.DataFrame({"date": train_days, "regime": train_regimes})

    holdout_days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    base = ["CAUTION"] * 30 + ["NEUTRAL"] * 30 + ["RISK-ON"] * 30 + ["EUPHORIA"] * 30 + ["RISK-OFF"] * 30
    holdout_regimes = [base[i % len(base)] for i in range(len(holdout_days))]
    holdout = pd.DataFrame({"date": holdout_days, "regime": holdout_regimes})

    check_regime_coverage(holdout, train=train)  # should not raise


def test_regime_coverage_train_aware_raises_when_holdout_lacks_material_regime():
    train_days = pd.date_range("2022-01-01", periods=400, freq="D")
    train = pd.DataFrame({"date": train_days, "regime": ["RISK-OFF"] * 400})

    holdout_days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    holdout = pd.DataFrame({"date": holdout_days, "regime": ["RISK-ON"] * len(holdout_days)})

    with pytest.raises(InsufficientRegimeCoverage):
        check_regime_coverage(holdout, train=train)


def test_regime_coverage_ignores_unknown_sentinel():
    """UNKNOWN regime must be excluded — it's a sentinel, not a real regime."""
    train_days = pd.date_range("2022-01-01", periods=400, freq="D")
    train = pd.DataFrame({"date": train_days, "regime": ["UNKNOWN"] * 400})

    holdout_days = pd.date_range(C.HOLDOUT_START, C.HOLDOUT_END, freq="D")
    holdout = pd.DataFrame({"date": holdout_days, "regime": ["UNKNOWN"] * len(holdout_days)})

    # No material train regimes (UNKNOWN excluded), but the fallback fires
    # because there are no >=3 material regimes with >=MIN days in holdout either.
    with pytest.raises(InsufficientRegimeCoverage):
        check_regime_coverage(holdout, train=train)
