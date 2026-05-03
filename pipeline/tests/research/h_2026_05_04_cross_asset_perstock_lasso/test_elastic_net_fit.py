import numpy as np
import pandas as pd
import pytest
from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.elastic_net_fit import (
    exp_decay_weights,
    fit_en_cell,
    score_en_cell,
)


def test_exp_decay_weights_sum_to_one_and_recent_heavy():
    n = 500
    w = exp_decay_weights(n_obs=n, hl_trading_days=90)
    assert w.shape == (n,)
    assert w.sum() == pytest.approx(1.0, rel=1e-9)
    # Most recent observation has highest weight
    assert w[-1] > w[0]
    # Half-life property: weight 90 obs back is half of weight at last
    assert w[-91] / w[-1] == pytest.approx(0.5, rel=1e-3)


def test_fit_en_cell_returns_predictions_in_zero_one():
    rng = np.random.default_rng(0)
    n, p = 400, 23
    X = rng.normal(0, 1, (n, p))
    # Synthetic signal: feature 0 weakly predicts label
    y = (X[:, 0] + rng.normal(0, 1, n) > 0).astype(int)
    model, cv_meta = fit_en_cell(
        X_train=X,
        y_train=y,
        sample_weights=exp_decay_weights(n, hl_trading_days=90),
        C_grid=(0.1, 1.0, 3.0),
        l1_ratio_grid=(0.3, 0.5, 0.7),
        cv_n_splits=3,
        random_state=0,
    )
    p_hat = score_en_cell(model, X)
    assert p_hat.shape == (n,)
    assert (p_hat >= 0).all() and (p_hat <= 1).all()
    # CV metadata recorded
    assert "best_C" in cv_meta and "best_l1_ratio" in cv_meta and "cv_mean_auc" in cv_meta


def test_fit_en_cell_aborts_on_single_class():
    X = np.zeros((50, 5))
    y = np.zeros(50, dtype=int)
    with pytest.raises(ValueError, match="single-class"):
        fit_en_cell(
            X_train=X, y_train=y,
            sample_weights=exp_decay_weights(50, 90),
            C_grid=(1.0,), l1_ratio_grid=(0.5,), cv_n_splits=3, random_state=0,
        )
