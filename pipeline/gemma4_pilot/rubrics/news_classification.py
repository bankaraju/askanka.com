"""Rubric for Task #2 -- news classification + sentiment.

Pass criteria from spec §3.1:
  1. label ∈ {BULLISH, BEARISH, NEUTRAL, NOT_RELEVANT}
  2. confidence ∈ [0, 1]
  3. sector tag from a canonical sector list

Canonical sector list lifted from pipeline/config/sector_map.json if it
exists; otherwise a hardcoded fallback covering the working universe.
The fallback list is kept in sync with sector_taxonomy.json the next
time a sector is added.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 8)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

_VALID_LABELS = {"BULLISH", "BEARISH", "NEUTRAL", "NOT_RELEVANT"}

_SECTOR_MAP_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "sector_map.json"
)


def _load_sectors() -> set[str]:
    if not _SECTOR_MAP_PATH.exists():
        # Fallback so tests don't depend on the live file
        return {
            "Banking & Financials",
            "IT",
            "Auto",
            "FMCG",
            "Pharma",
            "Metals",
            "Oil & Gas",
            "Power",
            "Realty",
            "Telecom",
            "Capital Goods",
            "Cement",
            "Chemicals",
            "Consumer Durables",
            "Media",
        }
    raw = json.loads(_SECTOR_MAP_PATH.read_text())
    if isinstance(raw, dict):
        return set(raw.values())
    return set(raw)


CANONICAL_SECTORS = _load_sectors()


def score(text: str, meta: Mapping[str, Any]) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"score": 0.0, "pass": False, "notes": f"invalid_json: {e}"}

    if not isinstance(data, dict):
        return {"score": 0.0, "pass": False, "notes": "json_not_object"}

    label = data.get("label")
    if label not in _VALID_LABELS:
        return {"score": 0.0, "pass": False, "notes": f"bad_label: {label!r}"}

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"bad_confidence: {conf!r}",
        }

    sector = data.get("sector")
    if sector not in CANONICAL_SECTORS:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"unknown_sector: {sector!r} (must be in canonical list)",
        }

    return {"score": 1.0, "pass": True, "notes": "ok"}
