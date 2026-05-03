"""4-fold expanding-origin walk-forward with qualifier gate, BH-FDR, permutation null."""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def expanding_quarter_folds(
    index: pd.DatetimeIndex, n_folds: int = 4,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-origin walk-forward: 4 contiguous quarters within training, expanding train.

    Returns list of (train_positional_idx, val_positional_idx) tuples.
    """
    n = len(index)
    fold_size = n // (n_folds + 1)  # +1 so first fold has fold_size train + fold_size val
    folds = []
    for k in range(n_folds):
        tr_start = 0
        tr_end = fold_size * (k + 1)
        va_start = tr_end
        va_end = min(tr_end + fold_size, n)
        if va_start >= va_end:
            break
        folds.append((np.arange(tr_start, tr_end), np.arange(va_start, va_end)))
    return folds


def bh_fdr(p_values: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg correction. Returns boolean array of survivors."""
    n = len(p_values)
    order = np.argsort(p_values)
    ranked = p_values[order]
    thresholds = (np.arange(1, n + 1) / n) * alpha
    survivors_in_order = ranked <= thresholds
    if not survivors_in_order.any():
        return np.zeros(n, dtype=bool)
    last_survivor = np.where(survivors_in_order)[0].max()
    out = np.zeros(n, dtype=bool)
    out[order[: last_survivor + 1]] = True
    return out


def qualifier_check(
    *,
    fold_aucs: Sequence[float],
    p_value: float,
    p_threshold: float,
    in_sample_holdout_auc: float,
    n_pred_pos_isho: int,
    perm_beat_pct: float,
) -> tuple[bool, list[str]]:
    """Apply the section 9 qualifier gate. Returns (qualified, list_of_failure_reasons).

    Gates per spec section 9:
      1. mean fold-AUC >= 0.55
      2. fold-AUC std <= 0.05
      3. in-sample-holdout AUC >= 0.55
      4. n predicted positive in in-sample-holdout >= 5
      5. BH-FDR p < threshold
      6. permutation null beat >= 95%
    """
    reasons = []
    aucs = np.array(fold_aucs)
    if aucs.mean() < 0.55:
        reasons.append(f"mean fold-AUC {aucs.mean():.3f} < 0.55")
    if aucs.std() > 0.05:
        reasons.append(f"fold-AUC std {aucs.std():.3f} > 0.05")
    if in_sample_holdout_auc < 0.55:
        reasons.append(f"in-sample-holdout AUC {in_sample_holdout_auc:.3f} < 0.55")
    if n_pred_pos_isho < 5:
        reasons.append(f"in-sample-holdout n_pred_pos {n_pred_pos_isho} < 5")
    if p_value >= p_threshold:
        reasons.append(f"BH-FDR p {p_value:.4f} >= {p_threshold}")
    if perm_beat_pct < 0.95:
        reasons.append(f"perm beat {perm_beat_pct:.3f} < 0.95")
    return (len(reasons) == 0, reasons)


def permutation_p_value(
    *,
    y_true: np.ndarray,
    y_score: np.ndarray,
    n_permutations: int,
    random_state: int,
) -> float:
    """Two-sided permutation p-value for AUC."""
    if len(np.unique(y_true)) < 2:
        return 1.0
    observed = roc_auc_score(y_true, y_score)
    rng = np.random.default_rng(random_state)
    null = []
    for _ in range(n_permutations):
        shuffled = rng.permutation(y_true)
        if len(np.unique(shuffled)) < 2:
            null.append(0.5)
            continue
        null.append(roc_auc_score(shuffled, y_score))
    null = np.array(null)
    p = (np.abs(null - 0.5) >= abs(observed - 0.5)).mean()
    return float(p)
