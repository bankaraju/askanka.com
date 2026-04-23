import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import metrics as M


def test_hit_rate_ci_brackets_point_estimate():
    wins = np.array([1, 1, 0, 1, 1, 0, 1, 0, 1, 1])  # 7/10
    lo, point, hi = M.hit_rate_ci(wins, n_resamples=5000, alpha=0.05, seed=7)
    assert lo < point < hi
    assert abs(point - 0.7) < 1e-9


def test_per_bucket_metrics_returns_all_required_fields():
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.004, scale=0.02, size=100)  # mean 0.4%/trade
    row = M.per_bucket_metrics(rets, annualisation_factor=252)
    for k in ("n_trades", "mean_ret_pct", "hit_rate",
              "hit_rate_ci_lo_95", "hit_rate_ci_hi_95",
              "sharpe", "sharpe_ci_lo_95", "sharpe_ci_hi_95",
              "max_drawdown_pct", "calmar"):
        assert k in row
    assert row["n_trades"] == 100


def test_per_bucket_metrics_handles_empty():
    row = M.per_bucket_metrics(np.array([]), annualisation_factor=252)
    assert row["n_trades"] == 0
    assert row["mean_ret_pct"] == 0.0
    assert row["sharpe"] == 0.0


def test_max_drawdown_matches_phase_c_stats():
    from pipeline.research.phase_c_backtest import stats as PC
    equity = np.array([100.0, 110.0, 90.0, 95.0, 80.0, 100.0])
    pct_returns = np.diff(equity) / equity[:-1] * 100  # percent returns
    assert M.max_drawdown_of(pct_returns) == pytest.approx(PC.max_drawdown(equity))
