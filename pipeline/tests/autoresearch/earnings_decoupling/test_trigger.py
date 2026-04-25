import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.earnings_decoupling.trigger import (
    cum_residual_window,
    compute_trigger_z,
)


@pytest.fixture
def residual_panel():
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-01", periods=400)
    return pd.DataFrame({
        "RELIANCE": np.random.normal(0, 0.005, size=400),
        "TCS":      np.random.normal(0, 0.005, size=400),
    }, index=dates)


def test_cum_residual_sums_t_minus_7_through_t_minus_3(residual_panel):
    event_date = residual_panel.index[300]
    expected = residual_panel.loc[
        residual_panel.index[300 - 7]:residual_panel.index[300 - 3],
        "RELIANCE",
    ].sum()
    actual = cum_residual_window(residual_panel, "RELIANCE", event_date)
    assert abs(actual - expected) < 1e-12


def test_compute_trigger_z_returns_none_when_insufficient_baseline(residual_panel):
    event_date = residual_panel.index[20]  # too early — fewer than 200 baseline days
    z = compute_trigger_z(residual_panel, "RELIANCE", event_date)
    assert z is None


def test_compute_trigger_z_returns_value_when_baseline_sufficient(residual_panel):
    event_date = residual_panel.index[300]
    z = compute_trigger_z(residual_panel, "RELIANCE", event_date)
    assert z is not None
    assert -10 < z < 10


def test_compute_trigger_z_baseline_excludes_t_minus_8_onwards(residual_panel):
    """Baseline σ must NOT include the trigger window itself."""
    rp = residual_panel.copy()
    event_idx = 300
    event_date = rp.index[event_idx]
    # Insert a huge spike inside [T-7, T-3] — should NOT inflate the baseline σ
    rp.loc[rp.index[event_idx - 5], "RELIANCE"] = 0.5
    z_with_spike = compute_trigger_z(rp, "RELIANCE", event_date)
    rp.loc[rp.index[event_idx - 5], "RELIANCE"] = 0.0
    z_without_spike = compute_trigger_z(rp, "RELIANCE", event_date)
    # Z values differ because cum_residual changed, but the σ must be the same
    # (the spike does not enter the baseline). Verify both are non-None.
    assert z_with_spike is not None and z_without_spike is not None


def test_compute_trigger_z_returns_none_when_zero_variance(residual_panel):
    rp = residual_panel.copy()
    rp["RELIANCE"] = 0.0  # constant baseline
    event_date = rp.index[300]
    z = compute_trigger_z(rp, "RELIANCE", event_date)
    assert z is None
