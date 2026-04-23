import json
from pathlib import Path

from pipeline.autoresearch.overshoot_compliance import universe_snapshot as U


def test_snapshot_when_history_file_missing(tmp_path):
    fake = tmp_path / "nope.json"
    snap = U.build_snapshot(
        current_tickers=["A", "B", "C"],
        history_path=fake,
        waiver_path=Path("docs/superpowers/waivers/2026-04-23-phase-c-residual-reversion-survivorship.md"),
    )
    assert snap["n_tickers_current"] == 3
    assert snap["status"] == "SURVIVORSHIP-UNCORRECTED-WAIVED"
    assert snap["coverage_ratio"] is None
    assert "waiver_path" in snap


def test_snapshot_when_history_file_present(tmp_path):
    history = tmp_path / "fno_universe_history.json"
    history.write_text(json.dumps({
        "snapshots": [
            {"month": "2024-12", "symbols": ["A", "B", "C", "X"]},
            {"month": "2025-01", "symbols": ["A", "B", "C"]},
        ]
    }), encoding="utf-8")
    snap = U.build_snapshot(
        current_tickers=["A", "B", "C"],
        history_path=history,
        waiver_path=None,
    )
    assert snap["n_tickers_current"] == 3
    assert snap["n_tickers_ever"] == 4
    assert snap["n_tickers_delisted"] == 1
    assert snap["coverage_ratio"] == 0.25
    assert snap["status"] == "SURVIVORSHIP-CORRECTED"
