"""Tests universe.py — V1 universe loaders and the options-liquidity gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.research.intraday_v1 import universe


def test_load_stocks_universe_returns_nifty50():
    stocks = universe.load_stocks_universe()
    assert isinstance(stocks, list)
    assert len(stocks) == 50
    assert "RELIANCE" in stocks
    assert "HDFCBANK" in stocks
    assert all(isinstance(s, str) and s == s.upper() for s in stocks)


def test_options_liquidity_gate_admits_high_liquidity():
    snapshot = {
        "atm_call_volume_median_20d": 50_000,
        "atm_put_volume_median_20d": 60_000,
        "near_month_total_oi": 500_000,
        "atm_bid_ask_spread_pct_median": 0.5,
        "active_strikes_count": 12,
    }
    assert universe.passes_options_liquidity_gate(snapshot) is True


def test_options_liquidity_gate_rejects_thin_volume():
    snapshot = {
        "atm_call_volume_median_20d": 1_000,
        "atm_put_volume_median_20d": 1_500,
        "near_month_total_oi": 500_000,
        "atm_bid_ask_spread_pct_median": 0.5,
        "active_strikes_count": 12,
    }
    assert universe.passes_options_liquidity_gate(snapshot) is False


def test_options_liquidity_gate_rejects_thin_oi():
    snapshot = {
        "atm_call_volume_median_20d": 50_000,
        "atm_put_volume_median_20d": 60_000,
        "near_month_total_oi": 10_000,
        "atm_bid_ask_spread_pct_median": 0.5,
        "active_strikes_count": 12,
    }
    assert universe.passes_options_liquidity_gate(snapshot) is False


def test_options_liquidity_gate_rejects_wide_spread():
    snapshot = {
        "atm_call_volume_median_20d": 50_000,
        "atm_put_volume_median_20d": 60_000,
        "near_month_total_oi": 500_000,
        "atm_bid_ask_spread_pct_median": 3.0,
        "active_strikes_count": 12,
    }
    assert universe.passes_options_liquidity_gate(snapshot) is False


def test_load_v1_universe_returns_combined_pools(tmp_path, monkeypatch):
    # Set up minimal fake OI snapshot dir so the gate has something to read
    oi_dir = tmp_path / "oi"
    oi_dir.mkdir()
    monkeypatch.setattr(universe, "OI_SNAPSHOT_DIR", oi_dir)

    out = universe.load_v1_universe()
    assert "stocks" in out
    assert "indices" in out
    assert "frozen_at" in out  # ISO timestamp
    assert isinstance(out["stocks"], list)
    assert len(out["stocks"]) == 50
    assert isinstance(out["indices"], list)
    # Indices may be empty if no OI snapshots; gate must run without erroring
    for ix in out["indices"]:
        assert ix in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
                      "NIFTYNXT50", "NIFTYIT", "NIFTYAUTO", "NIFTYPHARMA",
                      "NIFTYFMCG", "NIFTYBANK", "NIFTYMETAL", "NIFTYENERGY",
                      "NIFTYREALTY", "NIFTYMEDIA", "NIFTYPSUBANK"}


def test_options_snapshot_aggregates_recent_files(tmp_path, monkeypatch):
    """The 20-day rolling aggregation reads `*_near_chain.json` files,
    medians the per-day fields, and feeds the gate. This is the live
    kickoff path — the empty-directory branch is exercised elsewhere."""
    monkeypatch.setattr(universe, "OI_SNAPSHOT_DIR", tmp_path)
    sym_dir = tmp_path / "NIFTY"
    sym_dir.mkdir()

    # Two conformant daily snapshots
    (sym_dir / "20260427_near_chain.json").write_text(json.dumps({
        "atm_call_volume": 30_000,
        "atm_put_volume": 40_000,
        "total_oi": 600_000,
        "atm_bid_ask_spread_pct": 0.4,
        "active_strikes_count": 11,
    }), encoding="utf-8")
    (sym_dir / "20260428_near_chain.json").write_text(json.dumps({
        "atm_call_volume": 50_000,
        "atm_put_volume": 60_000,
        "total_oi": 700_000,
        "atm_bid_ask_spread_pct": 0.6,
        "active_strikes_count": 13,
    }), encoding="utf-8")

    snap = universe._build_options_snapshot("NIFTY")
    # Medians of the 2-file aggregation
    assert snap["atm_call_volume_median_20d"] == 40_000   # median(30k, 50k)
    assert snap["atm_put_volume_median_20d"] == 50_000    # median(40k, 60k)
    assert snap["near_month_total_oi"] == 650_000         # median(600k, 700k)
    assert abs(snap["atm_bid_ask_spread_pct_median"] - 0.5) < 1e-9  # median(0.4, 0.6)
    assert snap["active_strikes_count"] == 12             # int(median(11, 13))

    # And it clears the gate
    assert universe.passes_options_liquidity_gate(snap) is True
