"""Tests for synthetic_options.classify_single_leg_tier -- spec ss13 risk #4 adapter.

Run: pytest pipeline/tests/test_synthetic_options_single_leg.py -v
"""
import pytest
from unittest.mock import patch

from pipeline import synthetic_options, vol_engine

SAMPLE_PROFILES_HIGH_DRIFT = {
    "stock_profiles": {
        "RELIANCE": {"summary": {"avg_drift_5d": 0.04, "hit_rate": 0.62}},
    }
}

SAMPLE_PROFILES_LOW_DRIFT = {
    "stock_profiles": {
        "RELIANCE": {"summary": {"avg_drift_5d": 0.0001, "hit_rate": 0.50}},
    }
}

SAMPLE_PROFILES_EMPTY = {}


# ---------------------------------------------------------------------------
# 1. test_classify_single_leg_long_high_drift
# ---------------------------------------------------------------------------
def test_classify_single_leg_long_high_drift(monkeypatch):
    """vol=20%, drift=4%, 30d rent ~2% -> net_edge > 0 -> HIGH-ALPHA SYNTHETIC."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.20)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_HIGH_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    assert result["ticker"] == "RELIANCE"
    assert result["side"] == "LONG"
    assert abs(result["expected_drift_pct"] - 4.0) < 0.01
    month_tier = next(t for t in result["tiers"] if t["horizon"] == "1_month")
    assert month_tier["classification"] == "HIGH-ALPHA SYNTHETIC"


# ---------------------------------------------------------------------------
# 2. test_classify_single_leg_short
# ---------------------------------------------------------------------------
def test_classify_single_leg_short(monkeypatch):
    """side=SHORT uses abs(drift) -- outcome same as LONG since abs() is symmetric."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.20)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="SHORT",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_HIGH_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    assert result["side"] == "SHORT"
    month_tier = next(t for t in result["tiers"] if t["horizon"] == "1_month")
    assert month_tier["classification"] == "HIGH-ALPHA SYNTHETIC"
    # drift_pct must equal abs value regardless of direction
    assert abs(result["expected_drift_pct"] - 4.0) < 0.01


# ---------------------------------------------------------------------------
# 3. test_classify_single_leg_zero_drift_negative_carry
# ---------------------------------------------------------------------------
def test_classify_single_leg_zero_drift_negative_carry(monkeypatch):
    """drift~0%, rent>0% -> negative net_edge -> NEGATIVE CARRY for 1_month."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.25)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_LOW_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    month_tier = next(t for t in result["tiers"] if t["horizon"] == "1_month")
    assert month_tier["classification"] == "NEGATIVE CARRY"
    assert month_tier["net_edge_pct"] < 0


# ---------------------------------------------------------------------------
# 4. test_classify_single_leg_same_day_experimental
# ---------------------------------------------------------------------------
def test_classify_single_leg_same_day_experimental(monkeypatch):
    """same_day tier with positive net_edge -> EXPERIMENTAL (per classify_tier rule)."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.20)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_HIGH_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    sameday = next(t for t in result["tiers"] if t["horizon"] == "same_day")
    assert sameday["experimental"] is True
    # same_day with positive edge -> EXPERIMENTAL (not HIGH-ALPHA SYNTHETIC)
    if sameday["net_edge_pct"] > 0:
        assert sameday["classification"] == "EXPERIMENTAL"


