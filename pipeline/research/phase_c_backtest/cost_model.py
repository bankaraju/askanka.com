"""Zerodha retail equity-intraday cost model.

Round-trip = one BUY leg + one SELL leg. Fixed costs are computed per leg
then summed. Slippage is applied as parametric basis-points round-trip.
"""
from __future__ import annotations

# Zerodha equity intraday rates (April 2026)
BROKERAGE_RATE = 0.0003  # 0.03%
BROKERAGE_CAP_INR = 20.0
STT_SELL_RATE = 0.00025  # 0.025% on sell side only
EXCHANGE_TXN_RATE = 0.0000345  # NSE 0.00345%
SEBI_RATE = 0.000001  # 0.0001%
GST_RATE = 0.18
STAMP_DUTY_BUY_RATE = 0.00003  # 0.003% on buy side only


def _leg_cost_inr(notional_inr: float, leg: str) -> float:
    """Cost of a single leg ('BUY' or 'SELL'). Returns INR."""
    brokerage = min(notional_inr * BROKERAGE_RATE, BROKERAGE_CAP_INR)
    txn = notional_inr * EXCHANGE_TXN_RATE
    sebi = notional_inr * SEBI_RATE
    gst = (brokerage + txn) * GST_RATE
    stt = notional_inr * STT_SELL_RATE if leg == "SELL" else 0.0
    stamp = notional_inr * STAMP_DUTY_BUY_RATE if leg == "BUY" else 0.0
    return brokerage + txn + sebi + gst + stt + stamp


def round_trip_cost_inr(notional_inr: float, side: str, slippage_bps: float = 5.0) -> float:
    """Total cost in INR for a round-trip (buy + sell, regardless of order).

    Args:
        notional_inr: Position notional in INR.
        side: "LONG" (buy first) or "SHORT" (sell first). Total cost is identical
              because both involve one BUY + one SELL leg.
        slippage_bps: Slippage applied round-trip in basis points.

    Returns:
        Total round-trip cost in INR.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    # side is validated above but does not change the result: both LONG and SHORT
    # round trips include exactly one BUY leg and one SELL leg.
    fixed = _leg_cost_inr(notional_inr, "BUY") + _leg_cost_inr(notional_inr, "SELL")
    slippage = notional_inr * (slippage_bps / 10_000.0)
    return fixed + slippage


def apply_to_pnl(pnl_gross_inr: float, notional_inr: float, side: str, slippage_bps: float = 5.0) -> float:
    """Subtract round-trip cost from gross P&L."""
    return pnl_gross_inr - round_trip_cost_inr(notional_inr, side, slippage_bps)
