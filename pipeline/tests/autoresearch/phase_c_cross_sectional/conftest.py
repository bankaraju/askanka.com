"""Synthetic fixtures for cross-sectional model unit tests.

Deliberately tiny so tests stay under 1 s. Each fixture is fully deterministic
under the fixed seed in test_feature_builder / test_model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def tiny_events_df() -> pd.DataFrame:
    """Six events across three tickers, two dates. Three are persistent
    (|z|>=3 on T AND T-1, same sign), three are not."""
    rows = [
        # Persistent SBIN UP on 2024-01-10 (was +3.5 on 2024-01-09)
        {"ticker": "SBIN", "date": "2024-01-10", "z": 3.6, "today_resid": 4.0,
         "today_ret": 4.1, "next_resid": 0.2, "next_ret": 0.8,
         "direction": "UP", "actual_return_pct": 4.1, "expected_return_pct": 0.1},
        # Persistent RELIANCE DOWN on 2024-02-15
        {"ticker": "RELIANCE", "date": "2024-02-15", "z": -3.2,
         "today_resid": -3.8, "today_ret": -4.0, "next_resid": 1.1,
         "next_ret": 1.5, "direction": "DOWN",
         "actual_return_pct": -4.0, "expected_return_pct": -0.2},
        # Persistent HDFC UP on 2024-03-20
        {"ticker": "HDFC", "date": "2024-03-20", "z": 3.1, "today_resid": 3.5,
         "today_ret": 3.4, "next_resid": -0.3, "next_ret": -0.5,
         "direction": "UP", "actual_return_pct": 3.4, "expected_return_pct": -0.1},
        # Non-persistent: single-day 4σ on SBIN 2024-01-20 (no prior-day 3σ)
        {"ticker": "SBIN", "date": "2024-01-20", "z": 4.0, "today_resid": 4.5,
         "today_ret": 4.6, "next_resid": 0.1, "next_ret": 0.2,
         "direction": "UP", "actual_return_pct": 4.6, "expected_return_pct": 0.1},
        # Non-persistent: opposing-sign days on RELIANCE 2024-04-05
        {"ticker": "RELIANCE", "date": "2024-04-05", "z": 3.3,
         "today_resid": 3.7, "today_ret": 3.8, "next_resid": -0.5,
         "next_ret": -1.0, "direction": "UP",
         "actual_return_pct": 3.8, "expected_return_pct": 0.1},
        # Below threshold HDFC 2024-05-01 (|z|=2.7 < 3)
        {"ticker": "HDFC", "date": "2024-05-01", "z": 2.7, "today_resid": 3.0,
         "today_ret": 3.1, "next_resid": 0.2, "next_ret": 0.3,
         "direction": "UP", "actual_return_pct": 3.1, "expected_return_pct": 0.1},
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def tiny_z_panel() -> pd.DataFrame:
    """Synthetic z-score panel: dates × 3 tickers, deterministic.
    Includes T-1 rows needed by the persistence filter.
    """
    dates = pd.to_datetime([
        "2024-01-08", "2024-01-09", "2024-01-10",
        "2024-02-14", "2024-02-15",
        "2024-03-19", "2024-03-20",
        "2024-01-19", "2024-01-20",
        "2024-04-04", "2024-04-05",
        "2024-04-30", "2024-05-01",
    ])
    tickers = ["SBIN", "RELIANCE", "HDFC"]
    # Row-wise values chosen so SBIN/RELIANCE/HDFC have the needed T-1 z's:
    data = {
        "SBIN":     [0.1, 3.5, 3.6, 0.0, 0.1, 0.2, 0.3, 0.5, 4.0, 0.1, 0.2, 0.0, 0.1],
        "RELIANCE": [0.0, 0.1, 0.2, -3.1, -3.2, 0.1, 0.0, 0.0, 0.1, -0.5, 3.3, 0.0, 0.1],
        "HDFC":     [0.0, 0.1, 0.0, 0.1, 0.0, 3.0, 3.1, 0.1, 0.0, 0.1, 0.1, 2.5, 2.7],
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def tiny_regime_history() -> pd.DataFrame:
    """Date → regime label. Covers all dates referenced by tiny_events_df."""
    return pd.DataFrame({
        "date": pd.to_datetime([
            "2024-01-08", "2024-01-09", "2024-01-10",
            "2024-01-19", "2024-01-20",
            "2024-02-14", "2024-02-15",
            "2024-03-19", "2024-03-20",
            "2024-04-04", "2024-04-05",
            "2024-04-30", "2024-05-01",
        ]),
        "regime": [
            "NEUTRAL", "NEUTRAL", "NEUTRAL",
            "RISK_OFF", "RISK_OFF",
            "RISK_ON", "RISK_ON",
            "NEUTRAL", "NEUTRAL",
            "RISK_OFF", "RISK_OFF",
            "NEUTRAL", "NEUTRAL",
        ],
    }).set_index("date")


@pytest.fixture
def tiny_vix_series() -> pd.Series:
    """VIX close per date. Aligned with tiny_regime_history index."""
    idx = pd.to_datetime([
        "2024-01-08", "2024-01-09", "2024-01-10",
        "2024-01-19", "2024-01-20",
        "2024-02-14", "2024-02-15",
        "2024-03-19", "2024-03-20",
        "2024-04-04", "2024-04-05",
        "2024-04-30", "2024-05-01",
    ])
    return pd.Series(
        [14.2, 14.5, 15.0, 18.0, 19.5, 12.0, 11.8,
         15.5, 15.0, 20.0, 22.5, 14.8, 14.0],
        index=idx, name="vix_close",
    )


@pytest.fixture
def tiny_broad_sector() -> dict:
    """Broad sector map for the 3 test tickers."""
    return {"SBIN": "Banks", "RELIANCE": "Energy", "HDFC": "FinSvc"}
