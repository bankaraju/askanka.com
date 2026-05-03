"""Per-(stock, direction) cell EN logistic fit with exp-decay sample weights."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit


def exp_decay_weights(n_obs: int, hl_trading_days: float) -> np.ndarray:
    """Exponential-decay weights normalised to sum to 1.

    Most recent observation (index n_obs-1) gets highest weight.
    Weight at index n_obs-1-h is half the weight at n_obs-1 when h == hl_trading_days.
    """
    ages = np.arange(n_obs - 1, -1, -1, dtype=float)  # ages[-1] = 0 (most recent)
    raw = np.exp(-ages * np.log(2) / hl_trading_days)
    return raw / raw.sum()


def fit_en_cell(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    sample_weights: np.ndarray,
    C_grid: Sequence[float],
    l1_ratio_grid: Sequence[float],
    cv_n_splits: int,
    random_state: int,
) -> tuple[LogisticRegression, dict]:
    """Fit elastic-net logistic with C x l1_ratio CV using TimeSeriesSplit.

    Returns (frozen_model_refit_on_full_train, cv_meta).
    """
    if len(np.unique(y_train)) < 2:
        raise ValueError(f"single-class label, cannot fit (y_unique={np.unique(y_train)})")

    tscv = TimeSeriesSplit(n_splits=cv_n_splits)
    best = {"cv_mean_auc": -np.inf}
    for C in C_grid:
        for l1 in l1_ratio_grid:
            fold_aucs = []
            for tr_idx, va_idx in tscv.split(X_train):
                if len(np.unique(y_train[va_idx])) < 2:
                    continue
                clf = LogisticRegression(
                    penalty="elasticnet", solver="saga", l1_ratio=l1, C=C,
                    class_weight="balanced", max_iter=5000, random_state=random_state,
                )
                clf.fit(X_train[tr_idx], y_train[tr_idx], sample_weight=sample_weights[tr_idx])
                p_va = clf.predict_proba(X_train[va_idx])[:, 1]
                fold_aucs.append(roc_auc_score(y_train[va_idx], p_va))
            if not fold_aucs:
                continue
            mean_auc = float(np.mean(fold_aucs))
            if mean_auc > best["cv_mean_auc"]:
                best = {
                    "cv_mean_auc": mean_auc,
                    "best_C": C,
                    "best_l1_ratio": l1,
                    "cv_fold_aucs": fold_aucs,
                }

    if best["cv_mean_auc"] == -np.inf:
        raise ValueError("no valid CV folds (all folds had single-class validation sets)")

    final = LogisticRegression(
        penalty="elasticnet", solver="saga",
        l1_ratio=best["best_l1_ratio"], C=best["best_C"],
        class_weight="balanced", max_iter=5000, random_state=random_state,
    )
    final.fit(X_train, y_train, sample_weight=sample_weights)
    return final, best


def score_en_cell(model: LogisticRegression, X: np.ndarray) -> np.ndarray:
    """Return predict_proba for the positive class."""
    return model.predict_proba(X)[:, 1]
