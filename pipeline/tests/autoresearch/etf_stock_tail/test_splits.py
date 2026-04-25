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
