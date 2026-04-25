# pipeline/autoresearch/etf_stock_tail/permutation_null.py
"""Label-permutation null on held-out cross-entropy (joblib-parallel)."""
from __future__ import annotations

from typing import Optional

import numpy as np
from joblib import Parallel, delayed


def cross_entropy(probs: np.ndarray, labels: np.ndarray, eps: float = 1e-12) -> float:
    n = len(labels)
    return float(-np.mean(np.log(probs[np.arange(n), labels] + eps)))


def _one_perm(probs: np.ndarray, labels: np.ndarray, seed: int) -> float:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(labels)
    return cross_entropy(probs, perm)


def label_permutation_null(
    probs: np.ndarray,
    labels: np.ndarray,
    n_permutations: int,
    seed: int = 42,
    n_jobs: int = -1,
) -> dict:
    obs = cross_entropy(probs, labels)
    seeds = np.random.SeedSequence(seed).generate_state(n_permutations)
    perm_ces = Parallel(n_jobs=n_jobs, verbose=0)(
        delayed(_one_perm)(probs, labels, int(s)) for s in seeds
    )
    perm_arr = np.asarray(perm_ces, dtype=float)
    # Lower CE is better; p = P(perm CE ≤ observed CE under null)
    p = float((perm_arr <= obs).mean())
    return {
        "obs_ce": obs,
        "p_value": p,
        "n_permutations": n_permutations,
        "perm_ce_min": float(perm_arr.min()),
        "perm_ce_max": float(perm_arr.max()),
        "perm_ce_quantile_0p01": float(np.quantile(perm_arr, 0.01)),
    }
