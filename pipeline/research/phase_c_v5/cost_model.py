"""V5 cost model — dispatches on instrument type.

Per-instrument rate table from the V5 spec. Slippage is applied round-trip.
Fixed costs (brokerage, STT, stamp, GST, exchange txn, SEBI) reuse V4's
``_leg_cost_inr`` helper with per-instrument STT/stamp overrides.
"""
from __future__ import annotations

from pipeline.research.phase_c_backtest import cost_model as v4cm

_INSTRUMENT_PARAMS: dict[str, dict] = {
    "stock_future": {
        "slippage_bps": 5.0, "stt_sell_rate": 0.000125, "stamp_buy_rate": 0.00002,
    },
    "nifty_future": {
        "slippage_bps": 2.0, "stt_sell_rate": 0.000125, "stamp_buy_rate": 0.00002,
    },
    "sectoral_index_future": {
        "slippage_bps": 8.0, "stt_sell_rate": 0.000125, "stamp_buy_rate": 0.00002,
    },
    "option": {
        "slippage_bps": 15.0, "stt_sell_rate": 0.000625, "stamp_buy_rate": 0.00003,
    },
}


def _leg_cost(notional_inr: float, leg: str, stt_sell_rate: float,
              stamp_buy_rate: float) -> float:
    brokerage = min(notional_inr * v4cm.BROKERAGE_RATE, v4cm.BROKERAGE_CAP_INR)
    txn = notional_inr * v4cm.EXCHANGE_TXN_RATE
    sebi = notional_inr * v4cm.SEBI_RATE
    gst = (brokerage + txn) * v4cm.GST_RATE
    stt = notional_inr * stt_sell_rate if leg == "SELL" else 0.0
    stamp = notional_inr * stamp_buy_rate if leg == "BUY" else 0.0
    return brokerage + txn + sebi + gst + stt + stamp


def round_trip_cost(instrument: str, notional_inr: float, side: str) -> float:
    if instrument not in _INSTRUMENT_PARAMS:
        raise ValueError(
            f"instrument must be one of {list(_INSTRUMENT_PARAMS)}, got {instrument!r}")
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    p = _INSTRUMENT_PARAMS[instrument]
    fixed = (_leg_cost(notional_inr, "BUY", p["stt_sell_rate"], p["stamp_buy_rate"]) +
             _leg_cost(notional_inr, "SELL", p["stt_sell_rate"], p["stamp_buy_rate"]))
    slip = notional_inr * (p["slippage_bps"] / 10_000.0)
    return fixed + slip


def apply_to_pnl(pnl_gross_inr: float, instrument: str,
                 notional_inr: float, side: str) -> float:
    return pnl_gross_inr - round_trip_cost(instrument, notional_inr, side)
