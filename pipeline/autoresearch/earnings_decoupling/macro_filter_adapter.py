"""Adapter wrapping pipeline/earnings_calendar/macro_filter for earnings_decoupling.

Returns (excluded: bool, reason: str | None) where reason is one of
SECTOR_T, SECTOR_T1, VIX_SHOCK, or None when not excluded.

Rule logic lives in `pipeline.earnings_calendar.macro_filter.classify_macro_exclusion`;
this adapter only normalises the input panels' DatetimeIndex (strip tz,
midnight-align) and tuple-wraps the (excluded, reason) return shape that
the backtest event ledger expects. Keeping the rule in exactly one place
prevents drift between the live macro gate and the backtest's exclusion
classifier.
"""
from __future__ import annotations

import pandas as pd

from pipeline.earnings_calendar.macro_filter import classify_macro_exclusion


def _normalize_event_date(event_date) -> pd.Timestamp:
    ts = pd.Timestamp(event_date)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def _normalize_series_index(s: pd.Series) -> pd.Series:
    out = s.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        return out
    out.index = out.index.tz_localize(None) if out.index.tz is not None else out.index
    out.index = out.index.normalize()
    return out


def compute_index_returns_panel(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change()


def is_event_macro_excluded(
    *,
    event_date,
    sector_index_returns: pd.Series,
    india_vix: pd.Series,
) -> tuple[bool, str | None]:
    ts = _normalize_event_date(event_date)
    rets = _normalize_series_index(sector_index_returns)
    vix = _normalize_series_index(india_vix)
    reason = classify_macro_exclusion(
        event_date=ts.date(),
        index_returns=rets,
        india_vix=vix,
    )
    return (reason is not None, reason)
