"""Daily peer-residual returns ε_s(t) per H-2026-04-25-001 §4.1.

Assumes prices have passed `anka_data_validation_policy_global_standard` §9
cleanliness gates — no zero / negative ticks reach this module.

Cohort semantics are frozen ex-ante in `peers_frozen.json` and govern this
module's behaviour:
- `min_peers = 1` is the spec-locked floor (see `peers_frozen.json :: lineage`).
  Symbols whose cohort collapses to zero surviving peers on a given date emit
  NaN; cohorts of size 1+ are treated as the cohort.
- `mean(axis=1)` uses pandas default `skipna=True`, so an interior NaN in one
  peer's series (halt, suspension) is absorbed by the surviving peers. This
  matches the frozen-cohort contract: peers list is locked, daily availability
  is what the data shows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily log-returns; first row is NaN by construction."""
    return np.log(prices / prices.shift(1))


def compute_residual_panel(
    log_returns: pd.DataFrame,
    peers_map: dict[str, list[str]],
) -> pd.DataFrame:
    """ε_s(t) = r_s(t) − mean_{p ∈ peers(s) ∩ available}(r_p(t)).

    See module docstring for cohort-availability semantics (min_peers=1, skipna=True).
    """
    out = pd.DataFrame(index=log_returns.index, columns=list(peers_map.keys()), dtype=float)
    for sym, peers in peers_map.items():
        if sym not in log_returns.columns:
            continue
        available = [p for p in peers if p in log_returns.columns]
        if not available:
            continue
        peer_mean = log_returns[available].mean(axis=1)
        out[sym] = log_returns[sym] - peer_mean
    return out
