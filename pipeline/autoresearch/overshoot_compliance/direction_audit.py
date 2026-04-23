"""Direction audit per §8 of backtesting-specs.txt v1.0.

Cross-checks each backtest survivor's fade direction (UP→SHORT, DOWN→LONG)
against the production engine's current call. Mismatch is flagged
DIRECTION-CONFLICT — P0 per §8.
"""
from __future__ import annotations

from typing import Iterable


def _fade_sign(direction: str) -> str:
    return "SHORT" if direction == "UP" else "LONG"


def audit(
    survivors: Iterable[dict],
    engine_calls: dict[str, dict],
) -> dict:
    rows = []
    conflicts = 0
    for s in survivors:
        fade = _fade_sign(s["direction"])
        call = engine_calls.get(s["ticker"])
        if call is None:
            rows.append({
                "ticker": s["ticker"], "backtest_direction": s["direction"],
                "fade_trade": fade, "engine_direction": None, "conflict": None,
            })
            continue
        engine_dir = call.get("direction")
        is_conflict = (engine_dir != fade)
        if is_conflict:
            conflicts += 1
        rows.append({
            "ticker": s["ticker"], "backtest_direction": s["direction"],
            "fade_trade": fade, "engine_direction": engine_dir, "conflict": is_conflict,
        })
    return {"conflicts": conflicts, "n_survivors": len(rows), "rows": rows}
