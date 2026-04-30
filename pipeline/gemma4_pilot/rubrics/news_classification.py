"""Rubric for news classification (Tier-2 Gemini classifier in political_signals.py).

Production prompt expects JSON shape: {"category": <name|null>, "confidence": <float>}
where category is one of pipeline.config.EVENT_TAXONOMY keys (or null).

Pass criteria:
  1. Output parses as JSON object.
  2. "category" is either null OR a key in EVENT_TAXONOMY.
  3. "confidence" is a float in [0, 1].

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
"""
from __future__ import annotations

import json
from typing import Any, Mapping


def _load_categories() -> set[str]:
    try:
        from pipeline.config import EVENT_TAXONOMY
        return set(EVENT_TAXONOMY.keys())
    except Exception:
        # Fallback so tests don't depend on the live config
        return {
            "escalation", "de_escalation", "ceasefire",
            "oil_positive", "oil_negative", "sanctions",
            "hormuz", "defense_spend", "trump_threat", "diplomacy",
            "rbi_policy", "nbfc_reform", "ev_policy",
            "tax_reform", "infra_capex", "sebi_regulation",
        }


CANONICAL_CATEGORIES = _load_categories()


def score(text: str, meta: Mapping[str, Any]) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"score": 0.0, "pass": False, "notes": f"invalid_json: {e}"}

    if not isinstance(data, dict):
        return {"score": 0.0, "pass": False, "notes": "json_not_object"}

    cat = data.get("category")
    if cat is not None and cat not in CANONICAL_CATEGORIES:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"unknown_category: {cat!r}",
        }

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"bad_confidence: {conf!r}",
        }

    return {"score": 1.0, "pass": True, "notes": "ok"}
