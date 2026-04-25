# pipeline/tests/autoresearch/etf_stock_tail/test_etf_features.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_stock_tail import constants as C
from pipeline.autoresearch.etf_stock_tail.etf_features import (
    build_etf_features_matrix,
    etf_feature_names,
)


@pytest.fixture
def synthetic_etf_panel() -> pd.DataFrame:
    """30-day synthetic ETF panel, 30 ETFs, monotonic close = (ETF_idx + 1) * day."""
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    rows = []
    for i, sym in enumerate(C.ETF_SYMBOLS):
        for d in dates:
            day = (d - dates[0]).days + 1
            rows.append({"date": d, "etf": sym, "close": float((i + 1) * day)})
    return pd.DataFrame(rows)


def test_feature_names_are_30x3():
    names = etf_feature_names()
    assert len(names) == 90
    assert all(n.startswith("etf_") for n in names)
    # Each ETF appears 3 times (one per window)
    for sym in C.ETF_SYMBOLS:
        assert sum(sym in n for n in names) == 3


def test_features_are_strictly_causal(synthetic_etf_panel):
    """Feature for eval_date t MUST use only rows with date < t."""
    eval_date = pd.Timestamp("2024-01-25")
    feats_with = build_etf_features_matrix(synthetic_etf_panel, eval_date)

    # Mutate the row at t — features must be unchanged.
    panel_mut = synthetic_etf_panel.copy()
    panel_mut.loc[panel_mut["date"] == eval_date, "close"] = 99999.0
    feats_with_mut = build_etf_features_matrix(panel_mut, eval_date)

    pd.testing.assert_series_equal(feats_with, feats_with_mut)


def test_returns_match_known_values(synthetic_etf_panel):
    """For monotonic close = (i+1)*day, ret_1d at day d = (d - (d-1)) / (d-1) = 1/(d-1)."""
    eval_date = pd.Timestamp("2024-01-25")  # day 25 → ret_1d uses day 24 vs 23
    feats = build_etf_features_matrix(synthetic_etf_panel, eval_date)
    # brazil = ETF idx 1, so close at day 23 = 2*23 = 46, day 24 = 2*24 = 48
    expected_ret_1d = (48 - 46) / 46
    assert feats["etf_brazil_ret_1d"] == pytest.approx(expected_ret_1d)


def test_missing_etf_returns_nan(synthetic_etf_panel):
    """Drop one ETF entirely; its features should be NaN, others unaffected."""
    panel_partial = synthetic_etf_panel[synthetic_etf_panel["etf"] != "natgas"]
    eval_date = pd.Timestamp("2024-01-25")
    feats = build_etf_features_matrix(panel_partial, eval_date)
    assert np.isnan(feats["etf_natgas_ret_1d"])
    assert not np.isnan(feats["etf_brazil_ret_1d"])
