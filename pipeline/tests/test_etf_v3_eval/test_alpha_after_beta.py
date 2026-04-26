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
