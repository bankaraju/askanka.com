import pandas as pd

from pipeline.autoresearch.earnings_decoupling.macro_filter_adapter import (
    compute_index_returns_panel,
    is_event_macro_excluded,
)


def test_compute_index_returns_panel_returns_pct_change():
    closes = pd.DataFrame({
        "BANKNIFTY": [100.0, 101.0, 102.01],
    }, index=pd.bdate_range("2025-01-01", periods=3))
    rets = compute_index_returns_panel(closes)
    # First row NaN, then 1.0% then ~1.0%
    assert pd.isna(rets.iloc[0, 0])
    assert abs(rets.iloc[1, 0] - 0.01) < 1e-9


def test_is_event_macro_excluded_excludes_when_index_moves_2pct(monkeypatch):
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.02, 0.0], index=dates)  # +2% on T
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert excluded
    assert reason == "SECTOR_T"


def test_is_event_macro_excluded_excludes_on_t_plus_1():
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.0, 0.02], index=dates)  # +2% on T+1
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert excluded
    assert reason == "SECTOR_T1"


def test_is_event_macro_excluded_passes_when_quiet():
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0] * 5, index=dates)
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    assert not excluded
    assert reason is None


def test_is_event_macro_excluded_accepts_string_event_date():
    """Defensive: ISO-string event_date should normalise, not silently miss the index."""
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.02, 0.0], index=dates)
    vix = pd.Series([15.0] * 5, index=dates)
    excluded_ts, reason_ts = is_event_macro_excluded(
        event_date=dates[3], sector_index_returns=rets, india_vix=vix,
    )
    excluded_str, reason_str = is_event_macro_excluded(
        event_date=dates[3].strftime("%Y-%m-%d"),
        sector_index_returns=rets, india_vix=vix,
    )
    assert excluded_ts == excluded_str
    assert reason_ts == reason_str == "SECTOR_T"


def test_is_event_macro_excluded_accepts_tz_aware_event_date():
    """Defensive: tz-aware Timestamp must normalise to tz-naive panel index."""
    dates = pd.bdate_range("2025-01-01", periods=5)
    rets = pd.Series([0.0, 0.0, 0.0, 0.02, 0.0], index=dates)
    vix = pd.Series([15.0] * 5, index=dates)
    excluded, reason = is_event_macro_excluded(
        event_date=pd.Timestamp(dates[3].strftime("%Y-%m-%d"), tz="Asia/Kolkata"),
        sector_index_returns=rets, india_vix=vix,
    )
    assert excluded
    assert reason == "SECTOR_T"
