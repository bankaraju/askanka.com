"""Tests for the geometric classifier in reverse_regime_breaks."""
import pytest

from pipeline.autoresearch.reverse_regime_breaks import classify_event_geometry


class TestClassifyEventGeometry:
    def test_lag_same_direction_undershoot(self):
        # expected +2%, actual +0.5% → residual -1.5% → signs differ → LAG
        assert classify_event_geometry(expected_return=2.0, actual_return=0.5) == "LAG"

    def test_overshoot_same_direction(self):
        # expected +2%, actual +3% → residual +1% → signs same → OVERSHOOT
        assert classify_event_geometry(expected_return=2.0, actual_return=3.0) == "OVERSHOOT"

    def test_lag_opposite_direction(self):
        # expected +2%, actual -1% → residual -3% → signs differ → LAG (FADE and FOLLOW agree: both LONG)
        assert classify_event_geometry(expected_return=2.0, actual_return=-1.0) == "LAG"

    def test_overshoot_negative_direction(self):
        # expected -2%, actual -3% → residual -1% → signs same (both negative) → OVERSHOOT
        assert classify_event_geometry(expected_return=-2.0, actual_return=-3.0) == "OVERSHOOT"

    def test_lag_negative_direction_undershoot(self):
        # expected -2%, actual -0.5% → residual +1.5% → signs differ → LAG
        assert classify_event_geometry(expected_return=-2.0, actual_return=-0.5) == "LAG"

    def test_degenerate_tiny_expected(self):
        # |expected| < 0.1% → DEGENERATE
        assert classify_event_geometry(expected_return=0.05, actual_return=3.0) == "DEGENERATE"

    def test_degenerate_tiny_residual(self):
        # expected 2%, actual 2.05% → residual 0.05% → |residual| < 0.1% → DEGENERATE
        assert classify_event_geometry(expected_return=2.0, actual_return=2.05) == "DEGENERATE"

    def test_degenerate_negative_tiny_expected(self):
        assert classify_event_geometry(expected_return=-0.05, actual_return=-2.0) == "DEGENERATE"

    def test_boundary_at_01pct(self):
        # exactly 0.1% on both is NOT degenerate (strict less-than)
        assert classify_event_geometry(expected_return=0.1, actual_return=2.0) != "DEGENERATE"


from pipeline.autoresearch.reverse_regime_breaks import classify_break


class TestClassifyBreakLabelSplit:
    def test_lag_opportunity_yields_opportunity_lag(self):
        # expected +2%, actual +0.5% → LAG; PCR agrees; no anomaly → OPPORTUNITY_LAG
        label, action = classify_break(
            expected_return=2.0, actual_return=0.5,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "OPPORTUNITY_LAG"
        assert action == "ADD"

    def test_overshoot_opportunity_yields_opportunity_overshoot(self):
        # expected +2%, actual +3% → OVERSHOOT; PCR agrees; no anomaly → OPPORTUNITY_OVERSHOOT (alert-only)
        label, action = classify_break(
            expected_return=2.0, actual_return=3.0,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "OPPORTUNITY_OVERSHOOT"
        # action for overshoot is ALERT, not ADD — signals must not be traded
        assert action == "ALERT"

    def test_degenerate_yields_uncertain(self):
        # expected 0.05%, actual 3% → DEGENERATE → UNCERTAIN, HOLD
        label, action = classify_break(
            expected_return=0.05, actual_return=3.0,
            z_score=3.0, pcr_class="BULLISH", oi_anomaly=False,
        )
        assert label == "UNCERTAIN"
        assert action == "HOLD"

    def test_warning_branch_unchanged(self):
        # Existing WARNING decision-matrix branch must not be affected by the split
        label, action = classify_break(
            expected_return=2.0, actual_return=0.5,
            z_score=3.0, pcr_class="BEARISH", oi_anomaly=True,
        )
        assert label == "WARNING"
        assert action == "REDUCE"


from pipeline.autoresearch.reverse_regime_breaks import enrich_break_with_direction


class TestEnrichBreakWithDirection:
    def test_lag_break_direction_follow(self):
        brk = {
            "symbol": "RELIANCE",
            "expected_return": 2.0,
            "actual_return": 0.5,
            "classification": "OPPORTUNITY_LAG",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "LAG"
        assert enriched["direction_intended"] == "FOLLOW"
        assert enriched["direction_tested"] == "FADE"
        assert enriched["direction_consistent"] is True  # FADE and FOLLOW agree on LAG
        assert enriched["trade_rec"] == "LONG"  # expected_return > 0

    def test_overshoot_break_direction_neutral(self):
        brk = {
            "symbol": "TORNTPOWER",
            "expected_return": 2.0,
            "actual_return": 3.0,
            "classification": "OPPORTUNITY_OVERSHOOT",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "OVERSHOOT"
        assert enriched["direction_intended"] == "NEUTRAL"  # alert-only
        assert enriched["direction_tested"] == "FADE"
        assert enriched["direction_consistent"] is False
        assert enriched["trade_rec"] is None  # no trade

    def test_warning_break_direction_neutral(self):
        brk = {
            "symbol": "SBIN",
            "expected_return": 2.0,
            "actual_return": 0.5,
            "classification": "WARNING",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["direction_intended"] == "NEUTRAL"
        assert enriched["trade_rec"] is None

    def test_negative_expected_follow_is_short(self):
        brk = {
            "symbol": "IDFCFIRSTB",
            "expected_return": -2.0,
            "actual_return": -0.5,
            "classification": "OPPORTUNITY_LAG",
        }
        enriched = enrich_break_with_direction(brk)
        assert enriched["event_geometry"] == "LAG"
        assert enriched["trade_rec"] == "SHORT"
