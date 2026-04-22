"""Quarterly walk-forward validation for TA scorer. Mirrors feature_scorer
shape (2y train / 3mo test / 6 folds) but single-ticker and simpler frame
conventions."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from pipeline.ta_scorer import model as _model


def classify_health(*, mean_auc: float, min_fold_auc: float, n_folds: int) -> str:
    """Map fold-level AUC stats to a UI health band.

    Rules (evaluated in order):
      - ``n_folds < 3`` → ``UNAVAILABLE``
      - ``mean_auc >= 0.55`` AND ``min_fold_auc >= 0.52`` → ``GREEN``
      - ``mean_auc >= 0.52`` → ``AMBER`` (mean is passable but not
        consistently strong across folds)
      - otherwise → ``RED``
    """
    if n_folds < 3:
        return "UNAVAILABLE"
    if mean_auc >= 0.55 and min_fold_auc >= 0.52:
        return "GREEN"
    if mean_auc >= 0.52:  # includes case where mean>=0.55 but min<0.52
        return "AMBER"
    return "RED"


def _build_folds(dates: pd.Series, *, train_years: int, test_months: int,
                 max_folds: int, as_of: str) -> list[tuple[str, str, str, str]]:
    """Build up to ``max_folds`` quarterly folds anchored at ``as_of``.

    Each fold is ``(train_start, train_end, test_start, test_end)`` as
    ``YYYY-MM-DD`` strings. Folds are returned in chronological order
    (oldest first). Requires ≥400 unique trading dates in ``dates``.
    """
    dates = pd.to_datetime(dates.drop_duplicates().sort_values())
    if len(dates) < 400:
        return []
    anchor = pd.to_datetime(as_of)
    # Clamp to the last date <= as_of so we never walk past available data.
    end = dates[dates <= anchor].max() if (dates <= anchor).any() else dates.iloc[-1]
    folds = []
    for k in range(max_folds):
        test_end = end - pd.DateOffset(months=k * test_months)
        test_start = test_end - pd.DateOffset(months=test_months) + pd.Timedelta(days=1)
        train_end = test_start - pd.Timedelta(days=1)
        train_start = train_end - pd.DateOffset(years=train_years) + pd.Timedelta(days=1)
        if train_start < dates.iloc[0]:
            break
        folds.append((train_start.strftime("%Y-%m-%d"),
                      train_end.strftime("%Y-%m-%d"),
                      test_start.strftime("%Y-%m-%d"),
                      test_end.strftime("%Y-%m-%d")))
    folds.reverse()
    return folds


def run_walk_forward(frame: pd.DataFrame, *, train_years: int, test_months: int,
                     as_of: str, max_folds: int = 6) -> dict:
    """Run quarterly walk-forward validation on a single-ticker frame.

    ``frame`` must contain ``date``, ``y``, and feature columns. Folds are
    anchored at ``as_of`` (folds whose test window ends at or before
    ``as_of``). Returns:

        {"health": str, "mean_auc": float|None, "min_fold_auc": float|None,
         "n_folds": int, "folds": [per-fold detail dicts]}

    If no fold survives data-quality guards (≥400 train rows, ≥40 test
    rows, both classes present), returns the UNAVAILABLE shape with
    ``n_folds=0``.
    """
    folds = _build_folds(frame["date"], train_years=train_years,
                         test_months=test_months, max_folds=max_folds,
                         as_of=as_of)
    feature_cols = [c for c in frame.columns if c not in ("date", "y")]
    auc_list, details = [], []
    for tr_s, tr_e, te_s, te_e in folds:
        train = frame[(frame["date"] >= tr_s) & (frame["date"] <= tr_e)]
        test = frame[(frame["date"] >= te_s) & (frame["date"] <= te_e)]
        if len(train) < 400 or len(test) < 40:
            continue
        if train["y"].nunique() < 2 or test["y"].nunique() < 2:
            continue
        X_tr = _model.build_interaction_columns(train[feature_cols])
        X_te = _model.build_interaction_columns(test[feature_cols])
        clf = _model.fit_logistic(X_tr, train["y"])
        p = _model.predict_proba(clf, X_te)
        auc = float(roc_auc_score(test["y"], p))
        auc_list.append(auc)
        details.append({"train_start": tr_s, "train_end": tr_e,
                        "test_start": te_s, "test_end": te_e,
                        "n_train": len(train), "n_test": len(test),
                        "auc": auc})
    if not auc_list:
        return {"health": "UNAVAILABLE", "n_folds": 0, "mean_auc": None,
                "min_fold_auc": None, "folds": []}
    mean_auc = float(np.mean(auc_list))
    min_fold = float(np.min(auc_list))
    return {
        "health": classify_health(mean_auc=mean_auc, min_fold_auc=min_fold,
                                  n_folds=len(auc_list)),
        "mean_auc": mean_auc, "min_fold_auc": min_fold,
        "n_folds": len(auc_list), "folds": details,
    }
