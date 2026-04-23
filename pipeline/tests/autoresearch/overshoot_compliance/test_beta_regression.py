import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import beta_regression as BR


def _series(values, dates):
    return pd.Series(values, index=pd.to_datetime(dates))


def test_zero_beta_when_strategy_uncorrelated_with_nifty():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=252)
    nifty_rets = pd.Series(rng.normal(0.0005, 0.01, size=252), index=dates)
    strat_rets = pd.Series(rng.normal(0.001, 0.01, size=252), index=dates)
    res = BR.regress_on_nifty(strat_rets, nifty_rets)
    assert abs(res["beta"]) < 0.2


def test_unit_beta_when_strategy_equals_nifty():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(1)
    nifty_rets = pd.Series(rng.normal(0.0, 0.01, size=252), index=dates)
    res = BR.regress_on_nifty(nifty_rets, nifty_rets)
    assert abs(res["beta"] - 1.0) < 1e-6
    assert res["r_squared"] > 0.99


def test_residual_sharpe_returned():
    dates = pd.bdate_range("2024-01-01", periods=252)
    rng = np.random.default_rng(2)
    nifty_rets = pd.Series(rng.normal(0.0, 0.01, size=252), index=dates)
    alpha_component = pd.Series(rng.normal(0.001, 0.005, size=252), index=dates)
    strat_rets = 0.5 * nifty_rets + alpha_component
    res = BR.regress_on_nifty(strat_rets, nifty_rets)
    assert "residual_sharpe" in res
    assert res["residual_sharpe"] > 0.0


def test_alignment_by_date_only():
    nifty = _series([0.01, 0.02, -0.01, 0.005], ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    strat = _series([0.02, -0.01], ["2024-01-02", "2024-01-04"])
    res = BR.regress_on_nifty(strat, nifty)
    assert res["n_aligned"] == 2
