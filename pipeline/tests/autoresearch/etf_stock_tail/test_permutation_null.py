import numpy as np

from pipeline.autoresearch.etf_stock_tail.permutation_null import (
    cross_entropy,
    label_permutation_null,
)


def test_cross_entropy_matches_manual():
    probs = np.array([[0.7, 0.2, 0.1], [0.1, 0.6, 0.3]])
    labels = np.array([0, 1])
    ce = cross_entropy(probs, labels)
    expected = -(np.log(0.7) + np.log(0.6)) / 2
    assert abs(ce - expected) < 1e-9


def test_permutation_null_p_value_in_unit_interval():
    rng = np.random.default_rng(0)
    n = 200
    probs = rng.dirichlet(np.ones(3), size=n)
    labels = rng.integers(0, 3, size=n)
    res = label_permutation_null(probs, labels, n_permutations=200, seed=42)
    assert 0.0 <= res["p_value"] <= 1.0
    assert "obs_ce" in res
    assert "perm_ce_quantile_0p01" in res


def test_permutation_null_p_low_when_probs_match_labels():
    """If probs perfectly predict labels, observed CE should be near 0 and below all permutations."""
    n = 500
    rng = np.random.default_rng(7)
    labels = rng.integers(0, 3, size=n)
    probs = np.zeros((n, 3))
    probs[np.arange(n), labels] = 0.95
    probs[probs == 0] = 0.025
    res = label_permutation_null(probs, labels, n_permutations=300, seed=42)
    assert res["p_value"] < 0.01
