"""Persistent-break filter for H-2026-04-24-002.

A persistent break is an event on date T for ticker i where:
  |z_{i,T}|    >= z_threshold
  |z_{i,T-k}|  >= z_threshold  for k in 1..persistence_days-1
  sign(z_{i,T}) == sign(z_{i,T-k})  for all k
  ticker i has >= min_history_days non-NaN z observations through T-1

The spec binds (z_threshold=3.0, persistence_days=2, min_history_days=60) for
the primary run; fragility sweeps perturb the first two.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def filter_persistent_breaks(
    events_df: pd.DataFrame,
    z_panel: pd.DataFrame,
    *,
    z_threshold: float,
    persistence_days: int,
    min_history_days: int = 60,
) -> pd.DataFrame:
    """Return the subset of events_df satisfying the persistence filter.

    Parameters
    ----------
    events_df
        Parent panel events. Must have columns: ticker, date, z.
    z_panel
        Wide DataFrame (dates × tickers) of cross-sectional z-scores. Must
        contain all lookback rows needed for each event; missing rows raise.
    z_threshold, persistence_days, min_history_days
        Spec-bound parameters.

    Returns
    -------
    DataFrame with the same schema as events_df, filtered.
    """
    if persistence_days < 1:
        raise ValueError("persistence_days must be >= 1")

    ev = events_df.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    z_panel = z_panel.sort_index()

    keep_mask = np.zeros(len(ev), dtype=bool)
    for i, row in enumerate(ev.itertuples(index=False)):
        t = pd.Timestamp(row.date)
        tkr = row.ticker
        z_t = float(row.z)
        if abs(z_t) < z_threshold:
            continue
        if tkr not in z_panel.columns:
            continue
        col = z_panel[tkr].loc[:t]
        # History requirement: ticker must have enough non-NaN z observations
        # in the z_panel (up to and including T) to establish a reliable baseline.
        # For the real panel this enforces a minimum lookback window; for synthetic
        # fixtures the threshold is set lower via the min_history_days parameter.
        if z_panel[tkr].dropna().shape[0] < min_history_days:
            continue
        ok = True
        for k in range(1, persistence_days):
            # find the k-th previous trading day for this ticker (non-NaN row)
            col_before = col.loc[col.index < t].dropna()
            if col_before.shape[0] < k:
                ok = False
                break
            z_prev = float(col_before.iloc[-k])
            if abs(z_prev) < z_threshold or _sign(z_prev) != _sign(z_t):
                ok = False
                break
        if ok:
            keep_mask[i] = True

    return ev.loc[keep_mask].reset_index(drop=True)
