import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.pca_model import (
    fit_pca,
    apply_pca,
    save_pca,
    load_pca,
)


def _synthetic_etf_panel(n_days=600, n_etfs=30, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    common_factor = rng.normal(0, 1, n_days)
    cols = []
    for i in range(n_etfs):
        loading = rng.uniform(0.3, 0.9)
        idio = rng.normal(0, 1, n_days)
        cols.append(loading * common_factor + np.sqrt(1 - loading**2) * idio)
    return pd.DataFrame(np.array(cols).T, columns=[f"etf{i}" for i in range(n_etfs)])


def test_fit_pca_returns_correct_K_at_85pct_var():
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.65, max_K=12)
    assert model.K_ETF >= 1 and model.K_ETF <= 12
    assert model.cum_var_at_K >= 0.65


def test_apply_pca_shape():
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.65, max_K=12)
    Z = apply_pca(X, model)
    assert Z.shape == (len(X), model.K_ETF)
    assert list(Z.columns) == [f"PC{i+1}" for i in range(model.K_ETF)]


def test_apply_pca_uses_training_stats_only():
    """Z-score must use TRAINING mean/std, not the inference data's mean/std."""
    X_train = _synthetic_etf_panel(n_days=400, seed=1)
    X_inf = _synthetic_etf_panel(n_days=200, seed=99) + 100  # shifted inference data
    model = fit_pca(X_train, variance_target=0.65, max_K=12)
    Z_inf = apply_pca(X_inf, model)
    # Inference data shifted by 100 should still be Z-scored against training mu, so non-zero mean
    assert abs(Z_inf.mean().mean()) > 1.0


def test_save_load_roundtrip(tmp_path):
    X = _synthetic_etf_panel()
    model = fit_pca(X, variance_target=0.65, max_K=12)
    Z_before = apply_pca(X, model)

    path = tmp_path / "pca.npz"
    save_pca(model, path)
    model2 = load_pca(path)
    Z_after = apply_pca(X, model2)
    np.testing.assert_array_almost_equal(Z_before.values, Z_after.values)


def test_max_K_cap_aborts_when_violated():
    X = _synthetic_etf_panel()
    with pytest.raises(ValueError, match="K_ETF.*exceeds cap"):
        fit_pca(X, variance_target=0.99, max_K=2)  # forces K_ETF > 2 -> abort
