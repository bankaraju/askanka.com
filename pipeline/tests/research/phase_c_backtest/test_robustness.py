"""Tests for pipeline.research.phase_c_backtest.robustness."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import robustness


@pytest.fixture
def sample_ledger():
    return pd.DataFrame([
        {"entry_date": "2026-04-15", "exit_date": "2026-04-16", "symbol": f"S{i}",
         "side": "LONG", "notional_inr": 50000, "pnl_gross_inr": 100.0,
         "pnl_net_inr": 50.0, "z_score": float(i + 1), "label": "OPPORTUNITY"}
        for i in range(10)
    ])


def test_slippage_sweep_returns_one_row_per_bps(sample_ledger):
    out = robustness.slippage_sweep(sample_ledger, bps_grid=[5, 10, 20])
    assert len(out) == 3
    assert set(out["slippage_bps"]) == {5, 10, 20}
    # Higher slippage -> lower net P&L
    sorted_out = out.sort_values("slippage_bps")
    assert sorted_out["total_net_pnl_inr"].is_monotonic_decreasing


def test_top_n_sweep_caps_concurrent(sample_ledger):
    out = robustness.top_n_sweep(sample_ledger, n_grid=[3, 5, 10])
    assert len(out) == 3
    # n=3 -> smaller dataset
    n3 = out[out["top_n"] == 3].iloc[0]
    n10 = out[out["top_n"] == 10].iloc[0]
    assert n3["n_trades"] <= n10["n_trades"]
