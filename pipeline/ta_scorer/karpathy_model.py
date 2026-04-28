"""H-2026-04-29-ta-karpathy-v1 Lasso L1 logistic regression with per-fold alpha CV.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md §8.

sklearn LogisticRegression uses `C` (inverse regularisation strength). The spec
expresses alpha (= 1/C). We accept the alpha grid externally and convert.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

# Silence sklearn 1.8 FutureWarning about penalty/l1_ratio: penalty='l1' +
# solver='liblinear' is still functionally correct through sklearn 1.10. The
# new l1_ratio API requires solver='saga' which is materially slower and
# differs in tie-breaking. Keep the working path and silence the noise.
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=ConvergenceWarning, module="sklearn")

# Spec §8: alpha grid (9 points, log-spaced)
ALPHA_GRID: tuple[float, ...] = (
    1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0, 10.0,
)


@dataclass
class StandardiseStats:
    mean: pd.Series
    std: pd.Series

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return (X - self.mean) / self.std


def fit_standardiser(X_train: pd.DataFrame) -> StandardiseStats:
    mean = X_train.mean()
    std = X_train.std().replace(0, 1.0)
    return StandardiseStats(mean=mean, std=std)


def _fit_one(X: np.ndarray, y: np.ndarray, alpha: float) -> LogisticRegression:
    C = 1.0 / alpha
    clf = LogisticRegression(
        penalty="l1",
        solver="liblinear",
        class_weight="balanced",
        C=C,
        max_iter=2000,
        random_state=42,
    )
    clf.fit(X, y)
    return clf


def select_alpha_cv(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    n_splits: int = 5,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
) -> tuple[float, dict[float, float]]:
    """5-fold inner time-series CV. Returns (best_alpha, {alpha: mean_cv_auc}).

    If a fold has only one class in either train or val, that fold's AUC for
    that alpha is set to 0.5. Best alpha = highest mean CV AUC; ties broken by
    LARGER alpha (stronger regularisation) per Occam.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    Xv = X_train.values
    yv = np.asarray(y_train)

    scores: dict[float, list[float]] = {a: [] for a in alpha_grid}
    for tr_idx, va_idx in tscv.split(Xv):
        if len(np.unique(yv[tr_idx])) < 2 or len(np.unique(yv[va_idx])) < 2:
            for a in alpha_grid:
                scores[a].append(0.5)
            continue
        # Standardise inside the inner fold (no leakage)
        tr_X = pd.DataFrame(Xv[tr_idx], columns=X_train.columns)
        va_X = pd.DataFrame(Xv[va_idx], columns=X_train.columns)
        stats = fit_standardiser(tr_X)
        tr_Xs = stats.transform(tr_X).values
        va_Xs = stats.transform(va_X).values
        for a in alpha_grid:
            try:
                clf = _fit_one(tr_Xs, yv[tr_idx], a)
                p = clf.predict_proba(va_Xs)[:, 1]
                auc = roc_auc_score(yv[va_idx], p)
            except Exception:
                auc = 0.5
            scores[a].append(auc)

    mean_scores = {a: float(np.mean(scores[a])) for a in alpha_grid}
    # Best alpha: highest mean AUC; tie -> larger alpha
    best_alpha = max(alpha_grid, key=lambda a: (mean_scores[a], a))
    return best_alpha, mean_scores


def fit_lasso_cv(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    n_splits: int = 5,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
) -> tuple[LogisticRegression, StandardiseStats, float, dict[float, float]]:
    """Fit Lasso L1 logistic with 5-fold time-series CV alpha selection.

    Returns (fitted_clf, standardise_stats, best_alpha, alpha_score_map).
    The returned classifier was fit on the FULL train set (post-standardisation)
    using the CV-selected alpha. Use stats.transform on test data before predict.
    """
    best_alpha, scores = select_alpha_cv(
        X_train, y_train, n_splits=n_splits, alpha_grid=alpha_grid,
    )
    stats = fit_standardiser(X_train)
    X_std = stats.transform(X_train).values
    clf = _fit_one(X_std, np.asarray(y_train), best_alpha)
    return clf, stats, best_alpha, scores


def predict_proba(clf: LogisticRegression, stats: StandardiseStats, X: pd.DataFrame) -> np.ndarray:
    """Return positive-class probability after applying the saved standardiser."""
    return clf.predict_proba(stats.transform(X).values)[:, 1]


def nonzero_features(clf: LogisticRegression, columns: list[str]) -> dict[str, float]:
    """Return {feature_name: coef} for non-zero L1 coefficients."""
    coefs = clf.coef_[0]
    return {col: float(c) for col, c in zip(columns, coefs) if abs(c) > 1e-10}
