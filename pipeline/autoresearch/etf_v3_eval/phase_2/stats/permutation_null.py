"""§9B.2: permutation / reality-check tests with n ≥ 10,000 default.

Two-sample mean-difference shuffle preserving total event count. Use this for
strategy-vs-naive-benchmark comparisons.
"""
from __future__ import annotations

import numpy as np


def permutation_test_mean(
    a: np.ndarray,
    b: np.ndarray,
    n_permutations: int = 10_000,
    rng: np.random.Generator | None = None,
) -> float:
    """Two-sided permutation p-value: P(|shuffled mean diff| ≥ |observed mean diff|).

    Uses the (count + 1) / (n + 1) correction so the minimum reportable p-value
    is 1/(n_permutations + 1) (avoids 0.0 in finite-permutation tests).

    Accepts either ``np.ndarray`` or any sequence convertible by ``np.asarray``.
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    pooled = np.concatenate([np.asarray(a, dtype=float), np.asarray(b, dtype=float)])
    n_a = len(a)
    # Use already-cast pooled slices so list inputs work and obs uses the same
    # array semantics as the per-iteration comparisons.
    obs = abs(pooled[:n_a].mean() - pooled[n_a:].mean())
    count_extreme = 0
    for _ in range(n_permutations):
        # In-place shuffle — every call is a fresh uniform permutation of the
        # same multiset (do NOT replace with np.random.permutation: it would
        # allocate a new array per iteration).
        rng.shuffle(pooled)
        diff = abs(pooled[:n_a].mean() - pooled[n_a:].mean())
        if diff >= obs:
            count_extreme += 1
    return (count_extreme + 1) / (n_permutations + 1)
