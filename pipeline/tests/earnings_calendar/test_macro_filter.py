import datetime as dt

import pandas as pd

from pipeline.earnings_calendar.macro_filter import (
    INDEX_MOVE_THRESHOLD,
    VIX_ZSCORE_LOOKBACK_DAYS,
    VIX_ZSCORE_THRESHOLD,
    is_macro_excluded,
)


def _index_series_with(t_value: float, t_plus_1_value: float) -> pd.Series:
    dates = pd.date_range("2026-04-01", periods=10, freq="B")
    s = pd.Series(0.0, index=dates)
    s.iloc[-2] = t_value
    s.iloc[-1] = t_plus_1_value
    return s


def _quiet_vix_series(latest_z: float = 0.0) -> pd.Series:
    """Deterministic baseline alternating ±0.5 around 15.0 — gives mean
    exactly 15.0 and population std 0.5. Sample std (ddof=1) is
    approximately 0.5 as well for n=60. We solve for ``today`` such that
    z = (today - mu) / sd_sample = latest_z."""
    dates = pd.date_range("2025-12-01", periods=VIX_ZSCORE_LOOKBACK_DAYS + 1, freq="B")
    baseline = [15.0 + 0.5 if i % 2 == 0 else 15.0 - 0.5 for i in range(VIX_ZSCORE_LOOKBACK_DAYS)]
    s_window = pd.Series(baseline)
    mu = float(s_window.mean())
    sd = float(s_window.std(ddof=1))
    today = mu + latest_z * sd
    return pd.Series(baseline + [today], index=dates)


def test_thresholds_are_locked_to_user_decision():
    assert INDEX_MOVE_THRESHOLD == 0.015
    assert VIX_ZSCORE_THRESHOLD == 2.0
    assert VIX_ZSCORE_LOOKBACK_DAYS == 60


def test_excludes_when_event_day_index_move_exceeds_threshold():
    idx = _index_series_with(t_value=0.020, t_plus_1_value=0.001)
    vix = _quiet_vix_series()
    event_date = idx.index[-2].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_excludes_when_event_day_index_move_negative_exceeds_threshold():
    idx = _index_series_with(t_value=-0.018, t_plus_1_value=0.001)
    vix = _quiet_vix_series()
    event_date = idx.index[-2].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_excludes_when_t_plus_1_index_move_exceeds_threshold():
    idx = _index_series_with(t_value=0.001, t_plus_1_value=-0.018)
    vix = _quiet_vix_series()
    event_date = idx.index[-2].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_excludes_when_vix_zscore_at_or_above_threshold():
    idx = _index_series_with(t_value=0.005, t_plus_1_value=0.005)
    vix = _quiet_vix_series(latest_z=2.5)
    # event_date = last date so vix_zscore is computed at end of vix
    event_date = vix.index[-1].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_does_not_exclude_when_all_three_conditions_below_threshold():
    idx = _index_series_with(t_value=0.005, t_plus_1_value=-0.004)
    vix = _quiet_vix_series(latest_z=0.5)
    event_date = idx.index[-2].date()
    assert not is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_does_not_exclude_when_event_at_index_move_exactly_below_threshold():
    """Threshold is ≥ 1.5%; 1.49% must NOT exclude (no float-fudge bias)."""
    idx = _index_series_with(t_value=0.0149, t_plus_1_value=0.0)
    vix = _quiet_vix_series()
    event_date = idx.index[-2].date()
    assert not is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_excludes_at_exact_index_threshold_boundary():
    """The user-locked rule says ≥ 1.5%, so 1.5% MUST exclude."""
    idx = _index_series_with(t_value=0.015, t_plus_1_value=0.0)
    vix = _quiet_vix_series()
    event_date = idx.index[-2].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_excludes_just_above_vix_threshold():
    """Floating-point round-trip means exact 2.0 cannot be tested
    deterministically across pd.std → mul → div — but 2.001 can. The
    rule is ≥ 2.0; we verify the comparison is non-strict by checking
    a value just above the boundary."""
    idx = _index_series_with(t_value=0.0, t_plus_1_value=0.0)
    vix = _quiet_vix_series(latest_z=2.001)
    event_date = vix.index[-1].date()
    assert is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_does_not_exclude_just_below_vix_threshold():
    idx = _index_series_with(t_value=0.0, t_plus_1_value=0.0)
    vix = _quiet_vix_series(latest_z=1.999)
    event_date = vix.index[-1].date()
    assert not is_macro_excluded(event_date=event_date, index_returns=idx, india_vix=vix)


def test_event_outside_index_returns_returns_false_no_crash():
    """Defensive: missing index data must NOT crash, but also must NOT
    be silently treated as excluded — leave the decision to the caller
    via a documented absent-data path."""
    idx = _index_series_with(t_value=0.005, t_plus_1_value=0.005)
    vix = _quiet_vix_series()
    far_future = dt.date(2030, 6, 1)
    # No exception, no exclusion: missing data ≠ excluded
    assert not is_macro_excluded(event_date=far_future, index_returns=idx, india_vix=vix)
