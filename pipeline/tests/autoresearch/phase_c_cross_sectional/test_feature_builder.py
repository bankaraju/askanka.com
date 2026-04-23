import numpy as np
import pandas as pd

from pipeline.autoresearch.phase_c_cross_sectional.feature_builder import (
    build_feature_matrix,
)


def test_feature_shape(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0,
        persistence_days=2, min_history_days=1,
    )
    X, y, names = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # 3 tickers in peer block + 3 sector means + vix + 3 regime dummies + z_self_T + z_self_T-1 + direction
    expected_cols = 3 + 3 + 1 + 3 + 1 + 1 + 1
    assert X.shape == (3, expected_cols)
    assert len(names) == expected_cols
    assert list(y.index) == list(X.index)


def test_feature_no_lookahead_self_zero(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0,
        persistence_days=2, min_history_days=1,
    )
    X, y, names = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # For the SBIN row, z_peer_SBIN column should be 0 (self zeroed)
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert X.loc[sbin_idx, "z_peer_SBIN"] == 0.0
    # But z_peer_RELIANCE on the SBIN row should equal z_panel["RELIANCE"] at that date
    sbin_date = pd.Timestamp(persistent.loc[sbin_idx, "date"])
    assert X.loc[sbin_idx, "z_peer_RELIANCE"] == tiny_z_panel.loc[sbin_date, "RELIANCE"]


def test_break_direction_sign(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0,
        persistence_days=2, min_history_days=1,
    )
    X, _, _ = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    # SBIN row was UP (z=+3.6)
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert X.loc[sbin_idx, "break_direction"] == 1
    # RELIANCE row was DOWN (z=-3.2)
    rel_idx = persistent.index[persistent["ticker"] == "RELIANCE"][0]
    assert X.loc[rel_idx, "break_direction"] == -1


def test_label_matches_next_ret(tiny_events_df, tiny_z_panel, tiny_regime_history, tiny_vix_series, tiny_broad_sector):
    from pipeline.autoresearch.phase_c_cross_sectional.event_filter import filter_persistent_breaks
    persistent = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0,
        persistence_days=2, min_history_days=1,
    )
    _, y, _ = build_feature_matrix(
        persistent, tiny_z_panel, tiny_regime_history, tiny_vix_series,
        broad_sector=tiny_broad_sector,
    )
    sbin_idx = persistent.index[persistent["ticker"] == "SBIN"][0]
    assert y.loc[sbin_idx] == 0.8  # from tiny_events_df fixture
