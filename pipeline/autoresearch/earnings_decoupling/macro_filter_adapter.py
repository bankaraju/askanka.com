"""Adapter wrapping pipeline/earnings_calendar/macro_filter for earnings_decoupling.

Returns (excluded: bool, reason: str | None) where reason is one of
SECTOR_T, SECTOR_T1, VIX_SHOCK, or None when not excluded.
"""
from __future__ import annotations

import pandas as pd

from pipeline.earnings_calendar.macro_filter import (
    INDEX_MOVE_THRESHOLD,
    VIX_ZSCORE_THRESHOLD,
    VIX_ZSCORE_LOOKBACK_DAYS,
)


def compute_index_returns_panel(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change()


def _vix_z(vix: pd.Series, on: pd.Timestamp) -> float | None:
    if on not in vix.index:
        return None
    pos = vix.index.get_loc(on)
    if pos < VIX_ZSCORE_LOOKBACK_DAYS:
        return None
    window = vix.iloc[pos - VIX_ZSCORE_LOOKBACK_DAYS:pos]
    if window.std(ddof=1) == 0:
        return None
    return float((vix.iloc[pos] - window.mean()) / window.std(ddof=1))


def is_event_macro_excluded(
    *,
    event_date,
    sector_index_returns: pd.Series,
    india_vix: pd.Series,
) -> tuple[bool, str | None]:
    ts = pd.Timestamp(event_date).normalize()
    rets_idx = sector_index_returns.index.normalize()
    rets = sector_index_returns.copy()
    rets.index = rets_idx
    if ts in rets.index:
        r_t = rets.loc[ts]
        if pd.notna(r_t) and abs(r_t) >= INDEX_MOVE_THRESHOLD:
            return (True, "SECTOR_T")
        pos = rets.index.get_loc(ts)
        if pos + 1 < len(rets):
            r_t1 = rets.iloc[pos + 1]
            if pd.notna(r_t1) and abs(r_t1) >= INDEX_MOVE_THRESHOLD:
                return (True, "SECTOR_T1")
    vix_idx = india_vix.index.normalize()
    vix = india_vix.copy()
    vix.index = vix_idx
    z = _vix_z(vix, ts)
    if z is not None and z >= VIX_ZSCORE_THRESHOLD:
        return (True, "VIX_SHOCK")
    return (False, None)
