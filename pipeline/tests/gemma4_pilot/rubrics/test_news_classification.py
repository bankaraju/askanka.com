"""Tests for the news-classification rubric.

Validates the production schema produced by political_signals.classify_event_claude:
    {"category": <EVENT_TAXONOMY key | null>, "confidence": <float in [0,1]>}
"""
from __future__ import annotations

import json

from pipeline.gemma4_pilot.rubrics.news_classification import (
    CANONICAL_CATEGORIES,
    score,
)


def test_pass_valid_category():
    text = json.dumps({"category": "escalation", "confidence": 0.82})
    r = score(text, {})
    assert r["pass"] is True
    assert r["score"] == 1.0


def test_pass_null_category():
    text = json.dumps({"category": None, "confidence": 0.0})
    r = score(text, {})
    assert r["pass"] is True


def test_fail_unknown_category():
    text = json.dumps({"category": "made_up_thing", "confidence": 0.5})
    r = score(text, {})
    assert r["pass"] is False
    assert "category" in r["notes"]


def test_fail_confidence_out_of_range():
    text = json.dumps({"category": "ceasefire", "confidence": 1.7})
    r = score(text, {})
    assert r["pass"] is False
    assert "confidence" in r["notes"]


def test_fail_invalid_json():
    r = score("not json", {})
    assert r["pass"] is False
    assert "invalid_json" in r["notes"]


def test_canonical_categories_includes_known_keys():
    assert "escalation" in CANONICAL_CATEGORIES
    assert "ceasefire" in CANONICAL_CATEGORIES
    assert "rbi_policy" in CANONICAL_CATEGORIES
