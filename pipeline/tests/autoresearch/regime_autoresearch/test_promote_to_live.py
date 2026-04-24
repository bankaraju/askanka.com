"""Tests for v2 human-gated promote_to_live CLI (Task 6)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def _fake_pending_row(rule_id: str, regime: str = "NEUTRAL") -> dict:
    return {
        "proposal_id": rule_id,
        "regime": regime,
        "construction_type": "top_k",
        "feature": "return_5d",
        "threshold_op": "top_k",
        "threshold_value": 10,
        "hold_horizon": 5,
        "state": "FORWARD_SHADOW_PASS",
        "forward_sharpe": 1.2,
        "incumbent_sharpe": 0.8,
    }


def test_promote_to_live_refuses_nonexistent_rule(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live \
        import main
    pending_path = tmp_path / "pending_live_promotion.jsonl"
    pending_path.touch()
    exit_code = main([
        "--rule-id", "P-does-not-exist",
        "--pending-path", str(pending_path),
    ])
    assert exit_code != 0


def test_promote_to_live_refuses_non_forward_shadow_pass(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.scripts.promote_to_live \
        import main
    pending_path = tmp_path / "pending_live_promotion.jsonl"
    row = _fake_pending_row("P-abcd1234")
    row["state"] = "HOLDOUT_PASS"  # not yet forward-shadow
    pending_path.write_text(json.dumps(row) + "\n")
    exit_code = main([
        "--rule-id", "P-abcd1234",
        "--pending-path", str(pending_path),
    ])
    assert exit_code != 0
