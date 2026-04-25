import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.peer_residuals import (
    compute_log_returns,
    compute_residual_panel,
)


@pytest.fixture
def synthetic_panel():
    dates = pd.date_range("2025-01-01", periods=10, freq="B")
    # RELIANCE rises by +2%/day, TCS by +1%/day, INFY by +1%/day, HDFCBANK by +3%/day
    prices = pd.DataFrame({
        "RELIANCE": np.cumprod(np.full(10, 1.02)) * 1000,
        "TCS":      np.cumprod(np.full(10, 1.01)) * 3000,
        "INFY":     np.cumprod(np.full(10, 1.01)) * 1500,
        "HDFCBANK": np.cumprod(np.full(10, 1.03)) * 1500,
    }, index=dates)
    return prices


def test_compute_log_returns_first_row_is_nan(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    assert rets.iloc[0].isna().all()
    np.testing.assert_allclose(rets.iloc[1], np.log([1.02, 1.01, 1.01, 1.03]))


def test_residual_is_stock_minus_mean_of_peers(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {
        "RELIANCE": ["TCS", "INFY"],
        "TCS":      ["INFY", "HDFCBANK"],
        "INFY":     ["TCS", "HDFCBANK"],
        "HDFCBANK": ["TCS", "INFY"],
    }
    panel = compute_residual_panel(rets, peers_map)
    # RELIANCE return = log(1.02). Peers mean = log(1.01). Residual = log(1.02)-log(1.01).
    expected_rel = np.log(1.02) - np.log(1.01)
    np.testing.assert_allclose(panel.loc[rets.index[1], "RELIANCE"], expected_rel, rtol=1e-9)


def test_residual_panel_skips_symbol_when_no_peers_have_data(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {"RELIANCE": ["NONEXISTENT"]}
    panel = compute_residual_panel(rets, peers_map)
    assert panel["RELIANCE"].isna().all()


def test_residual_panel_uses_available_peers_when_some_missing(synthetic_panel):
    rets = compute_log_returns(synthetic_panel)
    peers_map = {"RELIANCE": ["TCS", "NONEXISTENT"]}
    panel = compute_residual_panel(rets, peers_map)
    expected = np.log(1.02) - np.log(1.01)
    np.testing.assert_allclose(panel.loc[rets.index[1], "RELIANCE"], expected, rtol=1e-9)
