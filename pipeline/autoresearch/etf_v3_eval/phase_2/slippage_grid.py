"""§1.1 slippage levels + §1.2 fill simulator + §3 pass/fail.

Round-trip cost (subtract from gross_pnl_pct):
- S0: 10 bps  (5 per side)
- S1: 30 bps  (15 per side)
- S2: 50 bps  (25 per side)
- S3: 70 bps  (35 per side, informational only)
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class SlippageLevel(str, Enum):
    S0 = "s0"
    S1 = "s1"
    S2 = "s2"
    S3 = "s3"


ROUND_TRIP_COST = {
    SlippageLevel.S0: 0.0010,
    SlippageLevel.S1: 0.0030,
    SlippageLevel.S2: 0.0050,
    SlippageLevel.S3: 0.0070,
}


PASS_THRESHOLDS = {
    SlippageLevel.S0: {"sharpe": 1.0, "hit_rate": 0.55, "max_dd": 0.20},
    SlippageLevel.S1: {"sharpe": 0.8, "hit_rate": 0.50, "max_dd": 0.25},
    SlippageLevel.S2: {"sharpe": 0.5, "hit_rate": 0.45, "max_dd": 0.30},
}


def apply_slippage(events: pd.DataFrame, level: SlippageLevel) -> pd.DataFrame:
    """Subtract round-trip slippage from gross_pnl_pct.

    Raises ValueError if ``gross_pnl_pct`` column is missing.
    """
    if "gross_pnl_pct" not in events.columns:
        raise ValueError(
            f"apply_slippage: column 'gross_pnl_pct' not found; "
            f"available: {list(events.columns)}"
        )
    out = events.copy()
    out["net_pnl_pct"] = events["gross_pnl_pct"] - ROUND_TRIP_COST[level]
    return out


def evaluate_pass_fail(metrics: dict, level: SlippageLevel) -> dict:
    """Return ``{pass: bool, failures: [str], level: str}`` per §3 thresholds.

    S3 is informational only — always returns ``pass=True`` with an extra
    ``informational=True`` flag so callers can route reporting differently.
    Required keys in ``metrics``: ``sharpe``, ``hit_rate``, ``max_dd``.
    """
    if level == SlippageLevel.S3:
        return {"pass": True, "failures": [], "level": level.value, "informational": True}
    for required in ("sharpe", "hit_rate", "max_dd"):
        if required not in metrics:
            raise ValueError(f"evaluate_pass_fail: metrics missing key '{required}'")
    th = PASS_THRESHOLDS[level]
    failures = []
    if metrics["sharpe"] < th["sharpe"]:
        failures.append("sharpe")
    if metrics["hit_rate"] < th["hit_rate"]:
        failures.append("hit_rate")
    if metrics["max_dd"] > th["max_dd"]:
        failures.append("max_dd")
    return {"pass": not failures, "failures": failures, "level": level.value}
