import pytest
from pipeline.research.phase_c_backtest import cost_model


def test_round_trip_cost_long_50000_default_slippage():
    """₹50,000 long round-trip at default 5 bps slippage.

    Actual breakdown (April 2026 Zerodha rates):
      Fixed costs: brokerage×2 + STT(sell) + exchange txn×2 + SEBI×2 + GST×2 + stamp(buy)
                   ≈ 10.7 bps on ₹50k = ₹53.57
      Slippage (5 bps round-trip): ₹25.00
      Total ≈ ₹78.57 (~15.7 bps)
    """
    cost = cost_model.round_trip_cost_inr(notional_inr=50000, side="LONG", slippage_bps=5.0)
    assert 70 <= cost <= 90, f"expected 70-90 INR, got {cost}"


def test_round_trip_cost_scales_linearly_with_notional():
    """Linearity holds when both notionals are below the brokerage cap crossover (₹66,667)."""
    a = cost_model.round_trip_cost_inr(notional_inr=20000, side="LONG", slippage_bps=5.0)
    b = cost_model.round_trip_cost_inr(notional_inr=40000, side="LONG", slippage_bps=5.0)
    assert abs(b / a - 2.0) < 0.01  # perfectly linear below brokerage cap


def test_higher_slippage_costs_more():
    base = cost_model.round_trip_cost_inr(notional_inr=50000, side="LONG", slippage_bps=5.0)
    stressed = cost_model.round_trip_cost_inr(notional_inr=50000, side="LONG", slippage_bps=20.0)
    assert stressed > base
    # 15 bps extra slippage round-trip on 50000 = 75 INR
    assert (stressed - base) == pytest.approx(75, abs=1)


def test_short_side_includes_buy_stamp_duty():
    """SHORT round-trip = sell first then buy. Buy leg has stamp duty."""
    cost_long = cost_model.round_trip_cost_inr(notional_inr=50000, side="LONG", slippage_bps=5.0)
    cost_short = cost_model.round_trip_cost_inr(notional_inr=50000, side="SHORT", slippage_bps=5.0)
    # Both round trips include one buy and one sell leg → costs should be equal
    assert cost_long == pytest.approx(cost_short, abs=0.01)


def test_apply_to_pnl_subtracts_cost():
    pnl_gross = 500.0
    pnl_net = cost_model.apply_to_pnl(pnl_gross_inr=500, notional_inr=50000, side="LONG", slippage_bps=5.0)
    expected = pnl_gross - cost_model.round_trip_cost_inr(50000, "LONG", 5.0)
    assert pnl_net == pytest.approx(expected, abs=0.01)
