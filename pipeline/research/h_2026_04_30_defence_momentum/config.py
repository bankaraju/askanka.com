"""Hypothesis-pack config for the Defence momentum bundle.

Two locked configs — DO NOT mutate during holdout (single_touch_locked).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class HypothesisConfig:
    hypothesis_id: str
    short_id: str  # used for basket_id prefix
    long_legs: tuple[str, ...]
    short_legs: tuple[str, ...]
    regime_gate: str
    hold_trading_days: int
    stop_bps: float       # negative number, e.g. -250.0 for -2.5%
    cost_rt_bps: float
    holdout_start: date
    holdout_end: date
    cap_x_baseline: Optional[float]  # None = no cap; 2.0 = AUTO-RISKON variant


CONFIGS: tuple[HypothesisConfig, ...] = (
    HypothesisConfig(
        hypothesis_id="H-2026-04-30-DEFENCE-IT-NEUTRAL",
        short_id="DEFIT",
        long_legs=("HAL", "BEL", "BDL"),
        short_legs=("TCS", "INFY", "WIPRO"),
        regime_gate="NEUTRAL",
        hold_trading_days=5,
        stop_bps=-250.0,
        cost_rt_bps=20.0,
        holdout_start=date(2026, 5, 1),
        holdout_end=date(2027, 4, 30),
        cap_x_baseline=None,
    ),
    HypothesisConfig(
        hypothesis_id="H-2026-04-30-DEFENCE-AUTO-RISKON",
        short_id="DEFAU",
        long_legs=("HAL", "BEL"),
        short_legs=("TMPV", "MARUTI"),
        regime_gate="RISK-ON",
        hold_trading_days=5,
        stop_bps=-250.0,
        cost_rt_bps=20.0,
        holdout_start=date(2026, 5, 1),
        holdout_end=date(2027, 4, 30),
        cap_x_baseline=2.0,
    ),
)


def get_config(short_id: str) -> HypothesisConfig:
    for c in CONFIGS:
        if c.short_id == short_id:
            return c
    raise ValueError(f"unknown short_id {short_id!r}; must be one of {[c.short_id for c in CONFIGS]}")
