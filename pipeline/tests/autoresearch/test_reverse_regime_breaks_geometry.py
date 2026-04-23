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
