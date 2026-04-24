"""Tests for v2 Mode 2 orchestrator (Task 6)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def test_run_mode2_dry_run_spawns_five_workers(tmp_path):
    """--dry-run --cap 0 should spawn 5 worker subprocesses and exit cleanly."""
    summary_dir = tmp_path / "summaries"
    summary_dir.mkdir()
    out = subprocess.run(
        [
            "python", "-m",
            "pipeline.autoresearch.regime_autoresearch.scripts.run_mode2",
            "--dry-run", "--cap", "0",
            "--summary-dir", str(summary_dir),
        ],
        capture_output=True, text=True, timeout=60,
        cwd="C:/Users/Claude_Anka/askanka.com",
    )
    assert out.returncode == 0, f"exit {out.returncode}\n{out.stderr}"
    # Summary JSON dropped at summary_dir/run_mode2_summary_*.json
    summary_files = list(summary_dir.glob("run_mode2_summary_*.json"))
    assert summary_files, f"no summary written; stdout: {out.stdout}"
    summary = json.loads(summary_files[0].read_text())
    assert len(summary["regime_results"]) == 5, (
        f"Expected 5 regime workers; got {len(summary['regime_results'])}"
    )
    for r in summary["regime_results"]:
        assert "regime" in r and r["regime"] in (
            "RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA",
        )
        assert "exit_code" in r
