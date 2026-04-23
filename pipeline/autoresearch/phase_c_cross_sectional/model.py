"""Lasso model fit/predict/serialize for H-2026-04-24-003.

Binding spec notes:
  - Alpha selected on MEAN OOS SHARPE across 4 purged walk-forward CV folds,
    not R^2. Sharpe on each fold is computed over validation-set predictions
    treated as a signed return (sign(pred) * y_val), annualised at 252.
  - Feature standardization fit on training only; standardizer travels with
    the bundle.
  - Refit on full training set after alpha selection (no CV held-out).
  - epsilon = 0.5 * median(|training_predictions|), frozen on training set.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler


def purged_walk_forward_splits(n: int, n_splits: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Chronological fold boundaries with +/- embargo days of training purged
    around each validation window. Returns (train_idx, val_idx) lists.
    """
    fold_size = n // n_splits
    splits = []
    for k in range(n_splits):
        val_lo = k * fold_size
        val_hi = (k + 1) * fold_size if k < n_splits - 1 else n
        val_idx = list(range(val_lo, val_hi))
        train_idx = [
            i for i in range(n)
            if (i < val_lo - embargo) or (i >= val_hi + embargo)
        ]
        splits.append((train_idx, val_idx))
    return splits


def _sharpe_of_signed(preds: np.ndarray, y: np.ndarray, ann_factor: int = 252) -> float:
    signed = np.sign(preds) * y
    signed = signed[~np.isnan(signed)]
    if signed.size < 2 or signed.std(ddof=1) == 0:
        return 0.0
    return float(signed.mean() / signed.std(ddof=1) * np.sqrt(ann_factor))


def fit_lasso(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    alpha_grid: np.ndarray,
    cv_splits: int,
    embargo_days: int,
    seed: int,
) -> dict:
    """Fit Lasso with alpha chosen to maximise mean OOS Sharpe over purged CV folds."""
    X = X_train.to_numpy(dtype=float)
    y = y_train.to_numpy(dtype=float)
    n = X.shape[0]
    splits = purged_walk_forward_splits(n, cv_splits, embargo_days)

    alpha_mean_sharpes = []
    for alpha in alpha_grid:
        fold_sharpes = []
        for train_idx, val_idx in splits:
            X_tr = X[train_idx]
            y_tr = y[train_idx]
            X_va = X[val_idx]
            y_va = y[val_idx]
            scaler = StandardScaler().fit(X_tr)
            model = Lasso(alpha=alpha, max_iter=50_000, random_state=seed)
            model.fit(scaler.transform(X_tr), y_tr)
            preds = model.predict(scaler.transform(X_va))
            fold_sharpes.append(_sharpe_of_signed(preds, y_va))
        alpha_mean_sharpes.append(float(np.mean(fold_sharpes)))

    best_idx = int(np.argmax(alpha_mean_sharpes))
    best_alpha = float(alpha_grid[best_idx])

    standardizer = StandardScaler().fit(X)
    final = Lasso(alpha=best_alpha, max_iter=50_000, random_state=seed)
    final.fit(standardizer.transform(X), y)

    return {
        "model": final,
        "standardizer": standardizer,
        "alpha": best_alpha,
        "alpha_grid": alpha_grid.tolist(),
        "alpha_mean_sharpes": alpha_mean_sharpes,
        "coef_": final.coef_,
        "intercept_": float(final.intercept_),
        "feature_names": list(X_train.columns),
    }


def predict(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """Apply standardizer then model, return predictions in percent-return units."""
    arr = X.to_numpy(dtype=float)
    return bundle["model"].predict(bundle["standardizer"].transform(arr))


def compute_epsilon(training_predictions: np.ndarray) -> float:
    """Frozen trading-rule threshold: 0.5 * median(|training_predictions|)."""
    return float(0.5 * np.median(np.abs(training_predictions)))


def serialize(bundle: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(bundle, fh)
    return path


def load(path: Path) -> dict:
    with open(path, "rb") as fh:
        return pickle.load(fh)
