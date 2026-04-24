"""Smoke tests: each feature must return a float or NaN, never raise, on a
realistic synthetic panel."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.regime_autoresearch.features import FEATURE_FUNCS


def _rich_panel() -> pd.DataFrame:
    """300-day, 5-ticker panel with NIFTY, VIX, REGIME pseudo-tickers and
    trust_score/sector columns so that optional-data features degrade
    predictably."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-01", periods=300)
    tickers = ["T0", "T1", "T2", "NIFTY", "VIX", "REGIME"]
    rows = []
    for t in tickers:
        close = 100 + np.cumsum(rng.standard_normal(300) * 0.5)
        for d, c in zip(dates, close):
            rows.append({
                "date": d, "ticker": t, "close": c, "volume": 1e6,
                "market_cap": 1e9, "trust_score": 0.6, "sector": "IT",
            })
    return pd.DataFrame(rows)


@pytest.mark.parametrize("feature_name", list(FEATURE_FUNCS.keys()))
def test_feature_returns_float_or_nan(feature_name):
    """Every registered feature must return a float (or NaN) — never raise."""
    panel = _rich_panel()
    eval_date = panel["date"].iloc[200]
    fn = FEATURE_FUNCS[feature_name]
    out = fn(panel, "T0", eval_date)
    assert isinstance(out, float), f"{feature_name} returned {type(out).__name__}, expected float"


@pytest.mark.parametrize("feature_name", list(FEATURE_FUNCS.keys()))
def test_feature_nan_on_empty_panel(feature_name):
    """Every registered feature must return NaN on an empty panel — never raise."""
    empty = pd.DataFrame(columns=["date", "ticker", "close", "volume"])
    fn = FEATURE_FUNCS[feature_name]
    out = fn(empty, "T0", pd.Timestamp("2024-01-01"))
    assert isinstance(out, float) and np.isnan(out), f"{feature_name} returned {out!r}, expected NaN"
