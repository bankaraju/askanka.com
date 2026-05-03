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
    bh_fdr_survivor: bool,
    fold_auc_threshold: float = 0.53,
) -> tuple[bool, list[str]]:
    """Cell-level qualifier per §9C of backtesting-specs.txt (Revision 1.1).

    Two gates:
      GATE A: mean walk-forward fold-AUC >= fold_auc_threshold (default 0.53,
              per A2 amendment to H-2026-05-04 spec; was 0.55 at v1.0).
      GATE B: BH-FDR p-value below pre-registered alpha. Family scope is
              per-direction (LONG, SHORT each form their own family per
              §9C.3) and N_PERMUTATIONS satisfies §9B.2 (>=100,000 with FDR).
              Caller passes the survivor flag computed by `bh_fdr` over the
              per-direction p-value array.

    Removed at A2 (kept as informational outputs in cell records, not gates):
      - fold-AUC std (forbidden by §9C.2 — Pardo 2008 §6.7)
      - in-sample-holdout AUC (forbidden by §9C.2 — leakage-prone)
      - n_pred_pos absolute threshold (forbidden by §9C.2 — non-standard)
      - perm-beat-percentile (forbidden by §9C.2 — redundant with Gate B)
    """
    reasons: list[str] = []
    aucs = np.array(fold_aucs)
    if aucs.mean() < fold_auc_threshold:
        reasons.append(
            f"mean fold-AUC {aucs.mean():.3f} < {fold_auc_threshold} (Gate A)"
        )
    if not bh_fdr_survivor:
        reasons.append("BH-FDR survivor=False (Gate B)")
    return (len(reasons) == 0, reasons)


def bh_fdr_per_direction(
    cells: Sequence[dict],
    *,
    alpha: float = 0.05,
    p_field: str = "perm_p_value",
    direction_field: str = "direction",
) -> dict[tuple[str, str], bool]:
    """Apply BH-FDR per-direction (§9C.3 default family scope).

    Splits `cells` by `direction_field`, computes BH-FDR survivors within
    each direction family at the given alpha, and returns a dict keyed by
    (ticker, direction) pointing at the survivor flag for that cell.

    Caller is expected to provide a `ticker` field on each cell.
    """
    out: dict[tuple[str, str], bool] = {}
    by_dir: dict[str, list[dict]] = {}
    for c in cells:
        by_dir.setdefault(c[direction_field], []).append(c)
    for direction, dir_cells in by_dir.items():
        p_arr = np.array([c[p_field] for c in dir_cells])
        survivors = bh_fdr(p_arr, alpha=alpha)
        for c, surv in zip(dir_cells, survivors):
            out[(c["ticker"], direction)] = bool(surv)
    return out


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
