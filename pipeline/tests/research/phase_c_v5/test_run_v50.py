from __future__ import annotations
from pipeline.research.phase_c_v5 import run_v50


def test_adapt_profile_picks_transition_with_most_episodes():
    """For each (stock, target_zone) pair, collapse by_transition entries
    ending in target_zone by keeping the transition with the largest
    episode_count."""
    real = {
        "stock_profiles": {
            "ALPHA": {
                "by_transition": {
                    "RISK-ON->NEUTRAL":  {"avg_drift_5d": 0.01, "hit_rate": 0.6, "episode_count": 10},
                    "CAUTION->NEUTRAL":  {"avg_drift_5d": 0.02, "hit_rate": 0.7, "episode_count": 30},
                    "NEUTRAL->RISK-OFF": {"avg_drift_5d": -0.03, "hit_rate": 0.5, "episode_count": 5},
                }
            },
            "BETA": {
                "by_transition": {
                    "RISK-ON->NEUTRAL": {"avg_drift_5d": 0.05, "hit_rate": 0.8, "episode_count": 8},
                }
            },
        }
    }
    adapted = run_v50._adapt_profile(real)
    # NEUTRAL picks CAUTION->NEUTRAL for ALPHA (30 episodes) and RISK-ON->NEUTRAL for BETA (8 episodes)
    assert set(adapted.keys()) == {"NEUTRAL", "RISK-OFF"}
    neutral_syms = adapted["NEUTRAL"]["symbols"]
    assert neutral_syms["ALPHA"] == {"drift_5d_mean": 0.02, "hit_rate_5d": 0.7, "episodes": 30}
    assert neutral_syms["BETA"] == {"drift_5d_mean": 0.05, "hit_rate_5d": 0.8, "episodes": 8}
    # RISK-OFF has only ALPHA
    risk_off = adapted["RISK-OFF"]["symbols"]
    assert risk_off == {"ALPHA": {"drift_5d_mean": -0.03, "hit_rate_5d": 0.5, "episodes": 5}}


def test_adapt_profile_skips_stocks_with_no_by_transition():
    """Stocks with missing or empty by_transition are silently skipped."""
    real = {
        "stock_profiles": {
            "EMPTY": {},
            "NO_TRANS": {"by_transition": {}},
            "VALID":  {"by_transition": {"X->NEUTRAL": {"avg_drift_5d": 0.01, "hit_rate": 0.6, "episode_count": 5}}},
        }
    }
    adapted = run_v50._adapt_profile(real)
    assert list(adapted["NEUTRAL"]["symbols"].keys()) == ["VALID"]


def test_adapt_profile_skips_malformed_transition_keys():
    """Transition keys not shaped 'FROM->TO' are skipped."""
    real = {
        "stock_profiles": {
            "ALPHA": {"by_transition": {
                "BAD_KEY":       {"avg_drift_5d": 0.01, "hit_rate": 0.6, "episode_count": 10},
                "X->Y->Z":       {"avg_drift_5d": 0.02, "hit_rate": 0.7, "episode_count": 20},
                "GOOD->NEUTRAL": {"avg_drift_5d": 0.03, "hit_rate": 0.8, "episode_count": 15},
            }}
        }
    }
    adapted = run_v50._adapt_profile(real)
    assert list(adapted.keys()) == ["NEUTRAL"]
    assert adapted["NEUTRAL"]["symbols"]["ALPHA"]["episodes"] == 15
