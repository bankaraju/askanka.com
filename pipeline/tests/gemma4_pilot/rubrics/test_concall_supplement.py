"""Tests for the concall-supplement rubric.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 7)
"""
from __future__ import annotations

import json

from pipeline.gemma4_pilot.rubrics.concall_supplement import score


UNIVERSE = {"RELIANCE", "TCS", "INFY", "HDFCBANK"}


def test_pass_when_valid_json_three_points_no_hallucination():
    text = json.dumps(
        {
            "ticker": "RELIANCE",
            "signal_points": [
                {"point": "Refining margins guided up", "stance": "BULLISH"},
                {"point": "Capex peak behind us", "stance": "BULLISH"},
                {"point": "Telecom ARPU stalling", "stance": "BEARISH"},
            ],
        }
    )
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is True
    assert r["score"] == 1.0


def test_fail_when_invalid_json():
    r = score("this is not json", {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert r["score"] == 0.0
    assert "json" in r["notes"].lower()


def test_fail_when_fewer_than_three_signal_points():
    text = json.dumps(
        {
            "ticker": "RELIANCE",
            "signal_points": [{"point": "only one", "stance": "BULLISH"}],
        }
    )
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert "3" in r["notes"]


def test_fail_when_hallucinated_ticker_appears_in_text():
    text = json.dumps(
        {
            "ticker": "RELIANCE",
            "signal_points": [
                {
                    "point": "Refining and FAKETICKER competition",
                    "stance": "BEARISH",
                },
                {"point": "Capex peak behind us", "stance": "BULLISH"},
                {"point": "Telecom ARPU stalling", "stance": "BEARISH"},
            ],
        }
    )
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is False
    assert "halluc" in r["notes"].lower()


def test_pass_when_known_ticker_referenced():
    """Cross-references to other universe tickers are allowed."""
    text = json.dumps(
        {
            "ticker": "RELIANCE",
            "signal_points": [
                {
                    "point": "Telecom competition vs vodafone idea",
                    "stance": "BEARISH",
                },
                {
                    "point": "Better than TCS in capex discipline",
                    "stance": "BULLISH",
                },
                {"point": "Telecom ARPU stalling", "stance": "BEARISH"},
            ],
        }
    )
    r = score(text, {"ticker": "RELIANCE", "universe": UNIVERSE})
    assert r["pass"] is True
