"""Coverage for incumbents.py: loader + clean filter + per-regime mean hurdle.

v2: scarcity fallback removed; hurdle_sharpe_for_regime no longer accepts a
buy_hold_sharpe_fn. Tests updated accordingly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.autoresearch.regime_autoresearch.incumbents import (
    clean_incumbents_for_regime,
    hurdle_sharpe_for_regime,
    load_table,
)


def _make_table(cells_per_incumbent: list[dict[str, dict]]) -> dict:
    """Build a strategy_results_10-shaped table for testing.

    cells_per_incumbent is a list of per_regime dicts, one per incumbent.
    """
    return {
        "incumbents": [
            {"strategy_id": f"INC_{i}", "per_regime": cells}
            for i, cells in enumerate(cells_per_incumbent)
        ],
    }


def test_load_table_reads_json(tmp_path):
    p = tmp_path / "sr.json"
    p.write_text(json.dumps({"incumbents": []}))
    out = load_table(p)
    assert out == {"incumbents": []}


def test_load_table_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_table(tmp_path / "nope.json")


def test_clean_incumbents_filters_insufficient_power():
    table = _make_table([
        {"NEUTRAL": {"status_flag": "INSUFFICIENT_POWER", "sharpe_ci_low": None, "sharpe_point": None}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.45}},
    ])
    clean = clean_incumbents_for_regime(table, "NEUTRAL")
    assert len(clean) == 1
    assert clean[0]["strategy_id"] == "INC_1"


def test_clean_incumbents_rejects_non_positive_ci_low():
    table = _make_table([
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": -0.02, "sharpe_point": 0.30}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.0, "sharpe_point": 0.20}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.05, "sharpe_point": 0.25}},
    ])
    clean = clean_incumbents_for_regime(table, "NEUTRAL")
    # Only the one with sharpe_ci_low=0.05 survives (strictly > 0)
    assert len(clean) == 1
    assert clean[0]["strategy_id"] == "INC_2"


def test_clean_incumbents_missing_regime_returns_empty():
    table = _make_table([
        {"RISK-ON": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.40}},
    ])
    # Asking for NEUTRAL when only RISK-ON has cells
    clean = clean_incumbents_for_regime(table, "NEUTRAL")
    assert clean == []


def test_hurdle_returns_mean_of_clean_incumbents():
    """v2: hurdle = mean Sharpe of all clean incumbents (not max)."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.30}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.15, "sharpe_point": 0.50}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.08, "sharpe_point": 0.40}},
    ])
    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL")
    # mean of 0.30, 0.50, 0.40 = 0.40
    assert abs(hurdle - 0.40) < 1e-9
    assert source == "mean_of_incumbents"


def test_hurdle_returns_mean_when_single_clean():
    """v2: single clean incumbent -> mean_of_incumbents (no scarcity fallback)."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.30}},
        {"NEUTRAL": {"status_flag": "INSUFFICIENT_POWER", "sharpe_ci_low": None, "sharpe_point": None}},
    ])
    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL")
    assert hurdle == 0.30
    assert source == "mean_of_incumbents"


def test_hurdle_returns_no_incumbent_when_zero_clean():
    """v2: 0 clean incumbents -> (0.0, 'no_incumbent'), no fallback."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "INSUFFICIENT_POWER", "sharpe_ci_low": None, "sharpe_point": None}},
    ])
    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL")
    assert hurdle == 0.0
    assert source == "no_incumbent"
