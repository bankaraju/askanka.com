import numpy as np
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.stats.permutation_null import (
    permutation_test_mean,
)


def test_permutation_null_detects_real_signal():
    np.random.seed(0)
    pos = np.random.normal(loc=0.005, scale=0.01, size=200)
    neg = np.random.normal(loc=-0.005, scale=0.01, size=200)
    obs = pos.mean() - neg.mean()
    rng = np.random.default_rng(0)
    p = permutation_test_mean(pos, neg, n_permutations=2000, rng=rng)
    assert p < 0.01


def test_permutation_null_no_signal_returns_p_near_05():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.01, 200)
    b = rng.normal(0, 0.01, 200)
    p = permutation_test_mean(a, b, n_permutations=2000, rng=np.random.default_rng(1))
    assert 0.2 < p < 0.8


def test_permutation_null_accepts_python_list_input():
    """Function signature says ndarray but Python doesn't enforce it; lists must work."""
    pos = [0.01] * 50 + [-0.01] * 50  # mean = 0
    neg = [0.005] * 50 + [-0.005] * 50  # mean = 0
    rng = np.random.default_rng(42)
    p = permutation_test_mean(pos, neg, n_permutations=200, rng=rng)
    assert 0.0 < p <= 1.0  # any valid p-value, just confirm no AttributeError
