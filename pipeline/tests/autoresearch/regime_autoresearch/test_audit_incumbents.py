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


def _cross_regime_fail_cell(artefact_path: str = "fake/path") -> dict:
    """Cell explicitly tagged as backed by a pooled cross-regime FAIL artefact."""
    return {
        "n_obs": 0, "sharpe_point": None,
        "sharpe_ci_low": None, "sharpe_ci_high": None,
        "p_value_vs_zero": None, "p_value_vs_buy_hold": None,
        "compliance_artifact_path": artefact_path,
        "status_flag": "CROSS_REGIME_FAIL",
    }


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


def test_audit_classifies_cross_regime_fail_as_backed(tmp_path):
    """CROSS_REGIME_FAIL cell + compliance_artifact_path -> BACKED_AS_CROSS_REGIME_FAIL.

    Validates the closed-verdict path: cell explicitly documents that backing
    artefact is a pooled cross-regime FAIL, per-regime metrics correctly absent.
    Priority should drop to NONE (not HIGH like SHOULD_HAVE_BEEN_RUN).
    """
    # Use a real path under tmp_path so the artefact exists on disk and is
    # found by _find_artefact_for_strategy. The strategy_id is matched to
    # the directory name via case-insensitive substring search.
    results_dir = tmp_path / "results"
    art_dir = results_dir / "compliance_xreg_strategy_pooled"
    art_dir.mkdir(parents=True)
    (art_dir / "gate_checklist.json").write_text(
        '{"decision":"FAIL"}', encoding="utf-8"
    )

    artefact_rel_path = "compliance_xreg_strategy_pooled"
    table_path = _write_table(tmp_path, [{
        "strategy_id": "XREG_STRATEGY",
        "strategy_name": "Cross-regime",
        "status": "LIVE",
        "backing_artefact_kind": "pooled_cross_regime",
        "per_regime": {r: _cross_regime_fail_cell(artefact_rel_path)
                       for r in REGIMES},
    }])

    report = audit_incumbents.audit(
        table_path=table_path,
        results_dir=results_dir,
        cutoff_date_iso="2026-04-23",
    )
    row = report["per_strategy"][0]
    assert all(v == "BACKED_AS_CROSS_REGIME_FAIL"
               for v in row["per_regime_verdict"].values()), \
        f"expected all BACKED_AS_CROSS_REGIME_FAIL, got {row['per_regime_verdict']}"
    assert row["re_qualification_priority"] == "NONE"
    assert report["summary"]["cells_backed_cross_regime_fail"] == 5
    assert report["summary"]["cells_should_have_been_run"] == 0
    assert report["summary"]["cells_stale"] == 0
    # Note string mentions pooled cross-regime FAIL.
    assert "cross-regime" in row["notes"].lower()


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
                "cells_backed_cross_regime_fail",
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
