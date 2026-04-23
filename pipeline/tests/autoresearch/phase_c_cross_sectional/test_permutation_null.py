import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.permutation_null import (
    run_label_permutation_null, single_shuffle_margin,
)


def _synth(n_train=60, n_test=20, n_features=5, seed=1):
    rng = np.random.default_rng(seed)
    X_train = pd.DataFrame(rng.standard_normal((n_train, n_features)),
                           columns=[f"f{i}" for i in range(n_features)])
    y_train = pd.Series(0.5 * X_train["f0"].values + 0.1 * rng.standard_normal(n_train))
    X_test = pd.DataFrame(rng.standard_normal((n_test, n_features)),
                          columns=[f"f{i}" for i in range(n_features)])
    y_test_gross = pd.Series(0.5 * X_test["f0"].values + 0.1 * rng.standard_normal(n_test))
    return X_train, y_train, X_test, y_test_gross


def test_single_shuffle_margin_is_scalar():
    X_train, y_train, X_test, y_test_gross = _synth()
    m = single_shuffle_margin(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, alpha=0.01, seed=42, cost_pct=0.30,
    )
    assert isinstance(m, float)


def test_run_label_permutation_null_returns_p():
    X_train, y_train, X_test, y_test_gross = _synth()
    result = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0,
        observed_margin=0.0,
        alpha=0.01, n_shuffles=100,
        seed=42, cost_pct=0.30, n_workers=1,
    )
    assert set(result.keys()) >= {"p_value", "n_shuffles_completed", "margin_samples_preview"}
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["n_shuffles_completed"] == 100


def test_permutation_null_is_deterministic_under_fixed_seed():
    X_train, y_train, X_test, y_test_gross = _synth()
    r1 = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, observed_margin=0.0,
        alpha=0.01, n_shuffles=100, seed=42, cost_pct=0.30, n_workers=1,
    )
    r2 = run_label_permutation_null(
        X_train, y_train, X_test, y_test_gross,
        strongest_naive_sharpe=0.0, observed_margin=0.0,
        alpha=0.01, n_shuffles=100, seed=42, cost_pct=0.30, n_workers=1,
    )
    assert r1["p_value"] == r2["p_value"]
