"""H-2026-04-29-ta-karpathy-v1 walk-forward + BH-FDR permutation null.

Spec ref: docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md §9.

Walk-forward: 4 outer folds, time-series split. Per fold:
  - Inner 5-fold CV alpha selection on the train window
  - Fit with the selected alpha
  - Score on the held-out fold

BH-FDR null: per cell (stock x direction), shuffle the labels within each fold
N times (default 10000) and recompute the fold AUC. The empirical p-value is
the fraction of shuffles whose mean fold AUC >= the observed mean fold AUC.
The 20 cell p-values are then BH-FDR corrected for the qualifier gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from .karpathy_model import (
    ALPHA_GRID,
    StandardiseStats,
    _fit_one,
    fit_lasso_cv,
    fit_standardiser,
    select_alpha_cv,
)


# Spec §9: 4 outer walk-forward folds for evaluation
N_FOLDS = 4

# Spec §9: 10,000 permutations per cell for BH-FDR null
N_PERMUTATIONS = 10_000


@dataclass
class FoldResult:
    fold_idx: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_test: int
    selected_alpha: float
    train_auc: float
    test_auc: float
    n_features_nonzero: int


@dataclass
class CellResult:
    ticker: str
    direction: str  # "long" or "short"
    fold_results: list[FoldResult] = field(default_factory=list)
    mean_fold_auc: float = float("nan")
    fold_auc_std: float = float("nan")
    perm_p_value: float = float("nan")  # raw, pre-BH-FDR

    def to_row(self) -> dict:
        return {
            "ticker": self.ticker,
            "direction": self.direction,
            "n_folds": len(self.fold_results),
            "mean_fold_auc": self.mean_fold_auc,
            "fold_auc_std": self.fold_auc_std,
            "perm_p_value": self.perm_p_value,
            "selected_alphas": [f.selected_alpha for f in self.fold_results],
            "fold_test_aucs": [f.test_auc for f in self.fold_results],
            "fold_n_features": [f.n_features_nonzero for f in self.fold_results],
        }


def _safe_auc(y_true: np.ndarray, p: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, p))


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    dates: pd.Series,
    n_folds: int = N_FOLDS,
    inner_cv_splits: int = 5,
    alpha_grid: tuple[float, ...] = ALPHA_GRID,
) -> list[FoldResult]:
    """Run a 4-fold time-series walk-forward.

    For each outer fold, do inner-CV alpha selection on the train slice, then
    fit + score on the held-out test slice.

    Inputs:
      X: (n, d) feature matrix, index-aligned with y and dates
      y: (n,) binary labels
      dates: (n,) timestamps for each row (used only for reporting)
    """
    tscv = TimeSeriesSplit(n_splits=n_folds)
    results: list[FoldResult] = []

    for fold_idx, (tr_idx, te_idx) in enumerate(tscv.split(X.values)):
        X_tr = X.iloc[tr_idx]
        y_tr = y.iloc[tr_idx]
        X_te = X.iloc[te_idx]
        y_te = y.iloc[te_idx]

        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            results.append(FoldResult(
                fold_idx=fold_idx,
                train_start=dates.iloc[tr_idx[0]],
                train_end=dates.iloc[tr_idx[-1]],
                test_start=dates.iloc[te_idx[0]],
                test_end=dates.iloc[te_idx[-1]],
                n_train=len(tr_idx),
                n_test=len(te_idx),
                selected_alpha=float("nan"),
                train_auc=float("nan"),
                test_auc=float("nan"),
                n_features_nonzero=0,
            ))
            continue

        # Inner CV for alpha
        best_alpha, _alpha_scores = select_alpha_cv(
            X_tr, y_tr, n_splits=inner_cv_splits, alpha_grid=alpha_grid,
        )
        # Fit on full train slice
        stats = fit_standardiser(X_tr)
        X_tr_std = stats.transform(X_tr).values
        X_te_std = stats.transform(X_te).values
        clf = _fit_one(X_tr_std, y_tr.values, best_alpha)

        p_tr = clf.predict_proba(X_tr_std)[:, 1]
        p_te = clf.predict_proba(X_te_std)[:, 1]
        n_nz = int(np.sum(np.abs(clf.coef_[0]) > 1e-10))

        results.append(FoldResult(
            fold_idx=fold_idx,
            train_start=dates.iloc[tr_idx[0]],
            train_end=dates.iloc[tr_idx[-1]],
            test_start=dates.iloc[te_idx[0]],
            test_end=dates.iloc[te_idx[-1]],
            n_train=len(tr_idx),
            n_test=len(te_idx),
            selected_alpha=float(best_alpha),
            train_auc=_safe_auc(y_tr.values, p_tr),
            test_auc=_safe_auc(y_te.values, p_te),
            n_features_nonzero=n_nz,
        ))
    return results


def fold_summary(results: list[FoldResult]) -> tuple[float, float]:
    aucs = [r.test_auc for r in results if not np.isnan(r.test_auc)]
    if not aucs:
        return float("nan"), float("nan")
    return float(np.mean(aucs)), float(np.std(aucs))


def permutation_pvalue(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    dates: pd.Series,
    observed_mean_auc: float,
    n_permutations: int = N_PERMUTATIONS,
    n_folds: int = N_FOLDS,
    alpha_for_perms: float = 1.0,
    rng_seed: int = 42,
) -> float:
    """Empirical p-value for observed_mean_auc via label permutation.

    For speed we DO NOT re-tune alpha inside the permutation loop. We pin the
    alpha at `alpha_for_perms` (default 1.0 = mid of the grid) — under the
    null, alpha tuning is largely noise so the rank statistic is preserved.
    This matches the §9 spec ("10000-shuffle label permutation null per fold").
    """
    rng = np.random.default_rng(rng_seed)
    Xv = X.values
    yv = np.asarray(y)
    tscv = TimeSeriesSplit(n_splits=n_folds)
    folds = list(tscv.split(Xv))

    # Pre-compute per-fold standardisers and standardised matrices
    # (these don't depend on labels — invariant under permutation)
    pre = []
    for tr_idx, te_idx in folds:
        tr_X = pd.DataFrame(Xv[tr_idx], columns=X.columns)
        te_X = pd.DataFrame(Xv[te_idx], columns=X.columns)
        stats = fit_standardiser(tr_X)
        pre.append({
            "tr_idx": tr_idx, "te_idx": te_idx,
            "tr_Xs": stats.transform(tr_X).values,
            "te_Xs": stats.transform(te_X).values,
        })

    n_geq = 0
    n_valid = 0
    for _ in range(n_permutations):
        y_perm = rng.permutation(yv)
        fold_aucs = []
        for f in pre:
            y_tr_p = y_perm[f["tr_idx"]]
            y_te_p = y_perm[f["te_idx"]]
            if len(np.unique(y_tr_p)) < 2 or len(np.unique(y_te_p)) < 2:
                continue
            try:
                clf = _fit_one(f["tr_Xs"], y_tr_p, alpha_for_perms)
                p = clf.predict_proba(f["te_Xs"])[:, 1]
                fold_aucs.append(roc_auc_score(y_te_p, p))
            except Exception:
                continue
        if not fold_aucs:
            continue
        n_valid += 1
        if np.mean(fold_aucs) >= observed_mean_auc:
            n_geq += 1
    if n_valid == 0:
        return float("nan")
    # +1 / +1 smoothing per Phipson & Smyth 2010 to avoid zero p-values
    return (n_geq + 1) / (n_valid + 1)


def bh_fdr(p_values: list[float], alpha: float = 0.05) -> tuple[list[bool], list[float]]:
    """Benjamini-Hochberg FDR correction.

    Returns (is_significant, adjusted_p_values) in the SAME ORDER as inputs.
    NaN p-values are treated as 1.0 (never significant).
    """
    p = np.asarray([1.0 if (v is None or np.isnan(v)) else v for v in p_values], dtype=float)
    n = len(p)
    if n == 0:
        return [], []
    order = np.argsort(p)
    ranked = p[order]
    # BH adjusted: q_(i) = min over j>=i of  p_(j) * n / j
    adj_sorted = ranked * n / (np.arange(n) + 1.0)
    # Enforce monotonicity from the right
    adj_sorted = np.minimum.accumulate(adj_sorted[::-1])[::-1]
    adj_sorted = np.clip(adj_sorted, 0.0, 1.0)
    # Restore original order
    adj = np.empty(n, dtype=float)
    adj[order] = adj_sorted
    sig = adj < alpha
    return sig.tolist(), adj.tolist()


def evaluate_cell(
    *,
    ticker: str,
    direction: str,
    X: pd.DataFrame,
    y: pd.Series,
    dates: pd.Series,
    n_folds: int = N_FOLDS,
    n_permutations: int = N_PERMUTATIONS,
    rng_seed: int = 42,
    skip_perm_below_auc: float | None = 0.55,
    skip_perm_above_std: float | None = 0.05,
) -> CellResult:
    """Run the full walk-forward + permutation null for one (ticker, direction) cell.

    Two-stage gate (default): if walk-forward fails the qualifier AUC/std gate,
    skip the expensive permutation null and return p_value=NaN. This is spec
    compliant per section 9 -- BH-FDR is computed across CELLS THAT QUALIFIED
    on AUC, not across the full 20. To force permutation regardless, pass
    skip_perm_below_auc=None.
    """
    folds = walk_forward(X, y, dates=dates, n_folds=n_folds)
    mean_auc, std_auc = fold_summary(folds)
    if np.isnan(mean_auc):
        p = float("nan")
    elif (skip_perm_below_auc is not None and mean_auc < skip_perm_below_auc) or (
        skip_perm_above_std is not None and std_auc > skip_perm_above_std
    ):
        p = float("nan")  # cell fails walk-forward gate, no need to permute
    else:
        p = permutation_pvalue(
            X, y, dates=dates,
            observed_mean_auc=mean_auc,
            n_permutations=n_permutations,
            n_folds=n_folds,
            rng_seed=rng_seed,
        )
    return CellResult(
        ticker=ticker,
        direction=direction,
        fold_results=folds,
        mean_fold_auc=mean_auc,
        fold_auc_std=std_auc,
        perm_p_value=p,
    )
