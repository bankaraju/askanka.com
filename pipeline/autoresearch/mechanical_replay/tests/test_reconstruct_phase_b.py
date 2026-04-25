"""TDD for reconstruct.phase_b — Phase B basket regeneration.

Phase B fires only on regime-transition days. The ranker reads the frozen
Phase A profile (`reverse_regime_profile.json`) and emits the top-N longs
+ shorts for transitions ending in the new regime.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay.reconstruct import phase_b


@pytest.fixture
def synth_profile(tmp_path: Path) -> Path:
    payload = {
        "generated_at": "2026-04-25T00:00:00",
        "stock_profiles": {
            "AAA": {
                "by_transition": {
                    "NEUTRAL->RISK-ON": {
                        "avg_drift_5d": 0.040, "avg_drift_1d": 0.005,
                        "avg_gap": 0.001, "hit_rate": 0.6, "episode_count": 10,
                        "tradeable_rate": 0.8, "persistence_rate": 0.5,
                    },
                },
            },
            "BBB": {
                "by_transition": {
                    "NEUTRAL->RISK-ON": {
                        "avg_drift_5d": -0.030, "avg_drift_1d": -0.004,
                        "avg_gap": 0.0, "hit_rate": 0.5, "episode_count": 8,
                        "tradeable_rate": 0.75, "persistence_rate": 0.4,
                    },
                },
            },
            "CCC": {
                "by_transition": {
                    "RISK-ON->NEUTRAL": {
                        "avg_drift_5d": 0.020, "avg_drift_1d": 0.002,
                        "avg_gap": 0.0, "hit_rate": 0.55, "episode_count": 6,
                        "tradeable_rate": 0.7, "persistence_rate": 0.45,
                    },
                },
            },
        },
    }
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_phase_b_fires_only_on_transition_days(synth_profile: Path):
    """A non-transition day should produce zero rows."""
    regime_history = pd.DataFrame({
        "date": pd.to_datetime(["2026-04-20", "2026-04-21", "2026-04-22"]),
        "regime_zone": ["NEUTRAL", "NEUTRAL", "NEUTRAL"],
    })
    out = phase_b.regenerate(
        regime_history=regime_history,
        profile_path=synth_profile,
    )
    assert out.empty


def test_phase_b_emits_basket_on_transition(synth_profile: Path):
    """A NEUTRAL → RISK-ON transition should pull AAA (long) and BBB (short)."""
    regime_history = pd.DataFrame({
        "date": pd.to_datetime(["2026-04-20", "2026-04-21"]),
        "regime_zone": ["NEUTRAL", "RISK-ON"],
    })
    out = phase_b.regenerate(
        regime_history=regime_history,
        profile_path=synth_profile,
    )
    assert not out.empty
    aaa = out[out["ticker"] == "AAA"].iloc[0]
    bbb = out[out["ticker"] == "BBB"].iloc[0]
    assert aaa["side"] == "LONG"
    assert bbb["side"] == "SHORT"
    assert aaa["regime"] == "RISK-ON"
    assert pd.Timestamp(aaa["date"]).normalize() == pd.Timestamp("2026-04-21")


def test_phase_b_filters_by_target_regime(synth_profile: Path):
    """CCC's transition is RISK-ON->NEUTRAL — should NOT appear on a
    NEUTRAL->RISK-ON day.
    """
    regime_history = pd.DataFrame({
        "date": pd.to_datetime(["2026-04-20", "2026-04-21"]),
        "regime_zone": ["NEUTRAL", "RISK-ON"],
    })
    out = phase_b.regenerate(
        regime_history=regime_history,
        profile_path=synth_profile,
    )
    assert "CCC" not in set(out["ticker"])


def test_phase_b_respects_top_n(synth_profile: Path):
    """top_n=1 should keep at most 1 long and 1 short."""
    regime_history = pd.DataFrame({
        "date": pd.to_datetime(["2026-04-20", "2026-04-21"]),
        "regime_zone": ["NEUTRAL", "RISK-ON"],
    })
    out = phase_b.regenerate(
        regime_history=regime_history,
        profile_path=synth_profile,
        top_n=1,
    )
    longs = out[out["side"] == "LONG"]
    shorts = out[out["side"] == "SHORT"]
    assert len(longs) <= 1
    assert len(shorts) <= 1


def test_phase_b_returns_required_columns(synth_profile: Path):
    regime_history = pd.DataFrame({
        "date": pd.to_datetime(["2026-04-20", "2026-04-21"]),
        "regime_zone": ["NEUTRAL", "RISK-ON"],
    })
    out = phase_b.regenerate(
        regime_history=regime_history,
        profile_path=synth_profile,
    )
    expected = {"date", "ticker", "side", "score", "regime", "transition"}
    assert expected.issubset(out.columns)
