"""§7.3 entry-timing audit hook.

For each trade emit lag = filled_at - signal_decidable_at. Fail if any lag < 0,
or (in MODE B/C) any lag < 30 min.
"""
from __future__ import annotations

from enum import Enum

import pandas as pd


class EntryMode(str, Enum):
    A = "eod_close"
    B = "morning_settled_30min"
    C = "intraday_t_plus_5"


def audit_entry_timing(trades: pd.DataFrame, mode: EntryMode) -> dict:
    """Return ``{pass, n_lag_negative, n_lag_under_30min, median_lag_seconds, mode}``.

    A negative lag (fill before signal) is ALWAYS a fail. In MODE B / MODE C, a
    positive lag below 30 minutes is also a fail (sub-30min execution is
    treated as non-realistic for those modes per §7.3). MODE A skips the
    sub-30min check.

    Raises ValueError if either required column is missing.
    """
    required = {"signal_decidable_at", "filled_at"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(
            f"trades missing required columns {sorted(missing)}; got {list(trades.columns)}"
        )
    lag = trades["filled_at"] - trades["signal_decidable_at"]
    n_neg = int((lag < pd.Timedelta(0)).sum())
    n_too_close = (
        int(((lag >= pd.Timedelta(0)) & (lag < pd.Timedelta(minutes=30))).sum())
        if mode in (EntryMode.B, EntryMode.C)
        else 0
    )
    return {
        "pass": (n_neg == 0) and (n_too_close == 0),
        "n_lag_negative": n_neg,
        "n_lag_under_30min": n_too_close,
        "median_lag_seconds": float(lag.dt.total_seconds().median()),
        "mode": mode.value,
    }
