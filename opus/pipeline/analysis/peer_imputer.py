"""
Sector peer trust score imputation.

For stocks without enough transcripts for direct scoring,
impute from scored sector peers. Capped at B+ grade.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("opus.peer_imputer")

DEFAULT_UNIVERSE = Path(__file__).parent.parent.parent / "config" / "universe.json"

GRADE_ORDER = ["F", "D", "C", "C+", "B", "B+", "A", "A+"]
MAX_IMPUTED_GRADE = "B+"


def _score_to_grade(score: float) -> str:
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "C+"
    elif score >= 35:
        return "C"
    elif score >= 25:
        return "D"
    return "F"


def _cap_grade(grade: str) -> str:
    try:
        if GRADE_ORDER.index(grade) > GRADE_ORDER.index(MAX_IMPUTED_GRADE):
            return MAX_IMPUTED_GRADE
    except ValueError:
        pass
    return grade


def _find_sector_peers(symbol: str, universe_path: Path) -> list[str]:
    try:
        universe = json.loads(universe_path.read_text(encoding="utf-8"))
        for sector_data in universe.get("sectors", {}).values():
            stocks = sector_data.get("stocks", [])
            if symbol in stocks:
                return [s for s in stocks if s != symbol]
    except Exception as exc:
        log.warning("Failed to load universe for peer lookup: %s", exc)
    return []


def impute_trust_score(
    symbol: str,
    scored_stocks: dict[str, dict],
    universe_path: Path = DEFAULT_UNIVERSE,
) -> Optional[dict]:
    peers = _find_sector_peers(symbol, universe_path)
    if not peers:
        log.info("  %s: no sector peers found — cannot impute", symbol)
        return None

    scored_peers = [(p, scored_stocks[p]) for p in peers if p in scored_stocks]
    if not scored_peers:
        log.info("  %s: no scored peers among %s — cannot impute", symbol, peers)
        return None

    avg_score = sum(s["trust_score"] for _, s in scored_peers) / len(scored_peers)
    raw_grade = _score_to_grade(avg_score)
    capped_grade = _cap_grade(raw_grade)

    result = {
        "trust_score": round(avg_score, 1),
        "grade": capped_grade,
        "trust_source": "PEER_IMPUTED",
        "peer_count": len(scored_peers),
        "peer_symbols": [p for p, _ in scored_peers],
    }

    log.info("  %s: imputed %.1f (%s) from %d peers %s",
             symbol, avg_score, capped_grade, len(scored_peers), result["peer_symbols"])
    return result
