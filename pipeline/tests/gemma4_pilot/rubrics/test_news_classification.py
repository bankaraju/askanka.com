"""Tests for the news-classification rubric.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 8)
"""
from __future__ import annotations

import json

from pipeline.gemma4_pilot.rubrics.news_classification import (
    CANONICAL_SECTORS,
    score,
)


def test_pass_valid():
    text = json.dumps(
        {
            "label": "BULLISH",
            "confidence": 0.82,
            "sector": "Banking & Financials",
        }
    )
    r = score(text, {})
    assert r["pass"] is True
    assert r["score"] == 1.0


def test_fail_invalid_label():
    text = json.dumps({"label": "MAYBE", "confidence": 0.5, "sector": "IT"})
    r = score(text, {})
    assert r["pass"] is False
    assert "label" in r["notes"]


def test_fail_confidence_out_of_range():
    text = json.dumps(
        {
            "label": "BEARISH",
            "confidence": 1.7,
            "sector": "Banking & Financials",
        }
    )
    r = score(text, {})
    assert r["pass"] is False
    assert "confidence" in r["notes"]


def test_fail_unknown_sector():
    text = json.dumps({"label": "NEUTRAL", "confidence": 0.5, "sector": "Crypto"})
    r = score(text, {})
    assert r["pass"] is False
    assert "sector" in r["notes"]


def test_canonical_sectors_includes_banking_and_it():
    """Smoke check on the canonical list shape."""
    assert "Banking & Financials" in CANONICAL_SECTORS
    assert "IT" in CANONICAL_SECTORS
