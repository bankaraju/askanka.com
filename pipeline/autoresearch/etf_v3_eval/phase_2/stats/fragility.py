"""§9A.2 — three stability conditions for parameter neighborhood.

Verdict STABLE iff ALL three hold:
- ≥ 60% of neighbors have positive net P&L
- median neighbor Sharpe ≥ 70% of chosen-point Sharpe
- < 50% of neighbors exhibit opposite-direction sign vs chosen

Edge cases:
- chosen_pnl == 0: np.sign(0) == 0, so inversion test compares against 0.
  Any neighbour with nonzero sign will be counted as "inverted". Document
  and leave as-is; callers should avoid chosen_pnl == 0 exactly.
- chosen_sharpe == 0: median_sharpe_ratio returns 0.0 → fails cond_b →
  FRAGILE. Guarded with explicit zero check.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import numpy as np


class FragilityVerdict(str, Enum):
    STABLE = "stable"
    FRAGILE = "fragile"


@dataclass(frozen=True)
class FragilityReport:
    verdict: FragilityVerdict
    pct_positive: float
    median_sharpe_ratio: float
    pct_inverted: float


def evaluate_fragility(
    chosen_pnl: float,
    neighbor_pnls: Sequence[float],
    chosen_sharpe: float,
    neighbor_sharpes: Sequence[float],
) -> FragilityReport:
    """Compute the §9A.2 stability verdict over a parameter neighborhood."""
    n_pnls = np.asarray(neighbor_pnls, dtype=float)
    n_sh = np.asarray(neighbor_sharpes, dtype=float)
    pct_positive = float((n_pnls > 0).mean())
    median_sharpe_ratio = float(np.median(n_sh) / chosen_sharpe) if chosen_sharpe else 0.0
    pct_inverted = float((np.sign(n_pnls) != np.sign(chosen_pnl)).mean())
    cond_a = pct_positive >= 0.60
    cond_b = median_sharpe_ratio >= 0.70
    cond_c = pct_inverted < 0.50
    verdict = FragilityVerdict.STABLE if (cond_a and cond_b and cond_c) else FragilityVerdict.FRAGILE
    return FragilityReport(verdict, pct_positive, median_sharpe_ratio, pct_inverted)
