from __future__ import annotations
import json
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import ranker_backfill as rb


@pytest.fixture
def minimal_profile(tmp_path):
    """Phase A profile with 2 regimes, 3 symbols each."""
    profile = {
        "NEUTRAL": {
            "symbols": {
                "HIGH_DRIFT":   {"drift_5d_mean": 0.10, "hit_rate_5d": 0.80, "episodes": 6},
                "MID_DRIFT":    {"drift_5d_mean": 0.05, "hit_rate_5d": 0.70, "episodes": 5},
                "NEG_DRIFT":    {"drift_5d_mean": -0.08, "hit_rate_5d": 0.75, "episodes": 5},
            }
        },
        "CAUTION": {
            "symbols": {
                "HIGH_DRIFT":   {"drift_5d_mean": -0.15, "hit_rate_5d": 0.80, "episodes": 6},
                "DEFENSIVE":    {"drift_5d_mean": 0.12, "hit_rate_5d": 0.85, "episodes": 7},
            }
        },
    }
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(profile))
    return p


@pytest.fixture
def regime_history_df():
    """10 trading days with known regimes."""
    rows = [
        {"date": "2026-03-01", "zone": "NEUTRAL"},
        {"date": "2026-03-02", "zone": "NEUTRAL"},
        {"date": "2026-03-03", "zone": "NEUTRAL"},
        {"date": "2026-03-04", "zone": "CAUTION"},
        {"date": "2026-03-05", "zone": "CAUTION"},
        {"date": "2026-03-06", "zone": "CAUTION"},
        {"date": "2026-03-07", "zone": "NEUTRAL"},
        {"date": "2026-03-08", "zone": "NEUTRAL"},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_top_n_per_day_respects_regime(minimal_profile, regime_history_df):
    """NEUTRAL day picks HIGH_DRIFT/MID_DRIFT/NEG_DRIFT; CAUTION picks its own symbols."""
    result = rb.backfill_daily_top_n(
        profile_path=minimal_profile,
        regime_history=regime_history_df,
        top_n=2,
        min_episodes=4,
        min_hit_rate=0.6,
    )
    # Should have one row per (date, side)
    assert set(result.columns) >= {"date", "zone", "side", "symbol", "rank", "drift_5d_mean"}
    # NEUTRAL 2026-03-01 longs: HIGH_DRIFT (rank 1), MID_DRIFT (rank 2)
    neutral_longs = result[(result["date"] == pd.Timestamp("2026-03-01")) &
                            (result["side"] == "LONG")].sort_values("rank")
    assert list(neutral_longs["symbol"]) == ["HIGH_DRIFT", "MID_DRIFT"]
    # NEUTRAL 2026-03-01 shorts: NEG_DRIFT (only one negative)
    neutral_shorts = result[(result["date"] == pd.Timestamp("2026-03-01")) &
                             (result["side"] == "SHORT")]
    assert list(neutral_shorts["symbol"]) == ["NEG_DRIFT"]


def test_min_episodes_filter_drops_low_sample(minimal_profile, regime_history_df):
    """Setting min_episodes above any available drops candidates."""
    result = rb.backfill_daily_top_n(
        profile_path=minimal_profile,
        regime_history=regime_history_df,
        top_n=5,
        min_episodes=100,
        min_hit_rate=0.0,
    )
    assert result.empty


def test_regime_age_tagging(minimal_profile, regime_history_df):
    """Each row must include how many consecutive days the regime has held."""
    result = rb.backfill_daily_top_n(
        profile_path=minimal_profile,
        regime_history=regime_history_df,
        top_n=2,
        min_episodes=4,
        min_hit_rate=0.6,
    )
    assert "regime_age_days" in result.columns
    # 2026-03-01 is day 1 of NEUTRAL; 2026-03-02 is day 2
    d1 = result[result["date"] == pd.Timestamp("2026-03-01")]["regime_age_days"].iloc[0]
    d2 = result[result["date"] == pd.Timestamp("2026-03-02")]["regime_age_days"].iloc[0]
    assert d1 == 1
    assert d2 == 2
