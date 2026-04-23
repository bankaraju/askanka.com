"""Tests for the EOD directional-edge simulator.

Validates the 4-year in-sample directional simulator: enter at next bar's
open, exit at next bar's close, side from sign(expected_return), apply
round-trip cost model.
"""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import simulator_eod


@pytest.fixture
def fake_universe_bars():
    # 10 business days ending 2026-04-17 (Fri) → 2026-04-06 .. 2026-04-17
    dates = pd.bdate_range(end="2026-04-19", periods=10)
    a = pd.DataFrame({
        "date": dates,
        "open":  [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
        "close": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
        "high":  [101.5] * 10,
        "low":   [99.5] * 10,
        "volume": [10000] * 10,
    })
    return {"A": a}


def test_run_simulation_emits_ledger_for_opportunity_only(fake_universe_bars):
    classifications = pd.DataFrame([
        {"date": "2026-04-15", "symbol": "A", "label": "OPPORTUNITY_LAG", "action": "ADD",
         "z_score": 2.0, "expected_return": 0.01},
        {"date": "2026-04-15", "symbol": "A", "label": "UNCERTAIN", "action": "HOLD",
         "z_score": 0.5, "expected_return": 0.01},
    ])
    ledger = simulator_eod.run_simulation(
        classifications=classifications,
        symbol_bars=fake_universe_bars,
        notional_inr=50000,
        slippage_bps=5.0,
    )
    # Only the OPPORTUNITY_LAG row emits a trade
    assert len(ledger) == 1
    assert ledger.iloc[0]["label"] == "OPPORTUNITY_LAG"
    assert "pnl_gross_inr" in ledger.columns
    assert "pnl_net_inr" in ledger.columns
    assert "side" in ledger.columns


def test_run_simulation_top_n_caps_concurrent_positions(fake_universe_bars):
    # Build 10 candidates same date; cap at top-3 by abs(z_score)
    classifications = pd.DataFrame([
        {"date": "2026-04-15", "symbol": "A", "label": "OPPORTUNITY_LAG", "action": "ADD",
         "z_score": float(z), "expected_return": 0.01}
        for z in range(1, 11)
    ])
    # Differentiate symbols so each is a distinct trade
    for i in range(10):
        classifications.loc[i, "symbol"] = f"S{i}"
    bars = {f"S{i}": fake_universe_bars["A"] for i in range(10)}
    ledger = simulator_eod.run_simulation(
        classifications=classifications,
        symbol_bars=bars,
        notional_inr=50000,
        slippage_bps=5.0,
        top_n=3,
    )
    assert len(ledger) == 3


def test_run_simulation_long_negative_pnl_when_price_falls():
    # 3 business days: 2026-04-15 (Wed), 2026-04-16 (Thu), 2026-04-17 (Fri)
    bars_down = pd.DataFrame({
        "date": pd.bdate_range(end="2026-04-19", periods=3),
        "open":  [100, 100, 95],
        "close": [100, 95, 90],
        "high":  [100.5] * 3,
        "low":   [89.5] * 3,
        "volume": [10000] * 3,
    })
    # Classify on Apr 15 → next bar is Apr 16 (open=100, close=95)
    classifications = pd.DataFrame([
        {"date": "2026-04-15", "symbol": "X", "label": "OPPORTUNITY_LAG", "action": "ADD",
         "z_score": 2.0, "expected_return": 0.01},
    ])
    ledger = simulator_eod.run_simulation(
        classifications=classifications,
        symbol_bars={"X": bars_down},
        notional_inr=50000,
        slippage_bps=5.0,
    )
    # LONG signal (expected_return > 0) entered open of 2026-04-16 at 100, closes at 95 → loss
    assert ledger.iloc[0]["side"] == "LONG"
    assert ledger.iloc[0]["pnl_gross_inr"] < 0
    assert ledger.iloc[0]["pnl_net_inr"] < ledger.iloc[0]["pnl_gross_inr"]  # cost makes it worse
