"""Quarterly walk-forward validation for per-ticker feature models."""
from __future__ import annotations
from typing import Any
import pandas as pd
from sklearn.metrics import roc_auc_score
from pipeline.feature_scorer.model import fit_logistic, predict_proba

_N_FOLDS_MIN = 3


def classify_health(*, mean_auc: float, min_fold_auc: float, n_folds: int) -> str:
    if n_folds < _N_FOLDS_MIN:
        return "RED"
    if mean_auc >= 0.55 and min_fold_auc >= 0.50:
        return "GREEN"
    if mean_auc >= 0.52:
        return "AMBER"
    return "RED"


def _build_folds(as_of: str, train_years: int, test_months: int, max_folds: int = 6) -> list[dict]:
    """Compose date windows: each fold's test is train_years of history + next test_months."""
    as_of_ts = pd.Timestamp(as_of)
    out = []
    for i in range(max_folds):
        test_end = as_of_ts - pd.DateOffset(months=test_months * i)
        test_start = test_end - pd.DateOffset(months=test_months)
        train_end = test_start
        train_start = train_end - pd.DateOffset(years=train_years)
        out.append({
            "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
        })
    return out


def run_walk_forward(
    df: pd.DataFrame,
    *,
    train_years: int = 2,
    test_months: int = 3,
    as_of: str,
    max_folds: int = 6,
) -> dict[str, Any]:
    df = df.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(df["date"])

    fold_windows = _build_folds(as_of, train_years, test_months, max_folds)
    folds: list[dict] = []

    for w in fold_windows:
        train_mask = (dates >= w["train_start"]) & (dates < w["train_end"])
        test_mask = (dates >= w["test_start"]) & (dates < w["test_end"])
        # Threshold chosen to accommodate Indian trading-day count (~250/yr)
        # so a 2-year train window yields ~500 rows minus the 20-day feature
        # lookback. Setting hard 500 floor caused every ticker to fail by
        # ~5-10 rows on 2026-04-23; 400 matches the TA scorer threshold and
        # still leaves ~1.5-1.6 years of data per fold.
        if train_mask.sum() < 400 or test_mask.sum() < 30:
            continue
        X_train = df.loc[train_mask].drop(columns=["date", "y"], errors="ignore")
        y_train = df.loc[train_mask, "y"]
        X_test = df.loc[test_mask].drop(columns=["date", "y"], errors="ignore")
        y_test = df.loc[test_mask, "y"]

        if y_train.nunique() < 2 or y_test.nunique() < 2:
            continue

        model = fit_logistic(X_train, y_train)
        probs = predict_proba(model, X_test)
        auc = float(roc_auc_score(y_test, probs))
        folds.append({
            "train_start": str(w["train_start"].date()),
            "train_end": str(w["train_end"].date()),
            "test_start": str(w["test_start"].date()),
            "test_end": str(w["test_end"].date()),
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "auc": auc,
        })

    if not folds:
        return {"folds": [], "mean_auc": None, "min_fold_auc": None,
                "health": "UNAVAILABLE"}

    aucs = [f["auc"] for f in folds]
    mean_auc = sum(aucs) / len(aucs)
    min_fold_auc = min(aucs)
    return {
        "folds": folds,
        "mean_auc": mean_auc,
        "min_fold_auc": min_fold_auc,
        "health": classify_health(mean_auc=mean_auc, min_fold_auc=min_fold_auc,
                                   n_folds=len(folds)),
    }
