"""§6.3 marker: held-fixed exit rule sanity check.

Phase 2 holds the exit rule fixed at TIME_STOP 14:30 unless explicitly testing
alternatives. This module exposes the swap point so a single call site picks
the realized return column.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class ExitRule(str, Enum):
    TIME_STOP_1430 = "time_stop_1430"
    CLOSE          = "close"


def apply_fixed_exit_rule(events: pd.DataFrame, rule: ExitRule) -> pd.DataFrame:
    """Set ``realized_pct`` from ``open_to_1430_pct`` or ``open_to_close_pct``.

    Raises ValueError if the required source column is missing OR if ``rule``
    is unrecognised.
    """
    required = "open_to_1430_pct" if rule == ExitRule.TIME_STOP_1430 else "open_to_close_pct"
    if required not in events.columns:
        raise ValueError(
            f"apply_fixed_exit_rule({rule}): column '{required}' not found; "
            f"available: {list(events.columns)}"
        )
    out = events.copy()
    if rule == ExitRule.TIME_STOP_1430:
        out["realized_pct"] = events["open_to_1430_pct"]
    elif rule == ExitRule.CLOSE:
        out["realized_pct"] = events["open_to_close_pct"]
    else:
        raise ValueError(f"unknown exit rule {rule}")
    return out
