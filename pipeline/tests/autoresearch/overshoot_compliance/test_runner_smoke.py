from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import runner


def test_smoke_runner_produces_all_artifacts(tmp_path):
    out_dir = tmp_path / "smoke_run"
    rc = runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert rc == 0
    expected = {
        "manifest.json",
        "data_audit.json",
        "universe_snapshot.json",
        "metrics_grid.json",
        "comparators.json",
        "permutations_100k.json",
        "fragility.json",
        "beta_residual.json",
        "impl_risk.json",
        "cusum_decay.json",
        "portfolio_gate.json",
        "direction_audit.json",
        "gate_checklist.json",
        "invalid_trades.json",
    }
    produced = {p.name for p in out_dir.iterdir()}
    missing = expected - produced
    assert not missing, f"missing artifacts: {missing}"


def test_smoke_gate_checklist_has_decision(tmp_path):
    import json
    out_dir = tmp_path / "smoke_run2"
    runner.main(["--out-dir", str(out_dir), "--smoke"])
    report = json.loads((out_dir / "gate_checklist.json").read_text(encoding="utf-8"))
    assert report["hypothesis_id"] == "H-2026-04-23-001"
    assert report["decision"] in {"PASS", "PARTIAL", "FAIL"}
