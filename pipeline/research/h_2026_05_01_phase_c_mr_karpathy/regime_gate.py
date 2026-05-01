"""Regime gate for the Phase C MR Karpathy v1 engine.

Spec section 6 step 5: skip if regime not in {RISK-ON, CAUTION}.

Reads the V3 CURATED-30 PIT regime tape; falls back to today_regime.json
for the live tape (post-2026-05-04 holdout).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIT_TAPE_PATH = REPO / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
LIVE_TAPE_PATH = REPO / "pipeline" / "data" / "today_regime.json"

ALLOWED = frozenset({"RISK-ON", "CAUTION"})


def regime_for_date(date_str: str) -> str | None:
    """Return the V3 CURATED-30 regime label for `date_str`, or None if missing.

    Looks up the PIT tape first; if `date_str` is today and PIT row absent, falls
    back to today_regime.json for forward live operation.
    """
    label = _from_pit_tape(date_str)
    if label is not None:
        return label
    return _from_live_tape(date_str)


def is_allowed(date_str: str) -> bool:
    """True if regime label for `date_str` is in {RISK-ON, CAUTION}."""
    label = regime_for_date(date_str)
    return label in ALLOWED


def _from_pit_tape(date_str: str) -> str | None:
    if not PIT_TAPE_PATH.is_file():
        return None
    with PIT_TAPE_PATH.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            if row.get("date") == date_str:
                lbl = row.get("regime") or row.get("label") or row.get("v3_curated_30")
                return lbl.strip() if lbl else None
    return None


def _from_live_tape(date_str: str) -> str | None:
    if not LIVE_TAPE_PATH.is_file():
        return None
    try:
        payload = json.loads(LIVE_TAPE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("date") != date_str:
        return None
    return payload.get("regime") or payload.get("label")
