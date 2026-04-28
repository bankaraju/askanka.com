"""Rubric for Task #3 -- EOD Telegram trade narrative.

Pass criteria from spec §3.1:
  1. Length 200-600 chars (Telegram-friendly).
  2. Mentions today's regime label.
  3. Mentions at least one position from the day's ledger.
  4. Per-position pnl numbers cited near a ticker name must be within
     0.5 percentage points of the ledger's pnl_pct for that ticker.

Number-grounding heuristic: extract every percent figure from the text;
for each mentioned ticker, the closest percent figure within 80 chars
of the ticker name must be within 0.5 pp of the ledger value. The
human pairwise audit catches cases this misses.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 9)
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_PCT_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)\s*%")
_MIN_LEN = 200
_MAX_LEN = 600
_PCT_TOL = 0.5  # percentage-points tolerance


def score(text: str, meta: Mapping[str, Any]) -> dict:
    n = len(text)
    if n < _MIN_LEN or n > _MAX_LEN:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"length: {n} chars not in [{_MIN_LEN}, {_MAX_LEN}]",
        }

    regime = str(meta.get("regime", ""))
    if regime and regime.upper() not in text.upper():
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"regime '{regime}' not mentioned",
        }

    positions = meta.get("positions") or []
    upper = text.upper()
    mentioned = [p for p in positions if p["ticker"].upper() in upper]
    if not mentioned:
        return {
            "score": 0.0,
            "pass": False,
            "notes": "no position mentioned from the day's ledger",
        }

    # Number-grounding: check each mentioned ticker's pnl
    for p in mentioned:
        ticker = p["ticker"].upper()
        true_pct = float(p["pnl_pct"])
        idx = upper.find(ticker)
        if idx < 0:
            continue
        # Look in an 80-char window after the ticker mention
        window = text[idx : idx + 80]
        pcts = [float(m) for m in _PCT_RE.findall(window)]
        if not pcts:
            continue
        nearest = min(pcts, key=lambda x: abs(x - true_pct))
        if abs(nearest - true_pct) > _PCT_TOL:
            return {
                "score": 0.0,
                "pass": False,
                "notes": (
                    f"wrong_pnl_number: {ticker} text says {nearest}% but "
                    f"ledger says {true_pct}%"
                ),
            }

    return {"score": 1.0, "pass": True, "notes": "ok"}
