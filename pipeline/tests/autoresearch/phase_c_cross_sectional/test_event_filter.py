import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_cross_sectional.event_filter import (
    filter_persistent_breaks,
)


def test_filter_keeps_three_persistent_events(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2,
        min_history_days=5,  # relaxed for synthetic fixture
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
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # SBIN 2024-01-20 had no prior-day 3σ
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-20")).any()


def test_filter_drops_opposing_sign(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # RELIANCE 2024-04-05: T-1=-0.5 (below threshold), T=+3.3 → fails persistence
    assert not ((out["ticker"] == "RELIANCE") & (out["date"] == "2024-04-05")).any()


def test_filter_drops_below_threshold(tiny_events_df, tiny_z_panel):
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=2, min_history_days=5,
    )
    # HDFC 2024-05-01: z=2.7 < 3
    assert not ((out["ticker"] == "HDFC") & (out["date"] == "2024-05-01")).any()


def test_persistence_3_days_stricter(tiny_events_df, tiny_z_panel):
    # With 3-day persistence, SBIN on 2024-01-10 is kept only if SBIN z on 2024-01-08 also >=3
    # In the fixture SBIN 2024-01-08 z=0.1 so 3-day persistence drops it
    out = filter_persistent_breaks(
        tiny_events_df, tiny_z_panel,
        z_threshold=3.0, persistence_days=3, min_history_days=5,
    )
    assert not ((out["ticker"] == "SBIN") & (out["date"] == "2024-01-10")).any()
