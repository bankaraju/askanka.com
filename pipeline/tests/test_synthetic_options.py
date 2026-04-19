"""
Tests for pipeline/synthetic_options.py — leverage matrix orchestrator.

Run: pytest pipeline/tests/test_synthetic_options.py -v
"""
import pytest
from unittest.mock import patch, MagicMock

SAMPLE_SIGNAL = {
    "signal_id": "SIG-2026-04-19-001-Defence_vs_IT",
    "spread_name": "Defence vs IT",
    "conviction": 68,
    "long_legs": [
        {"ticker": "HAL", "price": 4284.8, "weight": 0.5},
        {"ticker": "BEL", "price": 449.85, "weight": 0.5},
    ],
    "short_legs": [
        {"ticker": "TCS", "price": 2572.0, "weight": 0.5},
        {"ticker": "INFY", "price": 1322.1, "weight": 0.5},
    ],
}

SAMPLE_PROFILES = {
    "stock_profiles": {
        "HAL": {"summary": {"avg_drift_5d": 0.0139, "hit_rate": 0.62}},
        "BEL": {"summary": {"avg_drift_5d": 0.0120, "hit_rate": 0.58}},
        "TCS": {"summary": {"avg_drift_5d": -0.0100, "hit_rate": 0.55}},
        "INFY": {"summary": {"avg_drift_5d": -0.0090, "hit_rate": 0.54}},
    }
}


class TestClassifyTier:
    def test_positive_edge_non_sameday(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.5, "1_month") == "HIGH-ALPHA SYNTHETIC"

    def test_positive_edge_sameday(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.5, "same_day") == "EXPERIMENTAL"

    def test_negative_edge(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(-0.1, "1_month") == "NEGATIVE CARRY"

    def test_zero_edge(self):
        from pipeline.synthetic_options import classify_tier
        assert classify_tier(0.0, "15_day") == "NEGATIVE CARRY"


class TestBuildCautionBadges:
    def test_negative_carry_badge(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": -0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data=None)
        assert "NEGATIVE_CARRY" in badges

    def test_low_conviction_gamma_no_oi(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data=None)
        assert "LOW_CONVICTION_GAMMA" in badges

    def test_drift_exceeds_rent_badge(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 1.8, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data={"HAL": {"oi_anomaly_type": "CALL_BUILDUP"}})
        assert "DRIFT_EXCEEDS_RENT" in badges
        assert "LOW_CONVICTION_GAMMA" not in badges

    def test_no_badges_when_all_positive_with_oi(self):
        from pipeline.synthetic_options import build_caution_badges
        tiers = [
            {"horizon": "1_month", "net_edge_pct": 0.5, "experimental": False},
            {"horizon": "15_day", "net_edge_pct": 0.3, "experimental": False},
            {"horizon": "same_day", "net_edge_pct": 0.2, "experimental": True},
        ]
        badges = build_caution_badges(tiers, oi_data={"HAL": {"oi_anomaly_type": "CALL_BUILDUP"}})
        assert "NEGATIVE_CARRY" not in badges
        assert "LOW_CONVICTION_GAMMA" not in badges


class TestBuildLeverageMatrix:
    @patch("pipeline.synthetic_options.vol_engine")
    def test_returns_grounding_ok_true(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        assert result["grounding_ok"] is True
        assert result["signal_id"] == "SIG-2026-04-19-001-Defence_vs_IT"

    @patch("pipeline.synthetic_options.vol_engine")
    def test_three_tiers_present(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        horizons = [t["horizon"] for t in result["tiers"]]
        assert horizons == ["1_month", "15_day", "same_day"]

    @patch("pipeline.synthetic_options.vol_engine")
    def test_grounding_false_when_vol_unavailable(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = None
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        assert result["grounding_ok"] is False

    @patch("pipeline.synthetic_options.vol_engine")
    def test_tier_fields_complete(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        tier = result["tiers"][0]
        required = {"horizon", "days_to_expiry", "premium_cost_pct", "five_day_theta_pct",
                     "friction_pct", "total_rent_pct", "expected_drift_pct",
                     "net_edge_pct", "classification", "experimental"}
        assert required.issubset(set(tier.keys()))

    @patch("pipeline.synthetic_options.vol_engine")
    def test_sameday_is_experimental(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        sameday = [t for t in result["tiers"] if t["horizon"] == "same_day"][0]
        assert sameday["experimental"] is True

    @patch("pipeline.synthetic_options.vol_engine")
    def test_net_edge_is_drift_minus_rent(self, mock_vol):
        from pipeline.synthetic_options import build_leverage_matrix
        mock_vol.get_stock_vol.return_value = 0.30
        result = build_leverage_matrix(SAMPLE_SIGNAL, SAMPLE_PROFILES)
        for tier in result["tiers"]:
            expected = tier["expected_drift_pct"] - tier["total_rent_pct"]
            assert abs(tier["net_edge_pct"] - expected) < 0.001
