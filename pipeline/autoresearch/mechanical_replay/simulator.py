"""Single-trade intraday minute-bar walker for the mechanical replay.

Mandate (per spec §5):
  - Entry at 09:30 IST (close of the 09:30 minute bar)
  - Hard close at 14:30 IST (TIME_STOP)
  - ATR-based stop (per-ticker, per-date, computed by atr.py)
  - Optional Z_CROSS exit at a provided timestamp (Phase C: when peer-relative
    z falls back to neutral and the symbol is no longer an actionable break)
  - Ratcheted trail: arms when peak ≥ TRAIL_ARM_PCT, exits when
    (peak − close) ≥ TRAIL_GIVEBACK_PCT
  - 20bps round-trip slippage (per backtesting-specs.txt §1)

Tie-break order on a single bar (most-conservative-first, mirrors live):
  ATR_STOP → Z_CROSS → TRAIL → continue

Returns one dict per trade. Caller (runner) is responsible for assembling
the trades CSV and per-engine attribution.
"""
from __future__ import annotations

from datetime import time
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.autoresearch.mechanical_replay import constants as C


def _signed_return(entry: float, exit_price: float, side: str) -> float:
    """Percent P&L of a side trade between entry and exit (no slippage)."""
    if entry <= 0:
        return 0.0
    raw_pct = 100.0 * (exit_price - entry) / entry
    return raw_pct if side == "LONG" else -raw_pct


def _bar_signed_extreme(entry: float, high: float, low: float, side: str) -> tuple[float, float]:
    """(intra_bar_min_pnl, intra_bar_max_pnl) signed for the side."""
    pnl_high = _signed_return(entry, high, side)
    pnl_low = _signed_return(entry, low, side)
    return min(pnl_high, pnl_low), max(pnl_high, pnl_low)


def simulate_one_trade(
    *,
    bars: pd.DataFrame,
    side: str,
    stop_pct: float,
    zcross_time: Optional[pd.Timestamp] = None,
    entry_time: time = C.ENTRY_TIME,
    hard_close: time = C.HARD_CLOSE,
    slippage_bps_roundtrip: int = C.SLIPPAGE_BPS_ROUNDTRIP,
) -> dict:
    """Walk minute bars from entry_time → hard_close, return one trade record.

    bars: DataFrame with columns timestamp_ist (datetime), open, high, low, close
    side: "LONG" or "SHORT"
    stop_pct: ATR-based stop, NEGATIVE (e.g., -3.0 for 3% loss).
    zcross_time: if not None, force-exit at the close of the bar whose
                 timestamp ≥ zcross_time.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side!r}")
    if stop_pct >= 0:
        raise ValueError(f"stop_pct must be negative, got {stop_pct}")
    if bars.empty:
        return _no_entry()

    times = bars["timestamp_ist"].dt.time
    entry_mask = times >= entry_time
    if not entry_mask.any():
        return _no_entry()

    entry_idx_pos = np.argmax(entry_mask.to_numpy())
    entry_row = bars.iloc[entry_idx_pos]
    entry_price = float(entry_row["close"])
    entry_ts = entry_row["timestamp_ist"]

    walk = bars.iloc[entry_idx_pos + 1:].copy()
    walk = walk[walk["timestamp_ist"].dt.time <= hard_close]
    if walk.empty:
        # Edge case: 09:30 bar is the last bar in the session — flat exit.
        return _record(
            entry_ts=entry_ts,
            entry_price=entry_price,
            exit_ts=entry_ts,
            exit_price=entry_price,
            side=side,
            exit_reason="TIME_STOP",
            mfe=0.0,
            slippage_bps=slippage_bps_roundtrip,
        )

    peak = 0.0
    last_bar = walk.iloc[-1]

    for _, bar in walk.iterrows():
        bar_ts = bar["timestamp_ist"]
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        bar_min_pnl, bar_max_pnl = _bar_signed_extreme(entry_price, high, low, side)
        bar_close_pnl = _signed_return(entry_price, close, side)

        # 1) ATR_STOP — intra-bar low (LONG) or high (SHORT) breach.
        if bar_min_pnl <= stop_pct:
            # Exit at the stop price itself, not the bar's intra-bar extreme.
            exit_pnl_no_slip = stop_pct
            exit_price = entry_price * (1 + (exit_pnl_no_slip / 100.0)) if side == "LONG" \
                else entry_price * (1 - (exit_pnl_no_slip / 100.0))
            return _record(
                entry_ts=entry_ts,
                entry_price=entry_price,
                exit_ts=bar_ts,
                exit_price=exit_price,
                side=side,
                exit_reason="ATR_STOP",
                mfe=peak,
                slippage_bps=slippage_bps_roundtrip,
                forced_pnl=exit_pnl_no_slip,
            )

        # 2) Z_CROSS — provided exit time reached.
        if zcross_time is not None and bar_ts >= zcross_time:
            return _record(
                entry_ts=entry_ts,
                entry_price=entry_price,
                exit_ts=bar_ts,
                exit_price=close,
                side=side,
                exit_reason="Z_CROSS",
                mfe=max(peak, bar_max_pnl),
                slippage_bps=slippage_bps_roundtrip,
            )

        # 3) Ratchet peak; check trail give-back if armed.
        if bar_max_pnl > peak:
            peak = bar_max_pnl
        if peak >= C.TRAIL_ARM_PCT and (peak - bar_close_pnl) >= C.TRAIL_GIVEBACK_PCT:
            exit_pnl_no_slip = peak - C.TRAIL_GIVEBACK_PCT
            exit_price = entry_price * (1 + (exit_pnl_no_slip / 100.0)) if side == "LONG" \
                else entry_price * (1 - (exit_pnl_no_slip / 100.0))
            return _record(
                entry_ts=entry_ts,
                entry_price=entry_price,
                exit_ts=bar_ts,
                exit_price=exit_price,
                side=side,
                exit_reason="TRAIL",
                mfe=peak,
                slippage_bps=slippage_bps_roundtrip,
                forced_pnl=exit_pnl_no_slip,
            )

    # 4) TIME_STOP at the last bar's close.
    return _record(
        entry_ts=entry_ts,
        entry_price=entry_price,
        exit_ts=last_bar["timestamp_ist"],
        exit_price=float(last_bar["close"]),
        side=side,
        exit_reason="TIME_STOP",
        mfe=peak,
        slippage_bps=slippage_bps_roundtrip,
    )


def _no_entry() -> dict:
    return {
        "exit_reason": "NO_ENTRY",
        "pnl_pct": 0.0,
        "mfe_pct": 0.0,
        "entry_time": None,
        "exit_time": None,
        "entry_price": None,
        "exit_price": None,
        "side": None,
    }


def _record(
    *,
    entry_ts,
    entry_price: float,
    exit_ts,
    exit_price: float,
    side: str,
    exit_reason: str,
    mfe: float,
    slippage_bps: int,
    forced_pnl: float | None = None,
) -> dict:
    """Assemble the trade record with slippage applied."""
    raw_pnl = forced_pnl if forced_pnl is not None else _signed_return(entry_price, exit_price, side)
    slip_pp = slippage_bps / 100.0  # bps → pp
    pnl_after_slip = raw_pnl - slip_pp
    return {
        "exit_reason": exit_reason,
        "pnl_pct": round(pnl_after_slip, 4),
        "mfe_pct": round(max(mfe, raw_pnl), 4),
        "entry_time": entry_ts,
        "exit_time": exit_ts,
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "side": side,
    }
