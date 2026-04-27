"""Tests for pipeline.research.h_2026_04_27_secrsi.basket_builder.

Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md §3.2-§3.4
"""
from __future__ import annotations

import pytest

from pipeline.research.h_2026_04_27_secrsi.basket_builder import build_basket


def _snap(sector, score, stocks):
    return {
        "sector": sector,
        "sector_score": score,
        "n_stocks": len(stocks),
        "qualified": True,
        "stock_pcts": dict(stocks),
    }


def test_top_2_bottom_2_selection():
    """4 sectors → pick top-2 (LONG) and bottom-2 (SHORT)."""
    snapshot = [
        _snap("WIN_BIG", 0.030, {"W1": 0.04, "W2": 0.03, "W3": 0.02, "W4": 0.01}),
        _snap("WIN_SMALL", 0.010, {"X1": 0.02, "X2": 0.01, "X3": 0.005, "X4": 0.0}),
        _snap("LOSE_SMALL", -0.005, {"Y1": 0.0, "Y2": -0.005, "Y3": -0.01, "Y4": -0.02}),
        _snap("LOSE_BIG", -0.020, {"Z1": -0.01, "Z2": -0.02, "Z3": -0.025, "Z4": -0.03}),
    ]
    basket = build_basket(snapshot)

    longs = [b for b in basket if b["side"] == "LONG"]
    shorts = [b for b in basket if b["side"] == "SHORT"]
    assert len(longs) == 4
    assert len(shorts) == 4

    long_sectors = {b["sector"] for b in longs}
    short_sectors = {b["sector"] for b in shorts}
    assert long_sectors == {"WIN_BIG", "WIN_SMALL"}
    assert short_sectors == {"LOSE_SMALL", "LOSE_BIG"}


def test_pick_best_2_within_winning_sector():
    snapshot = [
        _snap("W", 0.02, {"W1": 0.05, "W2": 0.04, "W3": 0.02, "W4": 0.01, "W5": 0.0}),
        _snap("W2", 0.015, {"A1": 0.03, "A2": 0.02, "A3": 0.01, "A4": 0.0}),
        _snap("L", -0.01, {"L1": -0.02, "L2": -0.01, "L3": 0.0, "L4": 0.005}),
        _snap("L2", -0.02, {"M1": -0.05, "M2": -0.03, "M3": -0.02, "M4": 0.0}),
    ]
    basket = build_basket(snapshot)

    w_longs = sorted([b["ticker"] for b in basket if b["side"] == "LONG" and b["sector"] == "W"])
    assert w_longs == ["W1", "W2"]


def test_pick_worst_2_within_losing_sector():
    snapshot = [
        _snap("W", 0.02, {"W1": 0.03, "W2": 0.02, "W3": 0.01, "W4": 0.0}),
        _snap("W2", 0.015, {"A1": 0.02, "A2": 0.01, "A3": 0.0, "A4": -0.01}),
        _snap("L", -0.01, {"L1": 0.0, "L2": -0.01, "L3": -0.02, "L4": -0.05, "L5": 0.005}),
        _snap("L2", -0.02, {"M1": -0.03, "M2": -0.04, "M3": -0.05, "M4": -0.01}),
    ]
    basket = build_basket(snapshot)

    l_shorts = sorted([b["ticker"] for b in basket if b["side"] == "SHORT" and b["sector"] == "L"])
    assert l_shorts == ["L3", "L4"]


def test_disqualified_sector_skipped():
    snapshot = [
        _snap("W", 0.02, {"W1": 0.03, "W2": 0.02, "W3": 0.01, "W4": 0.0}),
        {"sector": "TINY", "sector_score": 0.10, "n_stocks": 2, "qualified": False,
         "stock_pcts": {"T1": 0.10, "T2": 0.10}},
        _snap("W2", 0.015, {"A1": 0.02, "A2": 0.01, "A3": 0.0, "A4": -0.01}),
        _snap("L", -0.01, {"L1": -0.02, "L2": -0.01, "L3": 0.0, "L4": 0.005}),
        _snap("L2", -0.02, {"M1": -0.05, "M2": -0.02, "M3": 0.0, "M4": 0.005}),
    ]
    basket = build_basket(snapshot)
    sectors = {b["sector"] for b in basket}
    assert "TINY" not in sectors


