import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.alpha_after_beta import (
    regress_against_benchmark,
)


def test_pure_benchmark_returns_zero_alpha_high_beta():
    rng = np.random.default_rng(0)
    nifty = rng.normal(0, 0.01, 500)
    strategy = nifty * 1.5
    out = regress_against_benchmark(strategy, nifty)
    assert out["alpha_annualized"] == pytest.approx(0.0, abs=1e-3)
    assert out["beta"] == pytest.approx(1.5, rel=1e-3)
    assert out["r_squared"] > 0.99


def test_residual_sharpe_independent_of_market():
    rng = np.random.default_rng(0)
    nifty = rng.normal(0, 0.01, 500)
    alpha_signal = rng.normal(0.001, 0.005, 500)
    strategy = 0.4 * nifty + alpha_signal
    out = regress_against_benchmark(strategy, nifty)
    assert abs(out["beta"] - 0.4) < 0.05
    assert out["residual_sharpe"] != 0.0


def test_regress_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="length mismatch"):
        regress_against_benchmark([0.01, 0.02], [0.01])


def test_regress_raises_on_too_few_observations():
    with pytest.raises(ValueError, match=">= 2 observations"):
        regress_against_benchmark([0.01], [0.01])


def test_regress_handles_weekly_annualization():
    """Confirm annualization parameter scales alpha + residual sharpe correctly."""
    rng = np.random.default_rng(0)
    nifty = rng.normal(0, 0.02, 100)
    strategy = nifty * 0.5 + rng.normal(0.001, 0.01, 100)
    daily = regress_against_benchmark(strategy, nifty, annualization=252)
    weekly = regress_against_benchmark(strategy, nifty, annualization=52)
    # alpha and residual_sharpe scale linearly / sqrt'ly with annualization
    assert weekly["alpha_annualized"] == pytest.approx(daily["alpha_annualized"] * (52/252), rel=1e-9)
    assert weekly["residual_sharpe"] == pytest.approx(daily["residual_sharpe"] * np.sqrt(52/252), rel=1e-9)
    # beta and r_squared are annualization-independent
    assert weekly["beta"] == pytest.approx(daily["beta"], rel=1e-12)
    assert weekly["r_squared"] == pytest.approx(daily["r_squared"], rel=1e-12)
