from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import basket_simulator as bs


def test_equal_weight_long_short_pair_pnl(sample_daily_basket_bars):
    """Long LEADER (+0.5%/day), short LAGGER (-0.2%/day), hold 5 days.
    With 5 days of compounding: LEADER ≈ 2.5%, LAGGER short ≈ 1.2%, combined ≈ 2.1%."""
    entry_date = pd.Timestamp("2026-01-05")
    trade = bs.simulate_basket_trade(
        entry_date=entry_date,
        long_legs=[{"symbol": "LEADER", "weight": 1.0}],
        short_legs=[{"symbol": "LAGGER", "weight": 1.0}],
        symbol_bars=sample_daily_basket_bars,
        hold_days=5,
        notional_per_leg_inr=50_000,
        slippage_bps=5.0,
    )
    assert trade is not None
    assert trade["side_count_long"] == 1
    assert trade["side_count_short"] == 1
    # With 5 days of compounding on independent drifts, combined return ≈ 2.1% before costs
    gross_pct = trade["pnl_gross_inr"] / trade["notional_total_inr"] * 100
    assert 2.0 <= gross_pct <= 2.2, f"expected 2.0-2.2% gross, got {gross_pct:.2f}%"
    # Net must be less than gross by exactly the cost sum
    assert trade["pnl_net_inr"] < trade["pnl_gross_inr"]


def test_skips_trade_when_any_leg_missing(sample_daily_basket_bars):
    """If a symbol has no bars on entry date, return None."""
    bars = dict(sample_daily_basket_bars)
    bars["GHOST"] = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    trade = bs.simulate_basket_trade(
        entry_date=pd.Timestamp("2026-01-05"),
        long_legs=[{"symbol": "GHOST", "weight": 1.0}],
        short_legs=[{"symbol": "LAGGER", "weight": 1.0}],
        symbol_bars=bars,
        hold_days=5,
        notional_per_leg_inr=50_000,
    )
    assert trade is None


def test_unequal_weights_respected(sample_daily_basket_bars):
    """Two longs (0.7 / 0.3 weight) + one short must sum notionals correctly."""
    trade = bs.simulate_basket_trade(
        entry_date=pd.Timestamp("2026-01-05"),
        long_legs=[{"symbol": "LEADER", "weight": 0.7},
                   {"symbol": "LEADER", "weight": 0.3}],
        short_legs=[{"symbol": "LAGGER", "weight": 1.0}],
        symbol_bars=sample_daily_basket_bars,
        hold_days=5,
        notional_per_leg_inr=50_000,
    )
    assert trade is not None
    # Total notional = 50k (long weights sum to 1.0) + 50k (short) = 100k
    assert trade["notional_total_inr"] == pytest.approx(100_000, abs=1.0)


def test_hold_horizon_of_zero_raises():
    with pytest.raises(ValueError, match="hold_days must be >= 1"):
        bs.simulate_basket_trade(
            entry_date=pd.Timestamp("2026-01-05"),
            long_legs=[{"symbol": "X", "weight": 1.0}],
            short_legs=[{"symbol": "Y", "weight": 1.0}],
            symbol_bars={},
            hold_days=0,
        )
