"""Tests for runner_phase_c_slice — slice-restricted compliance runner.

Covers:
  - filter_events_by_geometry: LAG / OVERSHOOT / DEGENERATE classification + invalid slice
  - SliceSpec: output_path construction for LAG and OVERSHOOT hypotheses
  - run_slice_compliance: writes filtered events + invokes runner.main with
    the expected flags
  - main (CLI): argparse plumbing
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pandas as pd

from pipeline.autoresearch.overshoot_compliance.runner_phase_c_slice import (
    filter_events_by_geometry,
    SliceSpec,
)
from pipeline.autoresearch.overshoot_compliance import runner_phase_c_slice as slice_mod


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


def _parent_events_df() -> pd.DataFrame:
    """Fixture matching the columns produced by _extract_parent_events."""
    return pd.DataFrame([
        # RELIANCE UP LAG: expected=+2%, actual=+0.5%
        {"ticker": "RELIANCE", "direction": "UP", "expected_return_pct": 2.0,
         "actual_return_pct": 0.5, "date": "2024-01-02", "z": 2.1,
         "today_resid": -1.5, "today_ret": 0.5, "next_resid": 0.0, "next_ret": 0.1},
        {"ticker": "RELIANCE", "direction": "UP", "expected_return_pct": 2.0,
         "actual_return_pct": 0.6, "date": "2024-02-02", "z": 2.2,
         "today_resid": -1.4, "today_ret": 0.6, "next_resid": 0.0, "next_ret": 0.1},
        # RELIANCE DOWN LAG
        {"ticker": "RELIANCE", "direction": "DOWN", "expected_return_pct": -2.0,
         "actual_return_pct": -0.5, "date": "2024-03-02", "z": -2.1,
         "today_resid": 1.5, "today_ret": -0.5, "next_resid": 0.0, "next_ret": -0.1},
        # TCS UP OVERSHOOT: expected=+1%, actual=+3% → same-sign residual → OVERSHOOT
        {"ticker": "TCS", "direction": "UP", "expected_return_pct": 1.0,
         "actual_return_pct": 3.0, "date": "2024-01-02", "z": 2.3,
         "today_resid": 2.0, "today_ret": 3.0, "next_resid": 0.0, "next_ret": 0.2},
    ])


class TestRunSliceCompliance:
    def test_run_slice_compliance_writes_filtered_events_and_invokes_runner(
        self, tmp_path, monkeypatch,
    ):
        # Write a parent events.json fixture to disk.
        parent_path = tmp_path / "parent_events.json"
        _parent_events_df().to_json(parent_path, orient="records", date_format="iso")

        captured: dict = {}

        def _fake_runner_main(argv: list[str]) -> int:
            captured["argv"] = list(argv)
            # Simulate success and touch a gate_checklist.json in the out-dir.
            out_dir = Path(argv[argv.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "gate_checklist.json").write_text(
                json.dumps({"decision": "FAIL"}), encoding="utf-8"
            )
            return 0

        import pipeline.autoresearch.overshoot_compliance.runner as real_runner
        monkeypatch.setattr(real_runner, "main", _fake_runner_main)

        spec = SliceSpec(
            slice_name="LAG",
            hypothesis_id="H-TEST-LAG",
            results_root=tmp_path / "results",
        )
        out_dir = slice_mod.run_slice_compliance(
            parent_events_path=parent_path,
            slice_spec=spec,
            run_timestamp="20260424-test",
            n_permutations=1000,
            min_events_per_cell=1,
        )

        # filtered_events.json must exist and contain only LAG rows.
        filtered_path = out_dir / "filtered_events.json"
        assert filtered_path.exists(), "filtered_events.json must be written"
        filtered = pd.read_json(filtered_path, orient="records")
        # LAG rows: 3 RELIANCE rows (2 UP LAG + 1 DOWN LAG).
        assert len(filtered) == 3
        assert set(filtered["ticker"]) == {"RELIANCE"}

        # runner.main was invoked with the expected flags.
        argv = captured["argv"]
        assert "--out-dir" in argv
        assert str(out_dir) == argv[argv.index("--out-dir") + 1]
        assert "--events-override" in argv
        assert str(filtered_path) == argv[argv.index("--events-override") + 1]
        assert "--hypothesis-id" in argv
        assert "H-TEST-LAG" == argv[argv.index("--hypothesis-id") + 1]
        # family_size = number of (ticker, direction) cells with >=1 event = 2
        assert "--family-size" in argv
        assert argv[argv.index("--family-size") + 1] == "2"

    def test_run_slice_compliance_applies_ticker_filter(self, tmp_path, monkeypatch):
        parent_path = tmp_path / "parent_events.json"
        _parent_events_df().to_json(parent_path, orient="records", date_format="iso")

        import pipeline.autoresearch.overshoot_compliance.runner as real_runner
        monkeypatch.setattr(real_runner, "main", lambda argv: 0)

        spec = SliceSpec(
            slice_name="OVERSHOOT",
            hypothesis_id="H-TEST-OVER",
            results_root=tmp_path / "results",
        )
        out_dir = slice_mod.run_slice_compliance(
            parent_events_path=parent_path,
            slice_spec=spec,
            run_timestamp="20260424-tcs-only",
            n_permutations=1000,
            min_events_per_cell=1,
            ticker_filter="TCS",
        )
        filtered = pd.read_json(out_dir / "filtered_events.json", orient="records")
        # Only TCS OVERSHOOT survives.
        assert len(filtered) == 1
        assert filtered.iloc[0]["ticker"] == "TCS"

    def test_run_slice_compliance_min_events_filter(self, tmp_path, monkeypatch):
        parent_path = tmp_path / "parent_events.json"
        _parent_events_df().to_json(parent_path, orient="records", date_format="iso")

        import pipeline.autoresearch.overshoot_compliance.runner as real_runner
        monkeypatch.setattr(real_runner, "main", lambda argv: 0)

        spec = SliceSpec(
            slice_name="LAG",
            hypothesis_id="H-TEST-MIN",
            results_root=tmp_path / "results",
        )
        # min_events_per_cell=2 drops RELIANCE-DOWN (only 1 event), keeps
        # RELIANCE-UP (2 events).
        out_dir = slice_mod.run_slice_compliance(
            parent_events_path=parent_path,
            slice_spec=spec,
            run_timestamp="20260424-minfilt",
            n_permutations=1000,
            min_events_per_cell=2,
        )
        filtered = pd.read_json(out_dir / "filtered_events.json", orient="records")
        assert len(filtered) == 2
        assert set(filtered["direction"]) == {"UP"}


class TestCLIMain:
    def test_cli_main_parses_flags_correctly(self, tmp_path, monkeypatch):
        parent_path = tmp_path / "parent_events.json"
        _parent_events_df().to_json(parent_path, orient="records", date_format="iso")

        captured: dict = {}

        def _fake_runner_main(argv: list[str]) -> int:
            captured["argv"] = list(argv)
            out_dir = Path(argv[argv.index("--out-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            return 0

        import pipeline.autoresearch.overshoot_compliance.runner as real_runner
        monkeypatch.setattr(real_runner, "main", _fake_runner_main)
        monkeypatch.setattr(slice_mod, "_RESULTS_ROOT", tmp_path / "results")
        # SliceSpec default factory has already captured the old _RESULTS_ROOT;
        # pass results_root explicitly through the CLI args instead by using
        # env-like override if supported.  For this test we just ensure argv
        # plumbs through; output dir can live anywhere.

        rc = slice_mod.main([
            "--parent-events", str(parent_path),
            "--slice", "LAG",
            "--hypothesis-id", "H-CLI-TEST",
            "--n-permutations", "500",
            "--min-events-per-cell", "1",
            "--run-timestamp", "20260424-cli",
        ])
        assert rc == 0
        argv = captured["argv"]
        # Flags made it through to the inner runner.main call.
        assert "--hypothesis-id" in argv
        assert argv[argv.index("--hypothesis-id") + 1] == "H-CLI-TEST"
        assert "--events-override" in argv
        assert "--family-size" in argv
