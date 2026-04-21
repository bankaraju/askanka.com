from __future__ import annotations
import pytest
from pipeline.research.phase_c_v5 import cost_model as cm


def test_nifty_futures_cost_lower_slippage_than_stock():
    """NIFTY futures slippage = 2 bps vs stock 5 bps → cost should be lower."""
    stock = cm.round_trip_cost("stock_future", notional_inr=500_000, side="LONG")
    nifty = cm.round_trip_cost("nifty_future", notional_inr=500_000, side="LONG")
    assert nifty < stock


def test_sectoral_index_higher_slippage_than_nifty():
    """Sectoral indices get 8 bps slippage vs 2 bps NIFTY."""
    sec = cm.round_trip_cost("sectoral_index_future", notional_inr=500_000, side="LONG")
    nifty = cm.round_trip_cost("nifty_future", notional_inr=500_000, side="LONG")
    assert sec > nifty


def test_options_round_trip_has_higher_stt_rate():
    """Options STT on sell is 0.0625% vs futures 0.0125%."""
    stock = cm.round_trip_cost("stock_future", notional_inr=50_000, side="LONG")
    opt = cm.round_trip_cost("option", notional_inr=50_000, side="LONG")
    assert opt > stock


def test_apply_to_pnl_uses_instrument_specific_cost():
    gross = 1000.0
    net_nifty = cm.apply_to_pnl(gross, "nifty_future", notional_inr=500_000, side="LONG")
    net_stock = cm.apply_to_pnl(gross, "stock_future", notional_inr=500_000, side="LONG")
    assert net_nifty > net_stock  # NIFTY cheaper → higher net


def test_invalid_instrument_raises():
    with pytest.raises(ValueError, match="instrument must be one of"):
        cm.round_trip_cost("bitcoin", notional_inr=50_000, side="LONG")
