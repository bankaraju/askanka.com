"""Tests for v2 proposal log sharding (Task 5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_v1_log_renamed_and_row_count_preserved():
    from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR
    new_path = DATA_DIR / "proposal_log_neutral.jsonl"
    old_path = DATA_DIR / "proposal_log.jsonl"
    assert new_path.exists(), (
        "v2: proposal_log_neutral.jsonl must exist (renamed from "
        "proposal_log.jsonl via git mv in Task 5)."
    )
    assert not old_path.exists(), (
        "v2: legacy proposal_log.jsonl must be gone (git mv, not git cp)."
    )
    lines = [l for l in new_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 20, (
        f"Expected >=20 v1 rows preserved in rename; got {len(lines)}"
    )
    # Each surviving row must be valid JSON and carry regime=NEUTRAL
    # (the v1 pilot only touched NEUTRAL).
    for line in lines:
        row = json.loads(line)
        assert row.get("regime") == "NEUTRAL", (
            f"v1 row has non-NEUTRAL regime: {row.get('regime')!r}"
        )


def test_per_regime_log_path_resolver():
    from pipeline.autoresearch.regime_autoresearch.proposer import (
        log_path_for_regime,
    )
    from pipeline.autoresearch.regime_autoresearch.constants import (
        DATA_DIR, REGIMES,
    )
    # Slug map: REGIMES tuple values -> filesystem slugs
    # (dash -> underscore, uppercase -> lower).
    expected = {
        "RISK-OFF": DATA_DIR / "proposal_log_risk_off.jsonl",
        "CAUTION": DATA_DIR / "proposal_log_caution.jsonl",
        "NEUTRAL": DATA_DIR / "proposal_log_neutral.jsonl",
        "RISK-ON": DATA_DIR / "proposal_log_risk_on.jsonl",
        "EUPHORIA": DATA_DIR / "proposal_log_euphoria.jsonl",
    }
    for regime in REGIMES:
        assert log_path_for_regime(regime) == expected[regime], (
            f"path mismatch for {regime}"
        )
    with pytest.raises(ValueError):
        log_path_for_regime("UNKNOWN")


def test_new_proposer_rows_carry_schema_version_v2(tmp_path, monkeypatch):
    """Assert rows built by _make_row carry schema_version='v2'.

    run_pilot.py owns _make_row (the write path) — not proposer.py.
    We import it directly and call it with a minimal Proposal to verify
    the schema_version field is present on every new row.
    """
    from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
    # Import _make_row from run_pilot (the actual write-path owner).
    import pipeline.autoresearch.regime_autoresearch.scripts.run_pilot as run_pilot
    proposal = Proposal(
        construction_type="long_short_basket",
        feature="ret_1d",
        threshold_op="top_k",
        threshold_value=10,
        hold_horizon=5,
        regime="NEUTRAL",
        pair_id=None,
    )
    row = run_pilot._make_row(proposal, "APPROVED", result=None,
                              hurdle_sharpe=None, hurdle_source=None)
    assert row["schema_version"] == "v2", (
        f"Expected schema_version='v2' in new row; got {row.get('schema_version')!r}"
    )
    assert row["regime"] == "NEUTRAL"
