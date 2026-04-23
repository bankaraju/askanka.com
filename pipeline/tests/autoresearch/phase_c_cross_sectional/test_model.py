import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.model import (
    fit_lasso, predict, serialize, load, compute_epsilon,
    purged_walk_forward_splits,
)


def _synthetic_regression(n=200, n_features=10, seed=1):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.standard_normal((n, n_features)),
                     columns=[f"f{i}" for i in range(n_features)])
    # true signal only on f0
    y = pd.Series(2.0 * X["f0"].values + 0.1 * rng.standard_normal(n),
                  name="y")
    return X, y


def test_fit_lasso_runs_and_returns_bundle():
    X, y = _synthetic_regression()
    alpha_grid = np.logspace(-5, 0, 6)
    bundle = fit_lasso(
        X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42,
    )
    assert set(bundle.keys()) >= {"model", "standardizer", "alpha", "coef_", "intercept_"}
    assert bundle["coef_"].shape[0] == X.shape[1]


def test_predict_roundtrip():
    X, y = _synthetic_regression()
    alpha_grid = np.logspace(-5, 0, 6)
    bundle = fit_lasso(X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42)
    yhat = predict(bundle, X)
    # On training set, Lasso should be ~correlated with y
    assert np.corrcoef(yhat, y)[0, 1] > 0.5


def test_compute_epsilon_is_half_median_abs():
    train_preds = np.array([-2.0, -1.0, 0.5, 1.0, 3.0])
    # |preds| = 2,1,0.5,1,3 -> median = 1.0 -> eps = 0.5
    assert compute_epsilon(train_preds) == pytest.approx(0.5)


def test_serialize_roundtrip(tmp_path):
    X, y = _synthetic_regression(n=50, n_features=5)
    alpha_grid = np.logspace(-5, 0, 4)
    bundle = fit_lasso(X, y, alpha_grid=alpha_grid, cv_splits=4, embargo_days=2, seed=42)
    pth = tmp_path / "model.pkl"
    serialize(bundle, pth)
    b2 = load(pth)
    np.testing.assert_allclose(b2["coef_"], bundle["coef_"])
    np.testing.assert_allclose(predict(b2, X), predict(bundle, X))


def test_purged_walk_forward_embargo():
    # 100 training dates; 4 folds; embargo 2 days
    splits = purged_walk_forward_splits(n=100, n_splits=4, embargo=2)
    assert len(splits) == 4
    for train_idx, val_idx in splits:
        # no training index should be within embargo of any validation index
        for v in val_idx:
            assert not any(abs(t - v) <= 2 for t in train_idx)
