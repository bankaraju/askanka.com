"""Coverage for audit_incumbents.py: cell classifier + report schema."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES
from pipeline.autoresearch.regime_autoresearch.scripts import audit_incumbents


def _make_table(incumbents: list[dict]) -> dict:
    return {"incumbents": incumbents, "seeded_at": "2026-04-24",
            "spec_version": "v1"}


def _insufficient_power_cell() -> dict:
    return {
        "n_obs": 0, "sharpe_point": None,
        "sharpe_ci_low": None, "sharpe_ci_high": None,
        "p_value_vs_zero": None, "p_value_vs_buy_hold": None,
        "compliance_artifact_path": None,
        "status_flag": "INSUFFICIENT_POWER",
    }


def _claimed_sharpe_cell(sharpe: float = 0.8) -> dict:
    return {
        "n_obs": 120, "sharpe_point": sharpe,
        "sharpe_ci_low": sharpe - 0.1, "sharpe_ci_high": sharpe + 0.1,
        "p_value_vs_zero": 0.01, "p_value_vs_buy_hold": 0.05,
        "compliance_artifact_path": None,  # the audit catches this mismatch
        "status_flag": "CLEAN",
    }


def _write_table(tmp_path: Path, incumbents: list[dict]) -> Path:
    p = tmp_path / "strategy_results_10.json"
    p.write_text(json.dumps(_make_table(incumbents)), encoding="utf-8")
    return p


def test_audit_classifies_insufficient_power_as_correct(tmp_path):
    """INSUFFICIENT_POWER row + no artefact on disk -> CORRECTLY_INSUFFICIENT_POWER."""
    table_path = _write_table(tmp_path, [{
        "strategy_id": "FOO_STRATEGY",
        "strategy_name": "Foo",
        "status": "LIVE",
        "per_regime": {r: _insufficient_power_cell() for r in REGIMES},
    }])
    empty_results_dir = tmp_path / "results_empty"
    empty_results_dir.mkdir()

    report = audit_incumbents.audit(
        table_path=table_path,
        results_dir=empty_results_dir,
        cutoff_date_iso="2026-04-23",
    )
    assert report["summary"]["total_rows"] == 1
    assert report["summary"]["total_cells"] == 5
    assert report["summary"]["cells_correctly_insufficient"] == 5
    assert report["summary"]["cells_backed"] == 0
    assert report["summary"]["cells_should_have_been_run"] == 0
    assert report["summary"]["cells_stale"] == 0

    row = report["per_strategy"][0]
    assert all(v == "CORRECTLY_INSUFFICIENT_POWER"
               for v in row["per_regime_verdict"].values())
    assert row["re_qualification_priority"] == "NONE"
    assert row["backing_artefact_path"] is None


def test_audit_detects_should_have_been_run(tmp_path):
    """Row claims Sharpe=0.8 but no artefact exists -> SHOULD_HAVE_BEEN_RUN."""
    table_path = _write_table(tmp_path, [{
        "strategy_id": "BAR_STRATEGY",
        "strategy_name": "Bar",
        "status": "LIVE",
        "per_regime": {r: _claimed_sharpe_cell(0.8) for r in REGIMES},
    }])
    empty_results_dir = tmp_path / "results_empty"
    empty_results_dir.mkdir()

    report = audit_incumbents.audit(
        table_path=table_path,
        results_dir=empty_results_dir,
        cutoff_date_iso="2026-04-23",
    )
    row = report["per_strategy"][0]
    assert all(v == "SHOULD_HAVE_BEEN_RUN"
               for v in row["per_regime_verdict"].values())
    assert row["re_qualification_priority"] == "HIGH"
    assert report["summary"]["cells_should_have_been_run"] == 5


def test_audit_detects_stale_artefact(tmp_path):
    """Artefact exists but mtime < cutoff -> STALE."""
    # Row claims a CLEAN Sharpe cell; artefact exists for strategy id
    # but its mtime is back-dated to 2026-04-10 (pre-cutoff).
    table_path = _write_table(tmp_path, [{
        "strategy_id": "BAZ_STRATEGY",
        "strategy_name": "Baz",
        "status": "LIVE",
        "per_regime": {r: _claimed_sharpe_cell(0.6) for r in REGIMES},
    }])
    results_dir = tmp_path / "results"
    art_dir = results_dir / "compliance_BAZ_STRATEGY_20260410T120000Z"
    art_dir.mkdir(parents=True)
    (art_dir / "gate_checklist.json").write_text('{"decision":"PASS"}', encoding="utf-8")

    # Back-date the artefact to 2026-04-10.
    pre_cutoff_ts = datetime(2026, 4, 10, tzinfo=timezone.utc).timestamp()
    os.utime(art_dir, (pre_cutoff_ts, pre_cutoff_ts))

    report = audit_incumbents.audit(
        table_path=table_path,
        results_dir=results_dir,
        cutoff_date_iso="2026-04-23",
    )
    row = report["per_strategy"][0]
    assert all(v == "STALE" for v in row["per_regime_verdict"].values()), \
        f"expected all STALE, got {row['per_regime_verdict']}"
    assert row["re_qualification_priority"] == "HIGH"
    assert report["summary"]["cells_stale"] == 5
    assert row["backing_artefact_path"] is not None


def test_audit_emits_valid_json_schema(tmp_path):
    """Report top-level keys exist and per_strategy rows have required fields."""
    table_path = _write_table(tmp_path, [{
        "strategy_id": "QUX_STRATEGY",
        "strategy_name": "Qux",
        "status": "LIVE",
        "per_regime": {r: _insufficient_power_cell() for r in REGIMES},
    }])
    empty_results_dir = tmp_path / "results_empty"
    empty_results_dir.mkdir()

    report = audit_incumbents.audit(
        table_path=table_path,
        results_dir=empty_results_dir,
        cutoff_date_iso="2026-04-23",
    )

    for key in ("audit_timestamp_iso", "audit_commit_sha", "cutoff_date_iso",
                "per_strategy", "summary"):
        assert key in report, f"missing top-level key: {key}"

    for key in ("total_rows", "total_cells", "cells_backed",
                "cells_correctly_insufficient", "cells_should_have_been_run",
                "cells_stale"):
        assert key in report["summary"], f"missing summary key: {key}"

    row = report["per_strategy"][0]
    for key in ("strategy_id", "strategy_name", "status", "per_regime_verdict",
                "backing_artefact_path", "artefact_mtime_iso",
                "re_qualification_priority", "notes"):
        assert key in row, f"missing per_strategy key: {key}"
    assert set(row["per_regime_verdict"].keys()) == set(REGIMES)

    # Round-trip through JSON to prove it's serialisable.
    json.dumps(report)
