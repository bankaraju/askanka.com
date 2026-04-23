"""Tests for slice-support flags added to runner.main for Task 10.

Covers:
  - events.json is materialized at the end of Step 4b on every run.
  - --events-override PATH bypasses Steps 4/4b and uses provided events.
  - --hypothesis-id ID overrides the default _HYPOTHESIS_ID in manifest and
    gate_checklist.
  - --family-size N overrides the Bonferroni threshold (0.05 / family_size)
    used in Step 13's survivor filter.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import runner


def test_smoke_run_writes_events_json(tmp_path):
    out_dir = tmp_path / "smoke_events"
    rc = runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert rc == 0
    events_path = out_dir / "events.json"
    assert events_path.exists(), "events.json must be written at end of Step 4b"
    data = json.loads(events_path.read_text(encoding="utf-8"))
    # On a 5-ticker smoke, the list may be empty but must be a list.
    assert isinstance(data, list)


def test_hypothesis_id_flag_overrides_default(tmp_path):
    out_dir = tmp_path / "hid_override"
    rc = runner.main([
        "--out-dir", str(out_dir),
        "--smoke",
        "--hypothesis-id", "H-TEST-OVERRIDE",
    ])
    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["hypothesis_id"] == "H-TEST-OVERRIDE"
    gc = json.loads((out_dir / "gate_checklist.json").read_text(encoding="utf-8"))
    assert gc["hypothesis_id"] == "H-TEST-OVERRIDE"


def test_events_override_bypasses_steps_4_4b(tmp_path, monkeypatch):
    """When --events-override is supplied, compute_residuals / classify_events
    must NOT be called; the runner must consume the override file directly."""
    import pipeline.autoresearch.overshoot_compliance.runner as R

    # Sentinel: raise if Step 4 primitives are invoked.
    def _should_not_call(*args, **kwargs):
        raise AssertionError("compute_residuals must not run under --events-override")

    def _should_not_classify(*args, **kwargs):
        raise AssertionError("classify_events must not run under --events-override")

    monkeypatch.setattr(R, "compute_residuals", _should_not_call)
    monkeypatch.setattr(R, "classify_events", _should_not_classify)

    # Tiny synthetic events file — 2 rows, one UP one DOWN, same ticker.
    override = tmp_path / "events_override.json"
    df = pd.DataFrame([
        {"ticker": "RELIANCE", "date": "2024-01-02", "z": 2.5, "today_resid": 1.5,
         "today_ret": 2.0, "next_resid": -0.3, "next_ret": -0.5, "direction": "UP",
         "expected_return_pct": 0.5, "actual_return_pct": 2.0},
        {"ticker": "RELIANCE", "date": "2024-02-02", "z": -2.3, "today_resid": -1.4,
         "today_ret": -1.8, "next_resid": 0.4, "next_ret": 0.6, "direction": "DOWN",
         "expected_return_pct": -0.4, "actual_return_pct": -1.8},
    ])
    df.to_json(override, orient="records", date_format="iso", indent=2)

    out_dir = tmp_path / "override_run"
    rc = runner.main([
        "--out-dir", str(out_dir),
        "--smoke",
        "--events-override", str(override),
    ])
    assert rc == 0

    # events.json should contain the override rows.
    events_out = json.loads((out_dir / "events.json").read_text(encoding="utf-8"))
    assert isinstance(events_out, list)
    assert len(events_out) == 2

    # Fragility verdict should be SKIPPED_SLICE_OVERRIDE (since only window=20
    # is populated from the override; windows 15/25 are missing).
    fr = json.loads((out_dir / "fragility.json").read_text(encoding="utf-8"))
    assert fr["verdict"] == "SKIPPED_SLICE_OVERRIDE"


def test_family_size_flag_affects_bonferroni_threshold(tmp_path, monkeypatch):
    """With --family-size N, the survivor threshold is 0.05/N, not 1.17e-4.

    We prove this by intercepting defense_filter.partition: it receives the
    survivor list built from fade_rows filtered by p_value <= threshold.
    """
    import pipeline.autoresearch.overshoot_compliance.runner as R

    # Monkeypatch per_ticker_fade_stats to return two rows with known p-values.
    fake_rows = [
        {"ticker": "RELIANCE", "direction": "UP", "edge_net_pct": 1.0, "p_value": 0.01},
        {"ticker": "RELIANCE", "direction": "DOWN", "edge_net_pct": 1.0, "p_value": 0.001},
    ]
    monkeypatch.setattr(R, "per_ticker_fade_stats", lambda *a, **k: fake_rows)

    captured: dict = {}
    original_partition = R.defense_filter.partition

    def _spy_partition(survivors, sector_of):
        captured["survivors"] = list(survivors)
        return original_partition(survivors, sector_of)

    monkeypatch.setattr(R.defense_filter, "partition", _spy_partition)

    # Use --events-override to guarantee `events` is non-empty so the
    # per_ticker_fade_stats path is reached (smoke alone has no events).
    override = tmp_path / "events_override.json"
    pd.DataFrame([
        {"ticker": "RELIANCE", "date": "2024-01-02", "z": 2.5, "today_resid": 1.5,
         "today_ret": 2.0, "next_resid": -0.3, "next_ret": -0.5, "direction": "UP"},
    ]).to_json(override, orient="records", date_format="iso")

    # family_size=5 → threshold = 0.05/5 = 0.01 → both 0.01 and 0.001 qualify.
    out_dir = tmp_path / "family5"
    rc = runner.main([
        "--out-dir", str(out_dir),
        "--smoke",
        "--events-override", str(override),
        "--family-size", "5",
    ])
    assert rc == 0
    # p<=0.01 matches both rows (edge positive on both).
    assert len(captured["survivors"]) == 2

    # family_size=1000 → threshold = 0.05/1000 = 5e-5 → neither row qualifies.
    captured.clear()
    out_dir2 = tmp_path / "family1000"
    rc = runner.main([
        "--out-dir", str(out_dir2),
        "--smoke",
        "--events-override", str(override),
        "--family-size", "1000",
    ])
    assert rc == 0
    assert len(captured["survivors"]) == 0
