"""§9B.1 naive benchmarks for the FOLLOW-DIRECTION earnings strategy.

Diverges from overshoot_compliance.naive_comparators (which models the FADE
strategy) because momentum_follow there equals our strategy.

Comparators:
- random_direction: random sign × next_ret on the same gated event set
- equal_weight_basket: just next_ret (long-bias bet on every event passing the trigger)
- fade_inverse: -sign(z) × next_ret — the opposite-direction strategy on the same
  event set. Pass condition (§9B.1): our strategy must beat the strongest of these
  at S0 on mean_ret_pct.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.overshoot_compliance import metrics as M


def _row(returns_pct: np.ndarray) -> dict:
    core = M.per_bucket_metrics(returns_pct)
    return {
        "mean_ret_pct": core["mean_ret_pct"],
        "sharpe": core["sharpe"],
        "hit_rate": core["hit_rate"],
        "n_trades": core["n_trades"],
    }


def random_direction(events: pd.DataFrame, seed: int | None = 42) -> dict:
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1, 1], size=len(events))
    return _row(events["next_ret"].to_numpy() * signs)


def equal_weight_basket(events: pd.DataFrame) -> dict:
    return _row(events["next_ret"].to_numpy())


def fade_inverse(events: pd.DataFrame) -> dict:
    signs = np.where(events["z"].to_numpy() > 0, -1.0, 1.0)
    return _row(events["next_ret"].to_numpy() * signs)


def run_suite(events: pd.DataFrame, seed: int | None = 42) -> dict:
    return {
        "random_direction": random_direction(events, seed=seed),
        "equal_weight_basket": equal_weight_basket(events),
        "fade_inverse": fade_inverse(events),
    }
