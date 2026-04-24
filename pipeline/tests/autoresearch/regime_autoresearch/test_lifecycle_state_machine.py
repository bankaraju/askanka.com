from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.promotions import (
    VALID_STATES, advance_state, displace_lowest_sharpe,
    rate_limit_passes,
)


def test_valid_states_set():
    assert VALID_STATES == {
        "PROPOSED", "PRE_REGISTERED", "HOLDOUT_PASS",
        "FORWARD_SHADOW", "PROMOTED_LIVE", "RETIRED", "DEAD",
    }


def test_advance_forward():
    assert advance_state("PROPOSED") == "PRE_REGISTERED"
    assert advance_state("PRE_REGISTERED") == "HOLDOUT_PASS"
    assert advance_state("HOLDOUT_PASS") == "FORWARD_SHADOW"
    assert advance_state("FORWARD_SHADOW") == "PROMOTED_LIVE"


def test_advance_terminal_raises():
    with pytest.raises(ValueError):
        advance_state("RETIRED")
    with pytest.raises(ValueError):
        advance_state("DEAD")


def test_displace_lowest_sharpe():
    slots = [
        {"strategy_id": "A", "sharpe": 0.3},
        {"strategy_id": "B", "sharpe": 0.5},
        {"strategy_id": "C", "sharpe": 0.2},
    ]
    kept, retired = displace_lowest_sharpe(slots, new_strategy_id="D", new_sharpe=0.4)
    assert retired["strategy_id"] == "C"
    assert {s["strategy_id"] for s in kept} == {"A", "B", "D"}


def test_rate_limit_allows_under_cap():
    assert rate_limit_passes(promotions_this_quarter=1, cap=2) is True
    assert rate_limit_passes(promotions_this_quarter=2, cap=2) is False
