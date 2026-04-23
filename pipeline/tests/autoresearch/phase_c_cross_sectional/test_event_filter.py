import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.event_filter import (
    filter_persistent_breaks,
)


def test_filter_keeps_three_persistent_events(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=2,
        min_history_days=1,  # relaxed for synthetic fixture (v2 tighter history bound)
    )
    kept = list(zip(out["ticker"], out["date"].astype(str)))
    assert sorted(kept) == [
        ("HDFC", "2024-03-20"),
        ("RELIANCE", "2024-02-15"),
        ("SBIN", "2024-01-10"),
    ]


def test_filter_drops_single_day_spike(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=2, min_history_days=5,
    )
    # SBIN 2024-01-20 had no prior-day 3σ
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-20")).any()


def test_filter_drops_opposing_sign(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=2, min_history_days=5,
    )
    # RELIANCE 2024-04-05: T-1=-0.5 (below threshold), T=+3.3 → fails persistence
    assert not ((out["ticker"] == "RELIANCE") & (out["date"] == "2024-04-05")).any()


def test_filter_drops_below_threshold(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=2, min_history_days=5,
    )
    # HDFC 2024-05-01: z=2.7 < 3
    assert not ((out["ticker"] == "HDFC") & (out["date"] == "2024-05-01")).any()


def test_persistence_3_days_stricter(tiny_events_df, tiny_z_panel):
    # With 3-day persistence, SBIN on 2024-01-10 is kept only if SBIN z on 2024-01-08 also >=3
    # In the fixture SBIN 2024-01-08 z=0.1 so 3-day persistence drops it
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=3.0, persistence_days=3, min_history_days=5,
    )
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-10")).any()


def test_asymmetric_threshold_accepts_2sigma_prior(tiny_events_df, tiny_z_panel):
    """|z|>=3 on T with |z|>=2 on T-1 same-sign should now pass.

    HDFC 2024-03-20: T=+3.1, T-1=+3.0. Already passed under symmetric rule.
    Kept here as a regression baseline that the asymmetric rule is no stricter.
    """
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=2.0,
        persistence_days=2, min_history_days=5,
    )
    assert ((out["ticker"] == "HDFC") & (out["date"] == "2024-03-20")).any()


def test_asymmetric_threshold_expands_matches(tiny_events_df, tiny_z_panel):
    """Under symmetric |z|>=3 on both days only 3 events pass (see
    test_filter_keeps_three_persistent_events). Asymmetric |z|>=3 T with
    |z|>=2 T-1 should still include those 3 at minimum; the synthetic fixture
    is too small to add new matches but the output count must be >=3.
    """
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold_current=3.0, z_threshold_prior=2.0,
        persistence_days=2, min_history_days=1,
    )
    assert len(out) >= 3
