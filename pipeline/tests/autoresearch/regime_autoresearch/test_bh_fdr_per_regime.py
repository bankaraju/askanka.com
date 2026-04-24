"""Tests for v2 per-regime BH-FDR trigger (Task 6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_preg_rows(path: Path, n: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(
        json.dumps({
            "proposal_id": f"P-{i:04x}",
            "regime": "NEUTRAL",
            "p_value": 0.01 if i < 2 else 0.5,
            "pre_registered_at": "2026-04-25T00:00:00+00:00",
        })
        for i in range(n)
    ) + "\n")


def test_bh_fdr_fires_when_ten_accumulated(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=10)
    state = {"last_batch_date": "2026-04-20T00:00:00+00:00"}
    assert should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )


def test_bh_fdr_fires_when_thirty_days_elapsed(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=3)  # < 10
    state = {"last_batch_date": "2026-03-20T00:00:00+00:00"}  # > 30 days
    assert should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )


def test_bh_fdr_does_not_fire_when_low_count_and_recent(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.run_bh_fdr_check \
        import should_fire_batch_for_regime
    preg_path = tmp_path / "pre_registered_neutral.jsonl"
    _write_preg_rows(preg_path, n=3)
    state = {"last_batch_date": "2026-04-20T00:00:00+00:00"}
    assert not should_fire_batch_for_regime(
        preg_path, state, now_iso="2026-04-25T00:00:00+00:00",
    )
