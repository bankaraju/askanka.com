"""Kill-switch checker for the legacy news-driven spread framework.

Per spec §13: on V1 holdout pass (verdict.json["pass"] == True), the
news-driven framework is killed. Live engines call
``is_news_driven_killed()`` at the top of their hot path and short-circuit
when this returns True.
"""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
VERDICT_PATH = PIPELINE_ROOT / "data" / "research" / "h_2026_04_29_intraday_v1" / "verdict_2026_07_04.json"


def is_news_driven_killed() -> bool:
    """Return True iff V1 holdout verdict exists and shows pass."""
    if not VERDICT_PATH.exists():
        return False
    try:
        v = json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(v.get("pass", False))
