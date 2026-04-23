# -*- coding: utf-8 -*-
"""Naive benchmarks per §9B.1.

On the same event set, compute random-direction, equal-weight basket, and
momentum (follow instead of fade) P&L. The registered strategy (fade) must
beat the STRONGEST of these at S0 on the primary metric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M


def _row(returns_pct: np.ndarray, annualisation_factor: int = 252) -> dict:
    core = M.per_bucket_metrics(returns_pct, annualisation_factor=annualisation_factor)
    return {
        "mean_ret_pct": core["mean_ret_pct"],
        "sharpe": core["sharpe"],
        "hit_rate": core["hit_rate"],
        "n_trades": core["n_trades"],
    }


def random_direction(events: pd.DataFrame, seed: int | None = 42) -> dict:
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1, 1], size=len(events))
    rets = events["next_ret"].to_numpy() * signs
    return _row(rets)


def equal_weight_basket(events: pd.DataFrame) -> dict:
    rets = events["next_ret"].to_numpy()
    return _row(rets)


def momentum_follow(events: pd.DataFrame) -> dict:
    signs = np.where(events["z"].to_numpy() > 0, 1.0, -1.0)
    rets = events["next_ret"].to_numpy() * signs
    return _row(rets)


def run_suite(events: pd.DataFrame, seed: int | None = 42) -> dict:
    return {
        "random_direction": random_direction(events, seed=seed),
        "equal_weight_basket": equal_weight_basket(events),
        "momentum_follow": momentum_follow(events),
    }
