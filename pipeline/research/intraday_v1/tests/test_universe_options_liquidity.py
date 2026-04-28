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
