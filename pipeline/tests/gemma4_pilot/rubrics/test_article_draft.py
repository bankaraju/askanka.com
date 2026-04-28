"""Tests for the article-draft rubric.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 10)
"""
from __future__ import annotations

from pipeline.gemma4_pilot.rubrics.article_draft import score


META = {
    "global_regime": {
        "brent_usd": 92.4,
        "wti_usd": 88.1,
        "usd_inr": 84.05,
        "us10y_pct": 4.32,
    },
    "universe": {"RELIANCE", "ONGC", "TCS", "INFY", "HDFCBANK"},
}


def _filler(words: int) -> str:
    return ("the market remained constructive into the close. " * (words // 7))


def test_pass_well_grounded_long_article():
    body = (
        "Brent crude held near $92 a barrel and the rupee at 84.1 to the "
        "dollar today. Reliance led the energy complex while ONGC trailed "
        "marginally. " + _filler(900)
    )
    r = score(body, META)
    assert r["pass"] is True, r["notes"]


def test_fail_too_short():
    r = score("short article.", META)
    assert r["pass"] is False
    assert "length" in r["notes"]


def test_fail_wrong_oil_price():
    body = (
        "Brent crude printed $103 a barrel — well above last week's range. "
        "Reliance led the rally. " + _filler(900)
    )
    r = score(body, META)
    assert r["pass"] is False
    assert "stale" in r["notes"].lower() or "number" in r["notes"].lower()


def test_fail_hallucinated_ticker():
    body = (
        "Brent at $92 a barrel, USDINR at 84.1. Reliance and TICKERX led "
        "the rally. " + _filler(900)
    )
    r = score(body, META)
    assert r["pass"] is False
    assert "halluc" in r["notes"].lower() or "ticker" in r["notes"].lower()
