"""K-fold time-series cross-validation for Sharpe robustness.

NOT purged walk-forward in the Lopez de Prado / ML sense. Our DSL rules
have no trainable parameters — a rule like `days_from_52w_high bottom_10
hold_horizon=5` is fully specified up front, there is nothing to fit. What
we actually need is a cross-time Sharpe estimate so early-heavy alpha
cannot look robust when it isn't distributed across time.

The split:

  * Sort event_dates ascending.
  * Partition into K contiguous chunks along the time axis.
  * Drop the first `embargo_days` events of every chunk after the first
    so a trade opened in chunk k-1 with a `hold_horizon`-day exit cannot
    bleed into chunk k's event set. The caller is responsible for
    passing `embargo_days = max(2, hold_horizon)`.
  * Return K test folds as `pd.DatetimeIndex` objects; there is no
    "train" fold because there are no trainable parameters.

Edge cases:

  * Any fold that ends up with fewer than `MIN_EVENTS_PER_FOLD=5` events
    after embargo is dropped from the return list. This prevents a
    degenerate 1-event fold from producing a Sharpe of 0 or inf that
    would dominate the mean.
  * If fewer than 2 folds survive, raise ValueError so the caller can
    fall back to a single-pass evaluation with a warning flag.
"""
from __future__ import annotations

import pandas as pd

MIN_EVENTS_PER_FOLD = 5


def split_walk_forward(
    event_dates: pd.DatetimeIndex,
    n_folds: int = 4,
    embargo_days: int = 2,
) -> list[pd.DatetimeIndex]:
    """Chronological K-fold partitioning with embargo.

    Returns a list of K test folds (each a `pd.DatetimeIndex`) sorted
    ascending. Folds with fewer than `MIN_EVENTS_PER_FOLD` events after
    embargo are dropped. Raises ValueError if fewer than 2 folds
    survive.

    Parameters
    ----------
    event_dates : pd.DatetimeIndex
        Regime-filtered event dates. May be unsorted / contain
        duplicates; both are handled.
    n_folds : int
        Number of contiguous chunks. Default 4 per spec §6.
    embargo_days : int
        Number of leading events to drop from each fold after the first.
        Caller should pass `max(2, hold_horizon)` to guarantee no trade
        opened in fold k-1 reaches into fold k's events. Default 2.

    Notes
    -----
    This is K-fold time-series cross-validation for Sharpe estimation,
    NOT purged walk-forward in the ML sense. Our DSL rules have no
    trainable parameters so "train" is conceptually unused; we return
    test folds only and the caller computes a per-fold Sharpe then
    aggregates.
    """
    if n_folds < 2:
        raise ValueError(f"n_folds must be >= 2; got {n_folds}")
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0; got {embargo_days}")

    sorted_dates = pd.DatetimeIndex(
        sorted(pd.DatetimeIndex(event_dates).unique())
    )
    n = len(sorted_dates)
    if n < 2:
        raise ValueError(
            "insufficient events for K-fold Sharpe estimation "
            f"(got {n}, need >= 2)"
        )

    folds: list[pd.DatetimeIndex] = []
    for k in range(n_folds):
        lo = k * n // n_folds
        hi = (k + 1) * n // n_folds
        chunk = sorted_dates[lo:hi]
        # Embargo: drop leading events from every fold after the first.
        if k > 0 and embargo_days > 0:
            chunk = chunk[embargo_days:]
        if len(chunk) < MIN_EVENTS_PER_FOLD:
            continue
        folds.append(chunk)

    if len(folds) < 2:
        raise ValueError(
            "insufficient events for K-fold Sharpe estimation "
            f"(only {len(folds)} folds survived with >= "
            f"{MIN_EVENTS_PER_FOLD} events each; need >= 2)"
        )
    return folds
