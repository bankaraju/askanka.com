# pipeline/tests/autoresearch/etf_stock_tail/test_calibration.py
import numpy as np
import pytest

from pipeline.autoresearch.etf_stock_tail.calibration import (
    PlattScaler,
    brier_decomposition,
    reliability_bins,
)


def test_platt_improves_calibration_on_skewed_logits():
    rng = np.random.default_rng(0)
    n = 2000
    # Synthesize logits that are 2× too sharp
    true_probs = rng.dirichlet(np.ones(3), size=n)
    sharp_logits = np.log(true_probs + 1e-9) * 2.0  # over-confident
    labels = np.array([rng.choice(3, p=p) for p in true_probs])
    sharp_probs = np.exp(sharp_logits) / np.exp(sharp_logits).sum(axis=1, keepdims=True)

    scaler = PlattScaler().fit(sharp_logits, labels)
    cal_probs = scaler.transform(sharp_logits)

    eps = 1e-12
    sharp_ce = -np.mean(np.log(sharp_probs[np.arange(n), labels] + eps))
    cal_ce = -np.mean(np.log(cal_probs[np.arange(n), labels] + eps))
    assert cal_ce < sharp_ce


def test_brier_decomp_sums_to_total():
    rng = np.random.default_rng(1)
    n = 500
    probs = rng.dirichlet(np.ones(3), size=n)
    labels = rng.integers(0, 3, size=n)
    decomp = brier_decomposition(probs, labels, n_bins=10)
    total = decomp["total"]
    rec = decomp["reliability"] - decomp["resolution"] + decomp["uncertainty"]
    assert abs(total - rec) < 1e-3


def test_reliability_bins_returns_n_bins_per_class():
    probs = np.array([[0.1, 0.8, 0.1], [0.4, 0.5, 0.1], [0.05, 0.05, 0.9]])
    labels = np.array([1, 0, 2])
    bins = reliability_bins(probs, labels, n_bins=10)
    assert "down_tail" in bins and "neutral" in bins and "up_tail" in bins
    assert len(bins["down_tail"]) == 10
