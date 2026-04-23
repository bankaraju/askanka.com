"""Smoke test for the TA Coincidence Scorer RELIANCE pilot compliance runner.

The runner executes the full §15.1 gate checklist for hypothesis H-2026-04-24-001:
  - TA attractiveness score >= 70 at EOD close on RELIANCE (LONG)
  - Exit at next close (T+1, MODE A close-to-close)
  - Claimed edge: mean next_ret >= 0.5%, hit_rate >= 55%, p <= 1e-3 at 100k perms.

The `--smoke` flag reduces the permutation count from 100_000 to 500 so CI stays
fast while still exercising every artifact-writing path.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.autoresearch.overshoot_compliance import ta_pilot_runner


def test_ta_pilot_smoke_produces_gate_checklist(tmp_path: Path) -> None:
    out_dir = tmp_path / "ta_pilot_smoke"
    rc = ta_pilot_runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert rc == 0, "ta_pilot_runner.main should return 0 on smoke run"

    gate_path = out_dir / "gate_checklist.json"
    assert gate_path.exists(), "gate_checklist.json must be written"

    report = json.loads(gate_path.read_text(encoding="utf-8"))
    assert report["hypothesis_id"] == "H-2026-04-24-001"
    assert report["decision"] in {"PASS", "PARTIAL", "FAIL"}

    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json must be written"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "invalid_trade_count" in manifest, (
        "manifest must include invalid_trade_count after raw-bar canonicity gate runs"
    )