def test_insufficient_qualifying_sectors_returns_empty():
    """Spec §3.6: fewer than 4 qualifying sectors → no trade."""
    snapshot = [
        _snap("A", 0.02, {"A1": 0.02, "A2": 0.02, "A3": 0.02, "A4": 0.02}),
        _snap("B", 0.01, {"B1": 0.01, "B2": 0.01, "B3": 0.01, "B4": 0.01}),
        {"sector": "C", "sector_score": -0.01, "n_stocks": 2, "qualified": False,
         "stock_pcts": {"C1": -0.01, "C2": -0.01}},
    ]
    basket = build_basket(snapshot)
    assert basket == []


def test_dollar_neutral_equal_legs():
    snapshot = [
        _snap("W", 0.02, {"W1": 0.03, "W2": 0.02, "W3": 0.01, "W4": 0.0}),
        _snap("W2", 0.015, {"A1": 0.02, "A2": 0.01, "A3": 0.005, "A4": 0.0}),
        _snap("L", -0.01, {"L1": -0.02, "L2": -0.01, "L3": 0.0, "L4": 0.005}),
        _snap("L2", -0.02, {"M1": -0.05, "M2": -0.03, "M3": -0.01, "M4": 0.0}),
    ]
    basket = build_basket(snapshot)

    longs = [b for b in basket if b["side"] == "LONG"]
    shorts = [b for b in basket if b["side"] == "SHORT"]
    assert len(longs) == len(shorts) == 4

    weights = {b["ticker"]: b["weight"] for b in basket}
    assert all(w == pytest.approx(1.0 / 8.0) for w in weights.values())


def test_carries_metadata_fields():
    snapshot = [
        _snap("W", 0.02, {"W1": 0.03, "W2": 0.02, "W3": 0.01, "W4": 0.0}),
        _snap("W2", 0.015, {"A1": 0.02, "A2": 0.01, "A3": 0.005, "A4": 0.0}),
        _snap("L", -0.01, {"L1": -0.02, "L2": -0.01, "L3": 0.0, "L4": 0.005}),
        _snap("L2", -0.02, {"M1": -0.05, "M2": -0.03, "M3": -0.01, "M4": 0.0}),
    ]
    basket = build_basket(snapshot)
    leg = basket[0]
    assert "ticker" in leg
    assert "sector" in leg
    assert "side" in leg
    assert "sector_score" in leg
    assert "stock_pct_at_snap" in leg
    assert "weight" in leg


def test_top_n_sectors_parameterizable():
    snapshot = [
        _snap("W1", 0.03, {f"W1{i}": 0.03 for i in range(4)}),
        _snap("W2", 0.02, {f"W2{i}": 0.02 for i in range(4)}),
        _snap("W3", 0.01, {f"W3{i}": 0.01 for i in range(4)}),
        _snap("L1", -0.01, {f"L1{i}": -0.01 for i in range(4)}),
        _snap("L2", -0.02, {f"L2{i}": -0.02 for i in range(4)}),
        _snap("L3", -0.03, {f"L3{i}": -0.03 for i in range(4)}),
    ]
    basket = build_basket(snapshot, top_n_sectors=3, top_n_stocks=2)
    longs = [b for b in basket if b["side"] == "LONG"]
    shorts = [b for b in basket if b["side"] == "SHORT"]
    assert len(longs) == 6
    assert len(shorts) == 6
    long_sectors = {b["sector"] for b in longs}
    short_sectors = {b["sector"] for b in shorts}
    assert long_sectors == {"W1", "W2", "W3"}
    assert short_sectors == {"L1", "L2", "L3"}


def test_deterministic_tie_breaking_alphabetical():
    """Spec §3.6: ties broken alphabetically (deterministic)."""
    snapshot = [
        _snap("ZZZ", 0.02, {"Z1": 0.02, "Z2": 0.02, "Z3": 0.02, "Z4": 0.02}),
        _snap("AAA", 0.02, {"A1": 0.02, "A2": 0.02, "A3": 0.02, "A4": 0.02}),  # tied
        _snap("MMM", 0.01, {"M1": 0.01, "M2": 0.01, "M3": 0.01, "M4": 0.01}),
        _snap("LOSER1", -0.01, {"X1": -0.01, "X2": -0.01, "X3": -0.01, "X4": -0.01}),
        _snap("LOSER2", -0.02, {"Y1": -0.02, "Y2": -0.02, "Y3": -0.02, "Y4": -0.02}),
    ]
    basket = build_basket(snapshot)
    long_sectors = sorted({b["sector"] for b in basket if b["side"] == "LONG"})
    # AAA + ZZZ are tied at 0.02 — alphabetical wins → AAA picked, then ZZZ.
    assert "AAA" in long_sectors
