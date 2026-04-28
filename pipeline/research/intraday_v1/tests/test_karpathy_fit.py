"""Tests karpathy_fit.py — random search + robust-Sharpe objective."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import karpathy_fit


def _synthetic_in_sample(n_days: int = 30, n_inst: int = 10, seed: int = 0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_days):
        for i in range(n_inst):
            features = rng.normal(0, 1, 6)
            label = float(np.dot(features, [0.5, -0.3, 0.2, 0.1, 0.0, 0.4])) + rng.normal(0, 0.5)
            rows.append({
                "date": f"2026-03-{1+d:02d}",
                "instrument": f"INST{i}",
                "f1": features[0], "f2": features[1], "f3": features[2],
                "f4": features[3], "f5": features[4], "f6": features[5],
                "next_return_pct": label,
            })
    return pd.DataFrame(rows)


def test_objective_robust_sharpe_returns_finite():
    df = _synthetic_in_sample()
    weights = np.array([0.5, -0.3, 0.2, 0.1, 0.0, 0.4])
    j = karpathy_fit.objective(weights, df)
    assert np.isfinite(j)


def test_random_search_reproducible_with_seed():
    df = _synthetic_in_sample()
    fit_a = karpathy_fit.run(df, seed=42, n_iters=50)
    fit_b = karpathy_fit.run(df, seed=42, n_iters=50)
    assert np.allclose(fit_a["weights"], fit_b["weights"])
    assert fit_a["objective"] == fit_b["objective"]


def test_different_seed_produces_different_weights():
    df = _synthetic_in_sample()
    fit_a = karpathy_fit.run(df, seed=1, n_iters=50)
    fit_b = karpathy_fit.run(df, seed=2, n_iters=50)
    assert not np.allclose(fit_a["weights"], fit_b["weights"])


def test_run_returns_thresholds():
    df = _synthetic_in_sample()
    fit = karpathy_fit.run(df, seed=42, n_iters=50)
    assert "long_threshold" in fit
    assert "short_threshold" in fit
    assert fit["long_threshold"] > fit["short_threshold"]


def test_run_emits_weight_vector_in_bounds():
    df = _synthetic_in_sample()
    fit = karpathy_fit.run(df, seed=42, n_iters=50)
    assert all(-2.0 <= w <= 2.0 for w in fit["weights"])
