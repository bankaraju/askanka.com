"""Slippage-stress grid per §1 of backtesting-specs.txt v1.0.

Subtracts a flat round-trip cost in percent-return space from every
event's gross trade return. The ledger format assumed:
    ticker, direction, trade_ret_pct  (percent, signed by direction)
Where trade_ret_pct already encodes the strategy's sign:
  fade-UP (SHORT) → positive when next-day close fell.
"""
from __future__ import annotations

import pandas as pd

# round-trip cost in percent (10 bps, 30 bps, 50 bps, 70 bps)
LEVELS: dict[str, float] = {
    "S0": 0.10,
    "S1": 0.30,
    "S2": 0.50,
    "S3": 0.70,
}


def apply_level(ledger: pd.DataFrame, level: str) -> pd.DataFrame:
    cost = LEVELS[level]
    out = ledger.copy()
    out["slippage_level"] = level
    out["cost_pct"] = cost
    out["net_ret_pct"] = out["trade_ret_pct"] - cost
    return out


def apply_full_grid(ledger: pd.DataFrame) -> pd.DataFrame:
    frames = [apply_level(ledger, lvl) for lvl in LEVELS]
    return pd.concat(frames, ignore_index=True)
