"""Trigger z-score per H-2026-04-25-001 §4.2-§4.3.

Spec: `docs/superpowers/specs/2026-04-25-earnings-decoupling-hypothesis-design.md`

## Baseline rolling-window interpretation

The pre-registered spec describes the baseline as "trailing 252-day distribution
ending T-8 of cum_residual values". Two readings are statistically equivalent
under stationarity but have different slice positions:

- **Spec literal**: rolling samples represent `cum_residual(s, u) = sum over
  [u-7, u-3]` for `u ∈ [T-260, T-8]`; the most recent sample's window is
  [T-15, T-11].
- **This implementation**: rolling 5-day sums at slice positions
  `[T-260, T-8]`; the most recent sample's window is [T-12, T-8].

The implementation choice is documented for the verdict trail. Both readings
exclude the trigger window [T-7, T-3] from the baseline (look-ahead clean).
Choice was locked into the verbatim plan at commit 80ba799 and is preserved
here without re-litigation post-pre-registration.

## NaN / calendar semantics

`rolling(5).sum()` runs over the raw 252-day baseline slice WITHOUT pre-dropna,
so each rolling sample represents a 5-trading-day calendar window — matching
the observation side (`cum_residual_window` sums over an inclusive
trading-day calendar slice). The post-rolling `dropna()` only trims windows
where ≥1 of the 5 days had no data. This avoids the "10-day suspension
straddled as if it never happened" failure mode.

## event_date type contract

`event_date` may be a string (ISO-8601), `datetime.date`, or `pd.Timestamp`.
It is normalized to midnight tz-naive before index lookup; the panel index
must also be tz-naive midnight (typical for EODHD/Kite daily bars).
"""
from __future__ import annotations

import pandas as pd

WINDOW_START = -7
WINDOW_END = -3
BASELINE_LEN = 252
BASELINE_END_OFFSET = -8
MIN_BASELINE_DAYS = 200
MIN_ROLLING_SAMPLES = 50


def _normalize_event_date(event_date) -> pd.Timestamp:
    return pd.Timestamp(event_date).tz_localize(None).normalize()


def cum_residual_window(
    residual_panel: pd.DataFrame, symbol: str, event_date,
    *, start_offset: int = WINDOW_START, end_offset: int = WINDOW_END,
) -> float:
    if symbol not in residual_panel.columns:
        return float("nan")
    idx = residual_panel.index.get_loc(_normalize_event_date(event_date))
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
    target = _normalize_event_date(event_date)
    if target not in residual_panel.index:
        return None
    idx = residual_panel.index.get_loc(target)
    if idx + baseline_end_offset < 0:
        return None

    cum_obs = cum_residual_window(
        residual_panel, symbol, event_date,
        start_offset=start_offset, end_offset=end_offset,
    )

    window_len = end_offset - start_offset + 1
    baseline_end_idx = idx + baseline_end_offset
    baseline_start_idx = max(0, baseline_end_idx - baseline_len + 1)
    baseline_slice = residual_panel[symbol].iloc[baseline_start_idx:baseline_end_idx + 1]
    if baseline_slice.dropna().shape[0] < min_baseline_days:
        return None

    rolling_cum = baseline_slice.rolling(window=window_len).sum().dropna()
    if len(rolling_cum) < MIN_ROLLING_SAMPLES:
        return None
    sigma = float(rolling_cum.std(ddof=1))
    mu = float(rolling_cum.mean())
    if sigma <= 0:
        return None
    return (cum_obs - mu) / sigma
