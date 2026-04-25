"""Trigger z-score per H-2026-04-25-001 §4.2-§4.3."""
from __future__ import annotations

import pandas as pd

WINDOW_START = -7
WINDOW_END = -3
BASELINE_LEN = 252
BASELINE_END_OFFSET = -8
MIN_BASELINE_DAYS = 200


def cum_residual_window(
    residual_panel: pd.DataFrame, symbol: str, event_date,
    *, start_offset: int = WINDOW_START, end_offset: int = WINDOW_END,
) -> float:
    if symbol not in residual_panel.columns:
        return float("nan")
    idx = residual_panel.index.get_loc(pd.Timestamp(event_date))
    lo = max(0, idx + start_offset)
    hi = max(0, idx + end_offset + 1)
    return float(residual_panel[symbol].iloc[lo:hi].sum())


def compute_trigger_z(
    residual_panel: pd.DataFrame, symbol: str, event_date,
    *, baseline_len: int = BASELINE_LEN,
    baseline_end_offset: int = BASELINE_END_OFFSET,
    min_baseline_days: int = MIN_BASELINE_DAYS,
    start_offset: int = WINDOW_START,
    end_offset: int = WINDOW_END,
) -> float | None:
    if symbol not in residual_panel.columns:
        return None
    if pd.Timestamp(event_date) not in residual_panel.index:
        return None
    idx = residual_panel.index.get_loc(pd.Timestamp(event_date))
    if idx + baseline_end_offset < 0:
        return None

    cum_obs = cum_residual_window(
        residual_panel, symbol, event_date,
        start_offset=start_offset, end_offset=end_offset,
    )

    window_len = end_offset - start_offset + 1
    baseline_end_idx = idx + baseline_end_offset
    baseline_start_idx = max(0, baseline_end_idx - baseline_len + 1)
    baseline_residuals = residual_panel[symbol].iloc[baseline_start_idx:baseline_end_idx + 1].dropna()
    if len(baseline_residuals) < min_baseline_days:
        return None

    rolling_cum = baseline_residuals.rolling(window=window_len).sum().dropna()
    if len(rolling_cum) < 50:
        return None
    sigma = float(rolling_cum.std(ddof=1))
    mu = float(rolling_cum.mean())
    if sigma <= 0:
        return None
    return (cum_obs - mu) / sigma
