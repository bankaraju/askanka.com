"""Tests for pipeline.research.h_2026_04_27_secrsi.sector_snapshot.

Spec: docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md §3.1
"""
from __future__ import annotations

import math

import pytest

from pipeline.research.h_2026_04_27_secrsi.sector_snapshot import take_snapshot


def test_basic_three_sector_aggregation():
    prices_open = {
        "STOCKA1": 100.0, "STOCKA2": 200.0, "STOCKA3": 300.0, "STOCKA4": 400.0,
        "STOCKB1": 100.0, "STOCKB2": 200.0, "STOCKB3": 300.0, "STOCKB4": 400.0,
        "STOCKC1": 100.0, "STOCKC2": 200.0, "STOCKC3": 300.0, "STOCKC4": 400.0,
    }
    prices_now = {
        "STOCKA1": 102.0, "STOCKA2": 204.0, "STOCKA3": 306.0, "STOCKA4": 408.0,  # +2%
        "STOCKB1": 100.0, "STOCKB2": 200.0, "STOCKB3": 300.0, "STOCKB4": 400.0,  # 0%
        "STOCKC1": 99.0,  "STOCKC2": 198.0, "STOCKC3": 297.0, "STOCKC4": 396.0,  # -1%
    }
    sector_map = {
        "STOCKA1": "SECTORA", "STOCKA2": "SECTORA", "STOCKA3": "SECTORA", "STOCKA4": "SECTORA",
        "STOCKB1": "SECTORB", "STOCKB2": "SECTORB", "STOCKB3": "SECTORB", "STOCKB4": "SECTORB",
        "STOCKC1": "SECTORC", "STOCKC2": "SECTORC", "STOCKC3": "SECTORC", "STOCKC4": "SECTORC",
    }

    snap = take_snapshot(prices_open, prices_now, sector_map, min_stocks_per_sector=4)

    by_sector = {row["sector"]: row for row in snap}
    assert math.isclose(by_sector["SECTORA"]["sector_score"], 0.02, abs_tol=1e-9)
    assert math.isclose(by_sector["SECTORB"]["sector_score"], 0.00, abs_tol=1e-9)
    assert math.isclose(by_sector["SECTORC"]["sector_score"], -0.01, abs_tol=1e-9)
    assert all(row["qualified"] is True for row in snap)
    assert all(row["n_stocks"] == 4 for row in snap)


def test_sector_below_min_stocks_disqualified():
    prices_open = {"STOCKA1": 100.0, "STOCKA2": 200.0, "STOCKA3": 300.0}
    prices_now = {"STOCKA1": 110.0, "STOCKA2": 220.0, "STOCKA3": 330.0}
    sector_map = {"STOCKA1": "SMALLSECTOR", "STOCKA2": "SMALLSECTOR", "STOCKA3": "SMALLSECTOR"}

    snap = take_snapshot(prices_open, prices_now, sector_map, min_stocks_per_sector=4)

    assert len(snap) == 1
    assert snap[0]["sector"] == "SMALLSECTOR"
    assert snap[0]["qualified"] is False
    assert snap[0]["n_stocks"] == 3


def test_median_robust_to_runaway():
    """Spec §3.1: use median, not mean — one runaway stock should not skew the sector."""
    prices_open = {"S1": 100.0, "S2": 100.0, "S3": 100.0, "S4": 100.0}
    prices_now = {"S1": 100.0, "S2": 100.0, "S3": 100.0, "S4": 200.0}  # one stock +100%
    sector_map = {"S1": "X", "S2": "X", "S3": "X", "S4": "X"}

    snap = take_snapshot(prices_open, prices_now, sector_map, min_stocks_per_sector=4)
    assert len(snap) == 1
    assert math.isclose(snap[0]["sector_score"], 0.0, abs_tol=1e-9)


def test_missing_stock_in_now_dropped():
    prices_open = {"S1": 100.0, "S2": 100.0, "S3": 100.0, "S4": 100.0}
    prices_now = {"S1": 105.0, "S2": 105.0, "S3": 105.0}  # S4 missing
    sector_map = {"S1": "X", "S2": "X", "S3": "X", "S4": "X"}

    snap = take_snapshot(prices_open, prices_now, sector_map, min_stocks_per_sector=4)

    assert snap[0]["sector"] == "X"
    assert snap[0]["n_stocks"] == 3
    assert snap[0]["qualified"] is False


def test_unmapped_stocks_excluded_from_sectors():
    prices_open = {"S1": 100.0, "S2": 100.0, "S3": 100.0, "S4": 100.0, "S5": 100.0}
    prices_now = {"S1": 110.0, "S2": 110.0, "S3": 110.0, "S4": 110.0, "S5": 110.0}
    sector_map = {"S1": "X", "S2": "X", "S3": "X", "S4": "X"}  # S5 unmapped

    snap = take_snapshot(prices_open, prices_now, sector_map, min_stocks_per_sector=4)

    assert {r["sector"] for r in snap} == {"X"}
    assert snap[0]["n_stocks"] == 4
