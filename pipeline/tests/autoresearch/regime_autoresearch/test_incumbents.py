"""Coverage for incumbents.py: loader + clean filter + scarcity fallback hurdle."""
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


def test_hurdle_uses_best_incumbent_when_enough_clean():
    """>=3 clean incumbents -> hurdle = max-Sharpe incumbent."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.30}},
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.15, "sharpe_point": 0.50}},  # best
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.08, "sharpe_point": 0.40}},
    ])
    sentinel_called = []

    def buy_hold_fn(regime):
        sentinel_called.append(regime)
        return 0.0  # should NOT be consulted when enough clean incumbents exist

    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL", buy_hold_fn)
    assert hurdle == 0.50
    assert source == "incumbent:INC_1"
    assert sentinel_called == []  # buy-and-hold path was not taken


def test_hurdle_falls_back_to_buy_hold_on_scarcity():
    """<3 clean incumbents -> hurdle = buy_and_hold_fn(regime)."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "CLEAN", "sharpe_ci_low": 0.10, "sharpe_point": 0.30}},
        {"NEUTRAL": {"status_flag": "INSUFFICIENT_POWER", "sharpe_ci_low": None, "sharpe_point": None}},
    ])

    def buy_hold_fn(regime):
        assert regime == "NEUTRAL"
        return 0.18

    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL", buy_hold_fn)
    assert hurdle == 0.18
    assert source == "scarcity_fallback:buy_and_hold"


def test_hurdle_falls_back_to_buy_hold_when_zero_clean():
    """0 clean incumbents (Task 0e seed state) -> buy-and-hold."""
    table = _make_table([
        {"NEUTRAL": {"status_flag": "INSUFFICIENT_POWER", "sharpe_ci_low": None, "sharpe_point": None}},
    ])

    hurdle, source = hurdle_sharpe_for_regime(table, "NEUTRAL",
                                              lambda r: 0.22)
    assert hurdle == 0.22
    assert source == "scarcity_fallback:buy_and_hold"
