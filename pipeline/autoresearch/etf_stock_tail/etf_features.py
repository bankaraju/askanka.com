"""ETF feature builder — 30 ETFs × {ret_1d, ret_5d, ret_20d} = 90 features, causal.

Every feature at eval_date t uses only rows where date < t (strict inequality).
Unit-test `test_etf_features.py` asserts this pointwise via mutation test.

Duplicate (etf, date) rows are deduplicated keeping the last; upstream is responsible
for not introducing duplicates.

Public API:
  etf_feature_names() -> tuple[str, ...]  — stable column order (90 names)
  build_etf_features_matrix(panel, eval_date) -> pd.Series  — one row of 90 features
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_stock_tail import constants as C


def etf_feature_names() -> tuple[str, ...]:
    """Return stable tuple of feature names: etf_{sym}_ret_{w}d.

    Per Amendment A1.1 (2026-04-25), iterates over C.ALL_INDEX_SYMBOLS
    (28 global ETFs + 10 NSE sectoral indices = 40 indices x 3 windows = 120 names).
    """
    return tuple(
        f"etf_{sym}_ret_{w}d"
        for sym in C.ALL_INDEX_SYMBOLS
        for w in C.ETF_RETURN_WINDOWS
    )


def _ret_n(closes: pd.Series, n: int) -> float:
    """Compute n-day return from the last n+1 closes. Returns NaN if insufficient data."""
    if len(closes) < n + 1:
        return float("nan")
    c0 = closes.iloc[-(n + 1)]
    cN = closes.iloc[-1]
    if c0 == 0 or pd.isna(c0) or pd.isna(cN):
        return float("nan")
    return float(cN / c0 - 1.0)


def build_etf_features_matrix(panel: pd.DataFrame, eval_date: pd.Timestamp) -> pd.Series:
    """Compute 90-feature ETF row for eval_date using only date < eval_date.

    Parameters
    ----------
    panel : pd.DataFrame
        Long-format ETF price panel with columns: date, etf, close.
    eval_date : pd.Timestamp
        The evaluation date. Only rows with date < eval_date are used (strict causality).

    Returns
    -------
    pd.Series
        90-element Series indexed by etf_feature_names(), dtype float64.
        Missing ETFs produce NaN for all their windows.
    """
    eval_date = pd.Timestamp(eval_date)
    out: dict[str, float] = {}
    for sym in C.ALL_INDEX_SYMBOLS:
        # STRICT causality: exclude eval_date itself
        df = panel[(panel["etf"] == sym) & (panel["date"] < eval_date)]
        df = df.drop_duplicates(subset="date", keep="last")  # documented policy: keep latest if dup
        closes = df.sort_values("date")["close"]
        for w in C.ETF_RETURN_WINDOWS:
            out[f"etf_{sym}_ret_{w}d"] = _ret_n(closes, w)
    result = pd.Series(out)
    return result[list(etf_feature_names())]   # raises KeyError on any missing column
