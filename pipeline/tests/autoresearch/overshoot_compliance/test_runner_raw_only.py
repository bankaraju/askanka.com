"""Tests for raw-bar canonicity integration in the compliance runner.

Covers policy docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md:
- Rule 3 (referee path is raw-only): gate_checklist.json never reads sensitivity grid.
- Rule 4 (execution-window strictness): invalid trades are dropped, logged,
  and counted in manifest.
- Rule 5 (sensitivity-track segregation): when --research-sensitivity is
  invoked, metrics_grid_sensitivity.json and sensitivity_manifest.json are
  emitted alongside the authoritative artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.autoresearch.overshoot_compliance import runner


def test_smoke_run_emits_invalid_trades_log_and_manifest_fields(tmp_path):
    out_dir = tmp_path / "raw_only"
    rc = runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert rc == 0
    invalid_path = out_dir / "invalid_trades.json"
    assert invalid_path.exists(), "invalid_trades.json must be written on every run"
    payload = json.loads(invalid_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "MODE_A"
    assert "n_invalid" in payload
    assert isinstance(payload.get("trades", []), list)

    m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "invalid_trade_count" in m
    assert m["invalid_trade_count"] == payload["n_invalid"]
    assert m.get("invalid_trade_log_path") == "invalid_trades.json"


def test_smoke_run_does_not_emit_sensitivity_artifacts_by_default(tmp_path):
    out_dir = tmp_path / "raw_only_default"
    runner.main(["--out-dir", str(out_dir), "--smoke"])
    assert not (out_dir / "metrics_grid_sensitivity.json").exists()
    assert not (out_dir / "sensitivity_manifest.json").exists()


def test_sensitivity_flag_emits_parallel_artifacts(tmp_path):
    out_dir = tmp_path / "sensitivity"
    rc = runner.main(["--out-dir", str(out_dir), "--smoke", "--research-sensitivity"])
    assert rc == 0
    sens_grid = out_dir / "metrics_grid_sensitivity.json"
    sens_man = out_dir / "sensitivity_manifest.json"
    assert sens_grid.exists(), "metrics_grid_sensitivity.json must be written when flag set"
    assert sens_man.exists(), "sensitivity_manifest.json must be written when flag set"

    sg = json.loads(sens_grid.read_text(encoding="utf-8"))
    assert sg.get("track") == "sensitivity"

    sm = json.loads(sens_man.read_text(encoding="utf-8"))
    assert sm.get("imputer") == "sector_beta"
    assert "min_obs" in sm
    assert "n_imputed_bars" in sm


def test_gate_checklist_never_references_sensitivity_grid(tmp_path):
    out_dir = tmp_path / "gate_scope"
    runner.main(["--out-dir", str(out_dir), "--smoke", "--research-sensitivity"])
    gc_text = (out_dir / "gate_checklist.json").read_text(encoding="utf-8")
    assert "metrics_grid_sensitivity" not in gc_text
    assert "sensitivity_manifest" not in gc_text


def test_raw_bars_are_never_mutated(tmp_path, monkeypatch):
    import pandas as pd

    repo = Path(__file__).resolve().parents[4]
    fno_dir = repo / "pipeline" / "data" / "fno_historical"

    from pipeline.autoresearch.overshoot_compliance import runner as R
    sector_map = R.load_sector_map()
    sample = [t for t in sorted(sector_map.keys()) if (fno_dir / f"{t}.csv").exists()][:3]

    pre = {}
    for t in sample:
        p = fno_dir / f"{t}.csv"
        pre[t] = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")[
            ["Open", "High", "Low", "Close"]
        ].copy()

    out_dir = tmp_path / "no_mutation"
    runner.main(["--out-dir", str(out_dir), "--smoke", "--research-sensitivity"])

    for t in sample:
        p = fno_dir / f"{t}.csv"
        post = pd.read_csv(p, parse_dates=["Date"]).sort_values("Date").set_index("Date")[
            ["Open", "High", "Low", "Close"]
        ]
        pd.testing.assert_frame_equal(pre[t], post, check_exact=True)
