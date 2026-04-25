"""Daily peer-residual returns ε_s(t) per H-2026-04-25-001 §4.1."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices / prices.shift(1))


def compute_residual_panel(
    log_returns: pd.DataFrame,
    peers_map: dict[str, list[str]],
) -> pd.DataFrame:
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
