"""Macro-exclusion gate for H-2026-04-25-001.

User-locked rule (2026-04-25): exclude an earnings event when

    |sector_index_return| >= 1.5%  on event_day OR T+1
    OR
    india_vix_z(60d) >= 2.0  on event_day.

Thresholds are pre-registered constants. Do NOT calibrate them from
observed data — the data validation policy §3.6 forbids retroactive
threshold loosening, and the backtesting policy §0.3 forbids redefining
success criteria after observation."""
from __future__ import annotations

import datetime as dt

import pandas as pd

INDEX_MOVE_THRESHOLD = 0.015
VIX_ZSCORE_THRESHOLD = 2.0
VIX_ZSCORE_LOOKBACK_DAYS = 60


def _index_return_on(returns: pd.Series, day: dt.date) -> float | None:
    ts = pd.Timestamp(day)
    if ts not in returns.index:
        return None
    return float(returns.loc[ts])


def _vix_zscore_on(vix: pd.Series, day: dt.date) -> float | None:
    ts = pd.Timestamp(day)
    if ts not in vix.index:
        return None
    pos = vix.index.get_loc(ts)
    if pos < VIX_ZSCORE_LOOKBACK_DAYS:
        return None
    window = vix.iloc[pos - VIX_ZSCORE_LOOKBACK_DAYS:pos]
    mu = float(window.mean())
    sd = float(window.std(ddof=1))
    if sd <= 0:
        return None
    return (float(vix.iloc[pos]) - mu) / sd


def is_macro_excluded(
    *,
    event_date: dt.date,
    index_returns: pd.Series,
    india_vix: pd.Series,
) -> bool:
    """Return True iff any of the three pre-registered macro conditions
    is breached on event_day or T+1.

    Missing index/vix data on a queried date is NOT treated as an
    exclusion — the caller is expected to handle absent-data events
    explicitly (data validation policy §9.3 quarantine pattern). A
    missing series silently returning False here would be safe but
    misleading; an over-eager True would corrupt the event count."""
    ts = pd.Timestamp(event_date)
    if ts in index_returns.index:
        pos = index_returns.index.get_loc(ts)
        t1_date = (
            index_returns.index[pos + 1].date()
            if pos + 1 < len(index_returns)
            else event_date
        )
        r_t = _index_return_on(index_returns, event_date)
        r_t1 = _index_return_on(index_returns, t1_date)
        if r_t is not None and abs(r_t) >= INDEX_MOVE_THRESHOLD:
            return True
        if r_t1 is not None and abs(r_t1) >= INDEX_MOVE_THRESHOLD:
            return True

    z = _vix_zscore_on(india_vix, event_date)
    if z is not None and z >= VIX_ZSCORE_THRESHOLD:
        return True
    return False
