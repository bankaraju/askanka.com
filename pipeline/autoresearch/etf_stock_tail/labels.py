"""3-class σ-thresholded tail labels per (ticker, date).

Public API:
  label_for_date(bars, eval_date) -> float  (NaN if ineligible)  — single date
  label_series(bars) -> pd.Series  — labels for every eligible date in bars

Eligibility: requires ≥ SIGMA_LOOKBACK_DAYS prior closes excluding t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def _classify(r: float, sigma: float) -> int:
    if pd.isna(r) or pd.isna(sigma) or sigma == 0:
        return -1  # sentinel, caller maps to NaN
    if r > C.SIGMA_THRESHOLD * sigma:
        return C.CLASS_UP
    if r < -C.SIGMA_THRESHOLD * sigma:
        return C.CLASS_DOWN
    return C.CLASS_NEUTRAL


def label_for_date(bars: pd.DataFrame, eval_date: pd.Timestamp) -> float:
    """Return label for eval_date; NaN if insufficient history."""
    eval_date = pd.Timestamp(eval_date)
    bars_sorted = bars.sort_values("date").reset_index(drop=True)
    idx = bars_sorted.index[bars_sorted["date"] == eval_date]
    if len(idx) == 0:
        return float("nan")
    i = int(idx[0])
    if i < 1:
        return float("nan")
    prior = bars_sorted.iloc[: i].tail(C.SIGMA_LOOKBACK_DAYS)
    if len(prior) < C.SIGMA_LOOKBACK_DAYS:
        return float("nan")
    rets_prior = prior["close"].pct_change().dropna().values
    sigma = float(np.std(rets_prior, ddof=1)) if len(rets_prior) >= 2 else float("nan")
    r_t = float(bars_sorted.loc[i, "close"] / bars_sorted.loc[i - 1, "close"] - 1.0)
    label = _classify(r_t, sigma)
    return float(label) if label >= 0 else float("nan")


def label_series(bars: pd.DataFrame) -> pd.Series:
    """Vectorised label per date. NaN where ineligible."""
    bars_sorted = bars.sort_values("date").reset_index(drop=True)
    out = pd.Series(np.nan, index=bars_sorted["date"].values, name="label", dtype="float64")
    closes = bars_sorted["close"].values
    rets_full = pd.Series(closes).pct_change().values
    for i in range(1, len(bars_sorted)):
        prior = rets_full[max(0, i - (C.SIGMA_LOOKBACK_DAYS - 1)): i]
        prior = prior[~np.isnan(prior)]
        if len(prior) < C.SIGMA_LOOKBACK_DAYS - 1:
            continue  # need ≥ SIGMA_LOOKBACK_DAYS-1 returns from SIGMA_LOOKBACK_DAYS prior closes
        sigma = float(np.std(prior, ddof=1))
        r_t = float(closes[i] / closes[i - 1] - 1.0)
        lbl = _classify(r_t, sigma)
        if lbl >= 0:
            out.iloc[i] = lbl
    return out
