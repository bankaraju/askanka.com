"""Test that run_pilot uses load_null_basket_hurdle (v2), not regime_buy_and_hold."""
from __future__ import annotations
import pathlib


def test_run_pilot_imports_load_null_basket_hurdle():
    run_pilot = pathlib.Path(
        "pipeline/autoresearch/regime_autoresearch/scripts/run_pilot.py"
    )
    src = run_pilot.read_text()
    assert "load_null_basket_hurdle" in src


def test_incumbents_no_longer_has_scarcity_fallback_branch():
    incumbents = pathlib.Path(
        "pipeline/autoresearch/regime_autoresearch/incumbents.py"
    )
    src = incumbents.read_text()
    assert "scarcity_fallback:buy_and_hold" not in src
    assert "INCUMBENT_SCARCITY_MIN" not in src
