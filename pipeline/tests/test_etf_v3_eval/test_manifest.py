"""Tests for run-manifest writer (Backtest Spec §13A)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline.autoresearch.etf_v3_eval.manifest import write_manifest


def test_write_manifest_records_required_fields(tmp_path: Path) -> None:
    out = tmp_path / "manifest.json"
    config = {"lookback_days": 1200, "seed": 42}
    sample_file = tmp_path / "sample.parquet"
    sample_file.write_bytes(b"hello")

    write_manifest(
        out_path=out,
        run_id="test_run_1",
        config=config,
        seed=42,
        artifact_paths=[sample_file],
    )

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_id"] == "test_run_1"
    assert data["config"] == config
    assert data["seed"] == 42
    assert "git_commit" in data
    assert "generated_at_utc" in data
    assert "pip_freeze_sha256" in data
    assert "artifacts" in data
    expected_hash = hashlib.sha256(b"hello").hexdigest()
    assert data["artifacts"][str(sample_file)] == expected_hash