# ---------------------------------------------------------------------------
# 5. test_classify_single_leg_no_vol_grounding_false
# ---------------------------------------------------------------------------
def test_classify_single_leg_no_vol_grounding_false(monkeypatch):
    """vol_engine returns None -> grounding_ok=False, tiers=[], reason populated."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: None)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="XYZ",
            side="LONG",
            spot=100.0,
            regime_profiles=SAMPLE_PROFILES_EMPTY,
            oi_data=None,
        )

    assert result["grounding_ok"] is False
    assert result["tiers"] == []
    assert result["reason"] != ""
    assert "XYZ" in result["reason"]


# ---------------------------------------------------------------------------
# 6. test_classify_single_leg_no_drift_in_profile_uses_zero
# ---------------------------------------------------------------------------
def test_classify_single_leg_no_drift_in_profile_uses_zero(monkeypatch):
    """ticker missing from regime_profiles -> drift defaults to 0 -> NEGATIVE CARRY."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.25)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_EMPTY,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    assert result["expected_drift_pct"] == 0.0
    month_tier = next(t for t in result["tiers"] if t["horizon"] == "1_month")
    assert month_tier["classification"] == "NEGATIVE CARRY"


# ---------------------------------------------------------------------------
# 7. test_classify_single_leg_caution_badges_invoked
# ---------------------------------------------------------------------------
def test_classify_single_leg_caution_badges_invoked(monkeypatch):
    """same_day tier without OI anomaly -> LOW_CONVICTION_GAMMA badge present."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.25)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_LOW_DRIFT,
            oi_data=None,  # no OI data -> LOW_CONVICTION_GAMMA should appear
        )

    assert "caution_badges" in result
    assert "LOW_CONVICTION_GAMMA" in result["caution_badges"]


# ---------------------------------------------------------------------------
# 8. test_output_schema_matches_phase_c_consumer
# ---------------------------------------------------------------------------
def test_output_schema_matches_phase_c_consumer(monkeypatch):
    """Output tiers list has all required keys matching build_leverage_matrix shape."""
    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: 0.20)
    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=1.0):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_HIGH_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    required_top = {"ticker", "side", "spot", "stock_vol", "vol_scalar_applied",
                    "expected_drift_pct", "tiers", "caution_badges", "grounding_ok"}
    assert required_top.issubset(set(result.keys()))

    required_tier_keys = {
        "horizon", "days_to_expiry", "premium_cost_pct", "five_day_theta_pct",
        "friction_pct", "total_rent_pct", "expected_drift_pct",
        "net_edge_pct", "classification", "experimental",
    }
    for tier in result["tiers"]:
        assert required_tier_keys.issubset(set(tier.keys())), (
            f"tier {tier['horizon']} missing keys: "
            f"{required_tier_keys - set(tier.keys())}"
        )

    horizons = [t["horizon"] for t in result["tiers"]]
    assert horizons == ["1_month", "15_day", "same_day"]


# ---------------------------------------------------------------------------
# 9. test_classify_single_leg_uses_vol_scalar
# ---------------------------------------------------------------------------
def test_classify_single_leg_uses_vol_scalar(monkeypatch):
    """vol_scalar=0.9 is applied to raw vol before passing to pricer."""
    raw_vol = 0.30
    scalar = 0.9
    expected_vol = raw_vol * scalar
    calls = []

    monkeypatch.setattr(vol_engine, "get_stock_vol", lambda ticker, **kw: raw_vol)

    import pipeline.options_pricer as options_pricer
    original_five_day_rent = options_pricer.five_day_rent

    def patched_five_day_rent(spot, vol, days_to_expiry):
        calls.append(vol)
        return original_five_day_rent(spot, vol, days_to_expiry)

    with patch("pipeline.synthetic_options._load_vol_scalar", return_value=scalar), \
         patch("pipeline.synthetic_options.options_pricer.five_day_rent",
               side_effect=patched_five_day_rent):
        result = synthetic_options.classify_single_leg_tier(
            ticker="RELIANCE",
            side="LONG",
            spot=2400.0,
            regime_profiles=SAMPLE_PROFILES_HIGH_DRIFT,
            oi_data=None,
        )

    assert result["grounding_ok"] is True
    assert result["vol_scalar_applied"] == scalar
    # All pricer calls must use the scaled vol
    for v in calls:
        assert abs(v - expected_vol) < 1e-9, f"pricer called with vol={v}, expected {expected_vol}"
