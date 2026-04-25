# pipeline/autoresearch/etf_stock_tail/calibration.py
"""Platt scaling + Brier decomposition + per-class reliability bins."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from pipeline.autoresearch.etf_stock_tail import constants as C


class PlattScaler:
    """Multinomial Platt: fit a logistic regression on (logits → label) then transform."""

    def __init__(self):
        # NOTE: multi_class kwarg removed for sklearn 1.8 compat (raises TypeError otherwise).
        # sklearn auto-detects multinomial when len(classes_) > 2.
        self.model_ = LogisticRegression(solver="lbfgs",
                                         max_iter=500, random_state=C.RANDOM_SEED)

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> "PlattScaler":
        self.model_.fit(logits, labels)
        return self

    def transform(self, logits: np.ndarray) -> np.ndarray:
        return self.model_.predict_proba(logits)


def reliability_bins(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> dict:
    """Per-class reliability: for each predicted-prob bin, return (mean_pred, frac_pos, count)."""
    out = {name: [] for name in C.CLASS_NAMES}
    edges = np.linspace(0, 1, n_bins + 1)
    for cls, name in enumerate(C.CLASS_NAMES):
        p_cls = probs[:, cls]
        y_cls = (labels == cls).astype(float)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (p_cls >= lo) & (p_cls < hi if hi < 1.0 else p_cls <= hi)
            if mask.sum() > 0:
                out[name].append({
                    "mean_pred": float(p_cls[mask].mean()),
                    "frac_pos": float(y_cls[mask].mean()),
                    "count": int(mask.sum()),
                })
            else:
                out[name].append({"mean_pred": float("nan"), "frac_pos": float("nan"), "count": 0})
    return out


def brier_decomposition(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> dict:
    """Murphy 1973 Brier decomposition. Sums over all 3 classes (multi-class Brier).

    ``total`` is the Murphy-binned Brier estimate (bin-mean probabilities substituted for
    each raw forecast), which makes the identity total = reliability - resolution + uncertainty
    algebraically exact.  The algebraic proof: total_binned = REL + sum_k nk/n*yk_bar*(1-yk_bar)
    and sum_k nk/n*yk_bar*(1-yk_bar) + RES = UNC (Murphy 1973 eq. 3), so total = REL-RES+UNC.
    """
    n = len(labels)

    # Per-class reliability + resolution; sum over classes for multiclass total
    edges = np.linspace(0, 1, n_bins + 1)
    rel_sum = 0.0
    res_sum = 0.0
    unc_sum = 0.0
    total = 0.0
    for cls in range(probs.shape[1]):
        p = probs[:, cls]
        y = (labels == cls).astype(float)
        ybar = float(y.mean())
        unc_sum += ybar * (1 - ybar)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (p >= lo) & (p < hi if hi < 1.0 else p <= hi)
            nk = int(mask.sum())
            if nk == 0:
                continue
            pk_bar = float(p[mask].mean())
            yk_bar = float(y[mask].mean())
            rel_sum += (nk / n) * (pk_bar - yk_bar) ** 2
            res_sum += (nk / n) * (yk_bar - ybar) ** 2
            # Murphy-binned Brier: replace raw p_i with bin-mean pk_bar so decomp is exact.
            # sum_j in bin (pk_bar - yj)^2 / n = nk/n * (pk_bar - yk_bar)^2 + nk/n * yk_bar*(1-yk_bar)
            total += (nk / n) * ((pk_bar - yk_bar) ** 2 + yk_bar * (1 - yk_bar))

    return {"total": total, "reliability": rel_sum,
            "resolution": res_sum, "uncertainty": unc_sum}
