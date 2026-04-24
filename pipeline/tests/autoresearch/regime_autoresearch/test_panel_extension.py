"""Tests for v2 panel extension (Task 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def test_panel_start_constant_exists_and_is_2020_04_23():
    from pipeline.autoresearch.regime_autoresearch import constants
    assert hasattr(constants, "PANEL_START"), (
        "v2 requires PANEL_START in constants.py"
    )
    assert constants.PANEL_START == "2020-04-23", (
        f"PANEL_START must be '2020-04-23' (252 trading days before "
        f"TRAIN_VAL_START); got {constants.PANEL_START!r}"
    )
    # Must stay strictly earlier than TRAIN_VAL_START.
    assert pd.Timestamp(constants.PANEL_START) < pd.Timestamp(
        constants.TRAIN_VAL_START
    )


def test_panel_coverage_audit_json_shape():
    from pipeline.autoresearch.regime_autoresearch import constants
    audit_path = constants.DATA_DIR / "panel_coverage_audit_2026-04-25.json"
    assert audit_path.exists(), (
        f"Missing {audit_path}; rerun build_regime_history.py for v2."
    )
    obj = json.loads(audit_path.read_text())
    for k in ("generated_at", "panel_start", "train_val_end",
              "retained_tickers", "dropped_tickers", "coverage_threshold"):
        assert k in obj, f"audit JSON missing key {k!r}"
    assert obj["coverage_threshold"] == {"max_missing_days": 100}
    assert obj["panel_start"] == constants.PANEL_START
    assert obj["train_val_end"] == constants.TRAIN_VAL_END
    assert isinstance(obj["retained_tickers"], list)
    assert len(obj["retained_tickers"]) > 0
    assert isinstance(obj["dropped_tickers"], list)
    overlap = set(obj["retained_tickers"]) & {
        d["ticker"] for d in obj["dropped_tickers"]
    }
    assert not overlap, f"Tickers in both retained and dropped: {overlap}"
