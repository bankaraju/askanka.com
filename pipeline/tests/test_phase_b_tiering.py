"""Tests for Phase B episode-based conviction tiering (B1.5)."""
from pipeline.terminal.api.candidates import _build_regime_picks


def _rec(ticker, conviction, episodes, hit_rate=1.0, direction="LONG"):
    return {"ticker": ticker, "direction": direction, "conviction": conviction,
            "episodes": episodes, "hit_rate": hit_rate}


def test_episodes_below_15_forces_provisional():
    today_recs = {"stocks": [_rec("KAYNES", "HIGH", 1, 1.0)]}
    out = _build_regime_picks(today_recs)
    assert out[0]["conviction"] == "PROVISIONAL"


def test_episodes_15_to_29_caps_at_medium():
    today_recs = {"stocks": [_rec("X", "HIGH", 20, 0.6)]}
    out = _build_regime_picks(today_recs)
    assert out[0]["conviction"] == "MEDIUM"


def test_episodes_30_plus_preserves_high():
    today_recs = {"stocks": [_rec("Y", "HIGH", 40, 0.65)]}
    out = _build_regime_picks(today_recs)
    assert out[0]["conviction"] == "HIGH"


def test_provisional_score_has_floor():
    today_recs = {"stocks": [_rec("KAYNES", "HIGH", 1, 1.0)]}
    out = _build_regime_picks(today_recs)
    assert out[0]["score"] >= 20   # floor
    assert out[0]["score"] < 100


def test_non_provisional_score_is_sample_weighted():
    today_recs = {"stocks": [_rec("Y", "HIGH", 30, 1.0)]}
    out = _build_regime_picks(today_recs)
    assert out[0]["score"] == 100   # full sample size × 100% hit = 100


def test_low_hit_rate_scales_down():
    today_recs = {"stocks": [_rec("Z", "HIGH", 40, 0.5)]}
    out = _build_regime_picks(today_recs)
    # n clamped at 30, hit_rate=0.5 → 0.5 × 100 × 1.0 = 50
    assert 48 <= out[0]["score"] <= 52


def test_missing_conviction_defaults_to_provisional_if_episodes_low():
    today_recs = {"stocks": [{"ticker": "W", "direction": "LONG", "episodes": 2, "hit_rate": 0.5}]}
    out = _build_regime_picks(today_recs)
    assert out[0]["conviction"] == "PROVISIONAL"
