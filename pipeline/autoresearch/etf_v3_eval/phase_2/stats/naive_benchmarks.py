"""§9B.1 — naive comparators required for every strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd


def always_long(events: pd.DataFrame) -> pd.DataFrame:
    """benchmark_pnl = realized return of every event (long every signal)."""
    out = events.copy()
    out["benchmark_pnl"] = events["realized_pct"]
    return out


def always_short(events: pd.DataFrame) -> pd.DataFrame:
    """benchmark_pnl = negated realized return (short every signal)."""
    out = events.copy()
    out["benchmark_pnl"] = -events["realized_pct"]
    return out


def never_trade(events: pd.DataFrame) -> pd.DataFrame:
    """benchmark_pnl = 0 (cash, no trades)."""
    out = events.copy()
    out["benchmark_pnl"] = 0.0
    return out


def random_direction(events: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """benchmark_pnl = realized × random ±1 (Bernoulli-coin direction).

    The ``rng`` is REQUIRED (not optional) so the call site is responsible for
    seeding — Phase 2 always pins seeds via the §13A.1 manifest.
    """
    out = events.copy()
    sign = rng.choice([-1.0, 1.0], size=len(events))
    out["benchmark_pnl"] = events["realized_pct"].to_numpy() * sign
    return out
