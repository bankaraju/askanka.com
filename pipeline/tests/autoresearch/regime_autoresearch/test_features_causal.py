"""Causality check: every feature at date t uses only rows with date < t."""
from __future__ import annotations

import pandas as pd
import numpy as np

from pipeline.autoresearch.regime_autoresearch.features import (
    FEATURE_FUNCS, build_feature_matrix,
)


def _synthetic_panel(n_tickers: int = 5, n_days: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    tickers = [f"T{i}" for i in range(n_tickers)]
    rows = []
    for t in tickers:
        closes = 100 + np.cumsum(rng.standard_normal(n_days) * 0.5)
        vols = 1e7 + rng.standard_normal(n_days) * 1e5
        for d, c, v in zip(dates, closes, vols):
            rows.append({"date": d, "ticker": t, "close": c, "volume": v})
    return pd.DataFrame(rows)


def test_all_20_features_registered():
    # v2: now 34 features (20 v1 + 14 v2); update assertion accordingly.
    assert len(FEATURE_FUNCS) == 34


def test_causality_pointwise():
    """For each feature, flipping a future bar must not change today's value."""
    panel = _synthetic_panel()
    evaluation_date = panel["date"].iloc[150]
    past = panel[panel["date"] < evaluation_date].copy()

    panel_mut = panel.copy()
    future_mask = panel_mut["date"] >= evaluation_date
    panel_mut.loc[future_mask, "close"] = panel_mut.loc[future_mask, "close"] * 10.0

    tickers = panel["ticker"].unique().tolist()
    v1 = build_feature_matrix(panel, evaluation_date, tickers)
    v2 = build_feature_matrix(panel_mut, evaluation_date, tickers)
    pd.testing.assert_frame_equal(v1, v2, check_exact=False, rtol=1e-9, atol=1e-9)
