"""§8 direction audit — compare strategy direction vs opposite-direction Sharpe.

If opposite-direction Sharpe at S0 exceeds strategy Sharpe → DIRECTION-SUSPECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

_REQUIRED_COLUMNS = {"realized_pct", "side"}


class DirectionVerdict(str, Enum):
    ALIGNED = "aligned"
    SUSPECT = "suspect"


@dataclass(frozen=True)
class DirectionReport:
    verdict: DirectionVerdict
    strategy_mean: float
    strategy_sharpe: float
    opposite_mean: float
    opposite_sharpe: float


def direction_audit(events: pd.DataFrame, annualization: int = 252) -> DirectionReport:
    """Compare strategy Sharpe to the opposite-direction counterfactual.

    Parameters
    ----------
    events:
        DataFrame with at least ``realized_pct`` (float) and ``side``
        (str, ``"LONG"`` or ``"SHORT"``) columns.
    annualization:
        Annualization factor for Sharpe calculation (default 252 trading days).

    Returns
    -------
    DirectionReport
        verdict is SUSPECT when opposite-direction Sharpe > strategy Sharpe.

    Raises
    ------
    ValueError
        If ``realized_pct`` or ``side`` columns are missing.
    ValueError
        If ``side`` contains values other than ``"LONG"`` or ``"SHORT"``.
    """
    # Required-column guard
    missing = _REQUIRED_COLUMNS - set(events.columns)
    if missing:
        raise ValueError(
            f"events missing required columns {sorted(missing)}; got {list(events.columns)}"
        )

    sign = events["side"].map({"LONG": 1.0, "SHORT": -1.0})

    # Unrecognized-side guard — map() silently produces NaN for unknown values
    if sign.isna().any():
        bad = sorted(events.loc[sign.isna(), "side"].unique().tolist())
        raise ValueError(
            f"side column contains unrecognized values {bad}; expected 'LONG' or 'SHORT'"
        )

    strat = events["realized_pct"] * sign
    opp = -strat

    s_mean = float(strat.mean())
    o_mean = float(opp.mean())

    # Use max(..., 1e-12) to avoid boolean-coercion edge cases with `or 1e-12`
    s_sd = max(float(strat.std(ddof=1)), 1e-12)
    o_sd = max(float(opp.std(ddof=1)), 1e-12)

    s_sharpe = (s_mean / s_sd) * np.sqrt(annualization)
    o_sharpe = (o_mean / o_sd) * np.sqrt(annualization)

    verdict = DirectionVerdict.SUSPECT if o_sharpe > s_sharpe else DirectionVerdict.ALIGNED
    return DirectionReport(verdict, s_mean, s_sharpe, o_mean, o_sharpe)
