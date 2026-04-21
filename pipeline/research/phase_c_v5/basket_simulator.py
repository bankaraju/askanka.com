"""Multi-leg daily basket replay.

Takes a basket (list of long legs + list of short legs, each with a weight),
enters at each leg's open on ``entry_date``, exits at each leg's close
``hold_days`` trading days later, aggregates P&L with round-trip costs.
"""
from __future__ import annotations

import logging
import pandas as pd

from pipeline.research.phase_c_backtest.cost_model import round_trip_cost_inr

log = logging.getLogger(__name__)


def _entry_close_rows(
    bars: pd.DataFrame, entry_date: pd.Timestamp, hold_days: int
) -> tuple[pd.Series, pd.Series] | None:
    """Return (entry_bar, exit_bar) or None if either is missing.

    If hold_days=5, we apply 5 days of price movements.
    Index-wise, that's entry_idx + hold_days.
    """
    df = bars.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    entry_rows = df.loc[df["date"] == entry_date]
    if entry_rows.empty:
        return None
    entry = entry_rows.iloc[0]
    entry_idx = entry.name
    exit_idx = entry_idx + hold_days
    if exit_idx >= len(df):
        return None
    return entry, df.iloc[exit_idx]


def simulate_basket_trade(
    entry_date: pd.Timestamp,
    long_legs: list[dict],
    short_legs: list[dict],
    symbol_bars: dict[str, pd.DataFrame],
    hold_days: int,
    notional_per_leg_inr: float = 50_000,
    slippage_bps: float = 5.0,
) -> dict | None:
    """Simulate a multi-leg basket trade.

    Each long leg enters at bar open on ``entry_date``, exits at close of the
    ``hold_days``-th subsequent bar. Each short leg mirrors. Leg notional is
    ``notional_per_leg_inr * weight`` for longs, same for shorts.

    Returns a dict with gross P&L, net P&L, notional total, leg count, entry
    and exit dates. Returns ``None`` if any leg's bars are missing.
    """
    if hold_days < 1:
        raise ValueError("hold_days must be >= 1")

    legs_rendered: list[dict] = []
    gross_pnl = 0.0
    cost_total = 0.0
    notional_total = 0.0
    exit_date: pd.Timestamp | None = None

    for side, legs in (("LONG", long_legs), ("SHORT", short_legs)):
        for leg in legs:
            sym = leg["symbol"]
            weight = float(leg.get("weight", 1.0))
            bars = symbol_bars.get(sym)
            if bars is None or bars.empty:
                log.debug("skip basket: missing bars for %s on %s", sym, entry_date.date())
                return None
            rows = _entry_close_rows(bars, entry_date, hold_days)
            if rows is None:
                log.debug("skip basket: incomplete bars for %s around %s", sym, entry_date.date())
                return None
            entry_row, exit_row = rows
            entry_px = float(entry_row["open"])
            exit_px = float(exit_row["close"])
            leg_notional = notional_per_leg_inr * weight
            if side == "LONG":
                leg_gross = (exit_px / entry_px - 1.0) * leg_notional
            else:
                leg_gross = (entry_px / exit_px - 1.0) * leg_notional
            leg_cost = round_trip_cost_inr(leg_notional, side, slippage_bps)
            gross_pnl += leg_gross
            cost_total += leg_cost
            notional_total += leg_notional
            exit_date = pd.Timestamp(exit_row["date"])
            legs_rendered.append({
                "symbol": sym, "side": side, "weight": weight,
                "entry_px": entry_px, "exit_px": exit_px,
                "leg_notional": leg_notional, "leg_gross_inr": leg_gross,
                "leg_cost_inr": leg_cost,
            })

    return {
        "entry_date": pd.Timestamp(entry_date),
        "exit_date": exit_date,
        "hold_days": hold_days,
        "side_count_long": len(long_legs),
        "side_count_short": len(short_legs),
        "notional_total_inr": notional_total,
        "pnl_gross_inr": gross_pnl,
        "pnl_cost_inr": cost_total,
        "pnl_net_inr": gross_pnl - cost_total,
        "legs": legs_rendered,
    }
