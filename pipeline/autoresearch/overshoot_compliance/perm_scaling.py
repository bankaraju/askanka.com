"""Streaming permutation-test runner for §9B.2.

Bootstraps the mean of n_events draws from an unconditional return
distribution n_shuffles times without allocating the full permutation
matrix. Works for n_shuffles up to ~10M on commodity hardware with a
5000-row batch.
"""
from __future__ import annotations

import numpy as np


def bootstrap_p_value(
    *,
    observed_mean: float,
    unconditional: np.ndarray,
    n_events: int,
    n_shuffles: int,
    seed: int | None = None,
    batch_size: int = 5_000,
    require_perm_floor: int | None = None,
) -> float:
    """One-sided: probability that a bootstrap mean meets/exceeds observed_mean."""
    if require_perm_floor is not None and n_shuffles < require_perm_floor:
        raise ValueError(
            f"n_shuffles={n_shuffles} below required floor {require_perm_floor} "
            "per §9B.2 when Bonferroni/FDR is active"
        )
    if n_events <= 0:
        return 1.0
    arr = np.asarray(unconditional, dtype=float)
    if arr.size == 0:
        return 1.0
    rng = np.random.default_rng(seed)

    remaining = n_shuffles
    exceed = 0
    while remaining > 0:
        this_batch = min(batch_size, remaining)
        sample = rng.choice(arr, size=(this_batch, n_events), replace=True)
        means = sample.mean(axis=1)
        exceed += int(np.sum(means >= observed_mean))
        remaining -= this_batch
    return exceed / n_shuffles
