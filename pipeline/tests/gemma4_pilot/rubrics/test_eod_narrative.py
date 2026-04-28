"""Tests for the EOD-narrative rubric.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 9)
"""
from __future__ import annotations

from pipeline.gemma4_pilot.rubrics.eod_narrative import score


META = {
    "regime": "RISK_ON",
    "positions": [
        {"ticker": "RELIANCE", "side": "LONG", "pnl_pct": 1.42},
        {"ticker": "TCS", "side": "SHORT", "pnl_pct": -0.31},
    ],
}


def test_pass_short_well_grounded_narrative():
    text = (
        "Today closed in RISK_ON. RELIANCE long booked +1.4% and TCS short "
        "printed -0.3% on the day. Net basket: +1.1%. Tomorrow watch oil "
        "and the rupee. Volatility was light and the FII flow stayed "
        "constructive. Stops held overnight, basket delivered as planned."
    )
    r = score(text, META)
    assert r["pass"] is True, r["notes"]


def test_fail_too_short():
    r = score("Quiet day.", META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_too_long():
    r = score("X" * 700, META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_missing_regime_mention():
    text = "RELIANCE long booked 1.4% and TCS short bled 0.3%. " * 4
    r = score(text, META)
    assert r["pass"] is False
    assert "regime" in r["notes"].lower()


def test_fail_no_position_mention():
    text = "RISK_ON regime today. " * 12
    r = score(text, META)
    assert r["pass"] is False
    assert "position" in r["notes"].lower()


def test_fail_wrong_pnl_number():
    text = (
        "RISK_ON closed flat on the day. RELIANCE long booked 9.99% well "
        "above expectation, while TCS short held in line with the model. "
        "Light volatility through the session, stops held overnight. The "
        "basket delivered as planned. Tomorrow watch oil and the rupee, "
        "FII flow constructive on net."
    )
    # ledger says 1.42% — 9.99% should be flagged as a wrong number
    r = score(text, META)
    assert r["pass"] is False
    assert "number" in r["notes"].lower() or "pnl" in r["notes"].lower()
