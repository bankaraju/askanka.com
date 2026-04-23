import pandas as pd
import pytest

from pipeline.autoresearch.overshoot_compliance import slippage_grid as SG


def test_grid_levels_are_named():
    assert SG.LEVELS["S0"] == 0.10
    assert SG.LEVELS["S1"] == 0.30
    assert SG.LEVELS["S2"] == 0.50
    assert SG.LEVELS["S3"] == 0.70


def test_apply_level_subtracts_cost():
    ledger = pd.DataFrame([
        {"ticker": "A", "direction": "UP", "trade_ret_pct": 1.00},
        {"ticker": "A", "direction": "UP", "trade_ret_pct": -0.40},
    ])
    out = SG.apply_level(ledger, "S1")
    assert out["net_ret_pct"].iloc[0] == pytest.approx(0.70)
    assert out["net_ret_pct"].iloc[1] == pytest.approx(-0.70)
    assert (out["slippage_level"] == "S1").all()


def test_apply_full_grid_returns_four_rows_per_event():
    ledger = pd.DataFrame([
        {"ticker": "A", "direction": "UP", "trade_ret_pct": 1.00},
    ])
    out = SG.apply_full_grid(ledger)
    assert set(out["slippage_level"]) == {"S0", "S1", "S2", "S3"}
    assert len(out) == 4
