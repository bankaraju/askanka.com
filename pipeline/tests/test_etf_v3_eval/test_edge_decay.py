# pipeline/tests/test_etf_v3_eval/test_edge_decay.py
import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.edge_decay import (
    rolling_12mo_sharpe,
    cusum_regime_change,
)


def test_rolling_12mo_sharpe_returns_per_period_value():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(0.001, 0.01, 300),
                  index=pd.date_range("2024-01-01", periods=300))
    out = rolling_12mo_sharpe(s, window=252)
    assert out.iloc[-1] is not None
    assert not np.isnan(out.iloc[-1])


def test_cusum_detects_known_break():
    """A clean shift from mean=0.005 to mean=-0.005 is detected by CUSUM."""
    s = pd.Series(np.r_[np.full(100, 0.005), np.full(100, -0.005)],
                  index=pd.date_range("2024-01-01", periods=200))
    triggers = cusum_regime_change(s, threshold=3.0)
    assert any(t > 100 for t in triggers)


def test_rolling_sharpe_empty_returns_empty():
    out = rolling_12mo_sharpe(pd.Series([], dtype=float))
    assert len(out) == 0


def test_cusum_with_in_sample_mean_target():
    """If target_mean is set to the in-sample mean, deviations from that mean
    (not from zero) are detected — useful for testing 'edge decay' against
    a known prior."""
    s = pd.Series(np.r_[np.full(100, 0.01), np.full(100, 0.001)])  # decay from 1bp to 0.1bp
    triggers_zero = cusum_regime_change(s, threshold=3.0, target_mean=0.0)
    triggers_prior = cusum_regime_change(s, threshold=3.0, target_mean=0.01)
    # Both should detect the decay; trigger indices may differ
    assert len(triggers_prior) > 0


def test_cusum_empty_returns_empty():
    out = cusum_regime_change(pd.Series([], dtype=float))
    assert out == []
