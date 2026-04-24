"""Holdout gate: single-touch per rule + BH-FDR q=0.1 batch."""
from __future__ import annotations

from pipeline.autoresearch.regime_autoresearch.constants import (
    BH_FDR_Q, BH_FDR_BATCH_CALENDAR_DAYS, BH_FDR_BATCH_ACCUMULATED_COUNT,
)


def bh_fdr_threshold(pvals: list[float], q: float = BH_FDR_Q) -> float | None:
    """Benjamini-Hochberg FDR threshold.

    Returns the largest p-value that survives, or None if no p-value survives.
    """
    if not pvals:
        return None
    sorted_p = sorted(pvals)
    m = len(sorted_p)
    survivor = None
    for k, p in enumerate(sorted_p, start=1):
        if p <= (k / m) * q:
            survivor = p
    return survivor


def should_fire_batch(days_since_last: int, count_accumulated: int) -> bool:
    """Whichever-first rule."""
    return (days_since_last >= BH_FDR_BATCH_CALENDAR_DAYS
            or count_accumulated >= BH_FDR_BATCH_ACCUMULATED_COUNT)
