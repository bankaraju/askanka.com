"""Rubric for Task #1 -- concall supplement.

Pass criteria from spec §3.1:
  1. Output is valid JSON matching the trust-score supplement schema
     (ticker, signal_points list of {point, stance}).
  2. Includes 3+ signal points.
  3. No hallucinated tickers -- capitalised tokens that look like
     tickers must either be in the universe or be a recognised
     non-ticker word.

Returns {'score': float in [0,1], 'pass': bool, 'notes': str}.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 7)
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

# Tokens that look ticker-like but aren't tickers in our universe
_NON_TICKER_ALLCAPS = {
    "USD", "EUR", "INR", "GBP", "JPY", "CNY",
    "GAAP", "EBITDA", "ROE", "ROCE", "PAT", "EPS", "DCF", "CAGR", "ARPU",
    "Q1", "Q2", "Q3", "Q4", "FY", "YOY", "QOQ", "MOM",
    "CEO", "CFO", "MD", "AGM", "EGM", "BOD",
    "GST", "TDS", "RBI", "SEBI", "IPO", "FPO", "OFS",
    "AI", "ML", "EV", "ESG", "B2B", "B2C", "API",
    "BULLISH", "BEARISH", "NEUTRAL",
}

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&]{2,15}\b")


def score(text: str, meta: Mapping[str, Any]) -> dict:
    universe = {u.upper() for u in meta.get("universe", set())}

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {"score": 0.0, "pass": False, "notes": f"invalid_json: {e}"}

    if not isinstance(data, dict):
        return {"score": 0.0, "pass": False, "notes": "json_not_object"}

    points = data.get("signal_points")
    if not isinstance(points, list):
        return {
            "score": 0.0,
            "pass": False,
            "notes": "missing_signal_points_list",
        }

    if len(points) < 3:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"only {len(points)} signal_points, need 3+",
        }

    for p in points:
        if not isinstance(p, dict) or "point" not in p or "stance" not in p:
            return {
                "score": 0.0,
                "pass": False,
                "notes": "bad_signal_point_shape",
            }
        if p["stance"] not in {"BULLISH", "BEARISH", "NEUTRAL"}:
            return {
                "score": 0.0,
                "pass": False,
                "notes": f"bad_stance: {p['stance']!r}",
            }

    # Hallucinated-ticker check: only ALL-CAPS tokens in the original text
    # are ticker candidates; normal sentence-case words are not. Real tickers
    # in concall transcripts are written in all-caps (e.g. "TCS", "RELIANCE").
    blob = " ".join(str(p.get("point", "")) for p in points)
    candidates = set(_TICKER_RE.findall(blob))
    candidates -= _NON_TICKER_ALLCAPS
    candidates -= universe
    candidates.discard(str(data.get("ticker", "")).upper())
    suspect = {
        c for c in candidates if re.fullmatch(r"[A-Z][A-Z0-9&]{3,15}", c)
    }
    if suspect:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"hallucinated_ticker_candidates: {sorted(suspect)}",
        }

    return {"score": 1.0, "pass": True, "notes": "ok"}
