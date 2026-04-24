"""Tests for v2 feature library expansion (Task 4)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


V2_NEW_FEATURES = (
    "return_1d", "return_5d", "return_60d",
    "skewness_20d", "kurtosis_20d",
    "volume_zscore_20d", "turnover_percentile_252d", "volume_trend_5d",
    "excess_return_vs_sector_20d", "rank_in_sector_20d_return",
    "peer_spread_zscore_20d", "correlation_to_sector_60d",
    "residual_return_5d", "adv_ratio_to_sector_mean_20d",
)


def test_all_14_v2_features_are_registered():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    missing = [f for f in V2_NEW_FEATURES if f not in FEATURE_FUNCS]
    assert not missing, f"v2 features missing from FEATURE_FUNCS: {missing}"


def test_feature_funcs_has_exactly_34_keys():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    assert len(FEATURE_FUNCS) == 34, (
        f"v2 library must have exactly 34 features; got {len(FEATURE_FUNCS)}"
    )


def _tiny_synth(n_days=260, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    rows = []
    # Two sectors with 3 tickers each + NIFTY pseudo-ticker.
    tickers_and_sectors = [
        ("T0", "A"), ("T1", "A"), ("T2", "A"),
        ("T3", "B"), ("T4", "B"), ("T5", "B"),
    ]
    for tk, sec in tickers_and_sectors:
        price = 100.0 + rng.normal(0, 5)
        for d in dates:
            price *= 1.0 + rng.normal(0, 0.012)
            rows.append({"date": d, "ticker": tk, "sector": sec,
                         "close": price,
                         "volume": max(1000.0, rng.normal(1e6, 2e5))})
    # NIFTY as pseudo-ticker (no sector).
    nprice = 18000.0
    for d in dates:
        nprice *= 1.0 + rng.normal(0, 0.008)
        rows.append({"date": d, "ticker": "NIFTY", "sector": "",
                     "close": nprice, "volume": 1.0})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("feature_name", [
    "return_1d", "return_5d", "return_60d",
    "skewness_20d", "kurtosis_20d",
    "volume_zscore_20d", "turnover_percentile_252d", "volume_trend_5d",
    "excess_return_vs_sector_20d", "rank_in_sector_20d_return",
    "peer_spread_zscore_20d", "correlation_to_sector_60d",
    "residual_return_5d", "adv_ratio_to_sector_mean_20d",
])
def test_v2_feature_is_causal_and_finite_on_synth(feature_name):
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    panel = _tiny_synth()
    fn = FEATURE_FUNCS[feature_name]
    # Evaluate at a date deep enough for 252-bar features.
    eval_t = panel["date"].iloc[-10]
    value = fn(panel, "T0", eval_t)
    # Causality spot-check: a panel truncated to date < eval_t gives same answer.
    truncated = panel[panel["date"] < eval_t]
    value_trunc = fn(truncated, "T0", eval_t)
    if np.isnan(value):
        assert np.isnan(value_trunc), (
            f"{feature_name}: NaN on full panel but finite on truncated"
        )
    else:
        assert np.isfinite(value), (
            f"{feature_name}: non-finite {value}"
        )
        assert np.isclose(value, value_trunc, equal_nan=True), (
            f"{feature_name}: value differs under causality truncation: "
            f"{value} vs {value_trunc} — LOOK-AHEAD BUG"
        )


def test_return_1d_matches_manual_on_known_prices():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    panel = pd.DataFrame([
        {"date": pd.Timestamp("2020-04-23"), "ticker": "T0",
         "close": 100.0, "volume": 1.0, "sector": "A"},
        {"date": pd.Timestamp("2020-04-24"), "ticker": "T0",
         "close": 110.0, "volume": 1.0, "sector": "A"},
        {"date": pd.Timestamp("2020-04-25"), "ticker": "T0",
         "close": 110.0, "volume": 1.0, "sector": "A"},
    ])
    # return_1d on 2020-04-25 reads close[t-1]=110, close[t-2]=100.
    v = FEATURE_FUNCS["return_1d"](panel, "T0", pd.Timestamp("2020-04-25"))
    assert np.isclose(v, 0.1), f"expected 0.1; got {v}"


def test_return_5d_matches_manual_on_known_prices():
    from pipeline.autoresearch.regime_autoresearch.features import (
        FEATURE_FUNCS,
    )
    # 7 bars so we have >= 6 past rows on day 7.
    dates = pd.bdate_range("2020-04-23", periods=7)
    prices = [100, 102, 104, 106, 108, 110, 115]
    panel = pd.DataFrame([
        {"date": d, "ticker": "T0", "close": p,
         "volume": 1.0, "sector": "A"}
        for d, p in zip(dates, prices)
    ])
    # Evaluate on day 7; t-1 = day 6 close=110, t-6 = day 1 close=100.
    eval_t = dates[6]
    v = FEATURE_FUNCS["return_5d"](panel, "T0", eval_t)
    assert np.isclose(v, 0.1), f"expected 0.1; got {v}"
