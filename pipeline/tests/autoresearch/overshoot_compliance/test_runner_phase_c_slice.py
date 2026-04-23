"""Tests for runner_phase_c_slice — slice-restricted compliance runner.

Covers:
  - filter_events_by_geometry: LAG / OVERSHOOT / DEGENERATE classification + invalid slice
  - SliceSpec: output_path construction for LAG and OVERSHOOT hypotheses
"""
from __future__ import annotations

import pytest
import pandas as pd

from pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice import (
    filter_events_by_geometry,
    SliceSpec,
)


class TestFilterEventsByGeometry:
    def _events_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            # ticker A UP: expected=+2%, actual=+0.5% → residual=-1.5% → opposite sign → LAG
            {"ticker": "A", "direction": "UP", "expected_return_pct": 2.0, "actual_return_pct": 0.5},
            # ticker A UP: expected=+2%, actual=+3.0% → residual=+1.0% → same sign → OVERSHOOT
            {"ticker": "A", "direction": "UP", "expected_return_pct": 2.0, "actual_return_pct": 3.0},
            # ticker B DOWN: expected=-2%, actual=-0.5% → residual=+1.5% → opposite sign → LAG
            {"ticker": "B", "direction": "DOWN", "expected_return_pct": -2.0, "actual_return_pct": -0.5},
            # ticker B DOWN: expected=-2%, actual=-3.0% → residual=-1.0% → same sign → OVERSHOOT
            {"ticker": "B", "direction": "DOWN", "expected_return_pct": -2.0, "actual_return_pct": -3.0},
            # ticker C UP: expected=+0.05% → |expected| < 0.1% → DEGENERATE
            {"ticker": "C", "direction": "UP", "expected_return_pct": 0.05, "actual_return_pct": 3.0},
        ])

    def test_lag_slice_keeps_lag_events_only(self):
        events = self._events_df()
        filtered = filter_events_by_geometry(events, "LAG")
        assert len(filtered) == 2
        assert set(filtered["ticker"]) == {"A", "B"}

    def test_overshoot_slice_keeps_overshoot_events_only(self):
        events = self._events_df()
        filtered = filter_events_by_geometry(events, "OVERSHOOT")
        assert len(filtered) == 2
        assert set(filtered["ticker"]) == {"A", "B"}

    def test_degenerate_excluded_from_both_slices(self):
        events = self._events_df()
        lag = filter_events_by_geometry(events, "LAG")
        overshoot = filter_events_by_geometry(events, "OVERSHOOT")
        assert len(lag) + len(overshoot) == 4  # DEGENERATE dropped from both

    def test_invalid_slice_raises(self):
        with pytest.raises(ValueError):
            filter_events_by_geometry(self._events_df(), "BOGUS")


class TestSliceSpec:
    def test_output_path_lag(self):
        spec = SliceSpec(slice_name="LAG", hypothesis_id="H-2026-04-23-002")
        path = spec.output_path("2026-04-23T12:00:00")
        assert "compliance_phase_c_lag" in str(path).lower()
        assert "H-2026-04-23-002" in str(path)

    def test_output_path_overshoot(self):
        spec = SliceSpec(slice_name="OVERSHOOT", hypothesis_id="H-2026-04-23-003")
        path = spec.output_path("2026-04-23T12:00:00")
        assert "compliance_phase_c_overshoot" in str(path).lower()
        assert "H-2026-04-23-003" in str(path)
