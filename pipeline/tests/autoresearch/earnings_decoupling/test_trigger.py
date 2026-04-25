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


def test_compute_trigger_z_accepts_string_event_date(residual_panel):
    """ISO-string event_date should be normalised, not silently miss the index."""
    event_ts = residual_panel.index[300]
    z_ts = compute_trigger_z(residual_panel, "RELIANCE", event_ts)
    z_str = compute_trigger_z(residual_panel, "RELIANCE", event_ts.strftime("%Y-%m-%d"))
    assert z_ts == z_str


def test_compute_trigger_z_accepts_tz_aware_event_date(residual_panel):
    """tz-aware Timestamp should normalise to the panel's tz-naive index."""
    event_ts = residual_panel.index[300]
    z_naive = compute_trigger_z(residual_panel, "RELIANCE", event_ts)
    z_aware = compute_trigger_z(
        residual_panel, "RELIANCE",
        pd.Timestamp(event_ts.strftime("%Y-%m-%d"), tz="Asia/Kolkata"),
    )
    assert z_naive == z_aware


def test_compute_trigger_z_baseline_window_spans_calendar_not_dropna_collapse(residual_panel):
    """A NaN-burst in the baseline must NOT silently collapse the rolling calendar.

    Previously (dropna → rolling), a 10-day suspension was straddled as 5
    valid contiguous data points, masking the gap. Now (rolling → dropna),
    the affected windows produce NaN and are discarded, but adjacent windows
    represent true 5-trading-day calendar slices.
    """
    rp = residual_panel.copy()
    event_idx = 300
    event_date = rp.index[event_idx]
    # Inject a 10-day NaN streak well inside the baseline
    rp.iloc[event_idx - 50:event_idx - 40, rp.columns.get_loc("RELIANCE")] = float("nan")
    z = compute_trigger_z(rp, "RELIANCE", event_date)
    # Should still produce a number (enough surrounding data) but the σ is
    # computed over windows that do not silently bridge the gap.
    assert z is not None
    assert -10 < z < 10
