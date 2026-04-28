"""Rubric for Task #4 -- daily article draft (markets only).

Pass criteria from spec §3.1 + memory feedback_stale_data_disqualifies_article.md:
  1. Length 800-2500 words.
  2. Any cited macro anchor (Brent, WTI, USDINR, US10Y) within tolerance
     of meta['global_regime']. Stale-or-wrong number = hard fail.
  3. No hallucinated tickers (capitalised 4-16-letter alpha tokens not
     in the universe and not in the non-ticker allowlist).

The rubric does NOT score prose quality -- that's the human pairwise
audit's job.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 10)
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_MIN_WORDS = 800
_MAX_WORDS = 2500

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&]{3,15}\b")
_NON_TICKER = {
    "USDINR", "EURUSD", "USDJPY", "BRENT", "WTI", "OPEC", "FII", "DII",
    "NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY", "MIDCAP", "SMALLCAP",
    "GAAP", "EBITDA", "ARPU", "RBI", "SEBI", "GST", "FY", "AGM", "CEO",
    "CFO", "USD", "INR", "EUR", "JPY", "GBP", "CNY", "BULLISH", "BEARISH",
    "NEUTRAL", "RISK",
}

_BRENT_RE = re.compile(
    r"brent[^\d$]{0,20}\$?\s*([0-9]{2,3}(?:\.[0-9])?)", re.I
)
_WTI_RE = re.compile(
    r"wti[^\d$]{0,20}\$?\s*([0-9]{2,3}(?:\.[0-9])?)", re.I
)
_USDINR_RE = re.compile(
    r"(?:rupee|usdinr|inr)[^\d]{0,20}([0-9]{2,3}\.[0-9])", re.I
)
_US10Y_RE = re.compile(
    r"(?:us\s*10\s*y(?:ear)?|10[-\s]?yr|treasur(?:y|ies))"
    r"[^\d%]{0,20}([0-9]\.[0-9]{1,2})",
    re.I,
)

_ANCHOR_TOL = {
    "brent_usd": 1.5,
    "wti_usd": 1.5,
    "usd_inr": 0.3,
    "us10y_pct": 0.10,
}


def score(text: str, meta: Mapping[str, Any]) -> dict:
    word_count = len(text.split())
    if word_count < _MIN_WORDS or word_count > _MAX_WORDS:
        return {
            "score": 0.0,
            "pass": False,
            "notes": (
                f"length: {word_count} words not in "
                f"[{_MIN_WORDS}, {_MAX_WORDS}]"
            ),
        }

    regime = meta.get("global_regime", {}) or {}
    universe = {u.upper() for u in meta.get("universe", set())}

    # Number-grounding: each anchor we can extract must be within tolerance
    checks = [
        ("brent_usd", _BRENT_RE),
        ("wti_usd", _WTI_RE),
        ("usd_inr", _USDINR_RE),
        ("us10y_pct", _US10Y_RE),
    ]
    for key, regex in checks:
        m = regex.search(text)
        if m is None:
            continue
        try:
            cited = float(m.group(1))
        except ValueError:
            continue
        truth = regime.get(key)
        if truth is None:
            continue
        if abs(cited - float(truth)) > _ANCHOR_TOL[key]:
            return {
                "score": 0.0,
                "pass": False,
                "notes": (
                    f"stale_or_wrong_number: {key} cited={cited} "
                    f"truth={truth} tol={_ANCHOR_TOL[key]}"
                ),
            }

    # Hallucinated-ticker check: capitalised 4-16-letter tokens not in
    # the universe and not in the non-ticker allowlist.
    candidates = set(_TICKER_RE.findall(text))
    candidates -= _NON_TICKER
    candidates -= universe
    suspect = {c for c in candidates if 4 <= len(c) <= 16 and c.isalpha()}
    if suspect:
        return {
            "score": 0.0,
            "pass": False,
            "notes": f"hallucinated_ticker_candidates: {sorted(suspect)[:5]}",
        }

    return {"score": 1.0, "pass": True, "notes": "ok"}
