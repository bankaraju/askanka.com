"""Historical replay: re-run closed signals through the trail-stop logic.

For each closed signal we have entry prices, the close date, and the final
P&L. This module walks each trading day between open and close using daily
OHLC (close prices) for every leg, updates a synthetic running peak and
trail_stop, and reports what date/P&L the trade would have exited at if the
trail stop had been live.

Output: list of {signal_id, actual_exit, simulated_exit, delta_pct} dicts.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow imports from pipeline/ root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signal_tracker import compute_trail_budget, trail_stop_triggered  # type: ignore


def _spread_pnl_pct(
    long_legs: List[Dict[str, Any]],
    short_legs: List[Dict[str, Any]],
    prices_on_day: Dict[str, float],
) -> Optional[float]:
    """Cumulative spread P&L from entry for a given day's closes.

    Returns None when any leg is missing a price for that day.
    """
    long_moves = []
    for leg in long_legs:
        curr = prices_on_day.get(leg["ticker"])
        entry = leg["price"]
        if curr is None or not entry:
            return None
        long_moves.append((curr / entry - 1) * 100)

    short_moves = []
    for leg in short_legs:
        curr = prices_on_day.get(leg["ticker"])
        entry = leg["price"]
        if curr is None or not entry:
            return None
        short_moves.append((1 - curr / entry) * 100)

    avg_long = sum(long_moves) / len(long_moves) if long_moves else 0.0
    avg_short = sum(short_moves) / len(short_moves) if short_moves else 0.0
    return round(avg_long + avg_short, 4)


def _dates_in_window(
    daily_prices: Dict[str, List[Tuple[str, float]]],
) -> List[str]:
    """Return the sorted union of all dates that appear in every leg."""
    common: Optional[set] = None
    for series in daily_prices.values():
        ds = {d for d, _ in series}
        common = ds if common is None else (common & ds)
    return sorted(common or [])


def simulate_signal(
    signal: Dict[str, Any],
    daily_prices: Dict[str, List[Tuple[str, float]]],
    levels: Dict[str, Any],
) -> Dict[str, Any]:
    """Replay one closed signal with trail-stop logic.

    Args:
        signal: Closed signal dict (needs long_legs, short_legs, open/close
            timestamps, final_pnl, peak_spread_pnl_pct).
        daily_prices: {ticker: [(YYYY-MM-DD, close_price), ...]} covering
            at least open_date..close_date for every leg ticker.
        levels: {"avg_favorable_move": float, "daily_std": float} for this
            spread (from spread_stats.json).

    Returns:
        {signal_id, spread_name, open_date, actual_exit, simulated_exit, delta_pct}
    """
    long_legs  = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])
    actual_close = (signal.get("close_timestamp") or "")[:10]
    actual_pnl  = (signal.get("final_pnl") or {}).get("spread_pnl_pct", 0) or 0
    actual_status = signal.get("status", "")

    avg_fav = levels.get("avg_favorable_move", 0.0) or 0.0

    # Build {date: {ticker: price}} for iteration
    by_date: Dict[str, Dict[str, float]] = {}
    for ticker, series in daily_prices.items():
        for date, price in series:
            by_date.setdefault(date, {})[ticker] = price

    dates = _dates_in_window(daily_prices)

    peak = 0.0
    sim_exit_date: Optional[str] = None
    sim_exit_pnl: Optional[float] = None
    prev_date: Optional[str] = None

    for date in dates:
        if date > actual_close:
            break
        prices_today = by_date.get(date, {})
        cum = _spread_pnl_pct(long_legs, short_legs, prices_today)
        if cum is None:
            continue

        if cum > peak:
            peak = cum

        if prev_date is None:
            days_since = 1
        else:
            from datetime import datetime as _dt
            a = _dt.strptime(prev_date, "%Y-%m-%d")
            b = _dt.strptime(date, "%Y-%m-%d")
            days_since = max(1, (b - a).days)
        prev_date = date

        budget = compute_trail_budget(avg_fav, days_since)
        if trail_stop_triggered(cum, peak, budget):
            sim_exit_date = date
            sim_exit_pnl = cum
            break

    if sim_exit_date is None:
        sim_exit = {
            "date": actual_close,
            "reason": "ACTUAL_CLOSE",
            "pnl_pct": round(actual_pnl, 2),
        }
        delta = 0.0
    else:
        sim_exit = {
            "date": sim_exit_date,
            "reason": "TRAIL_STOP",
            "pnl_pct": round(sim_exit_pnl, 2),
        }
        delta = round(sim_exit_pnl - actual_pnl, 2)

    return {
        "signal_id": signal.get("signal_id", ""),
        "spread_name": signal.get("spread_name", ""),
        "open_date": (signal.get("open_timestamp") or "")[:10],
        "actual_exit": {
            "date": actual_close,
            "reason": actual_status,
            "pnl_pct": round(actual_pnl, 2),
        },
        "simulated_exit": sim_exit,
        "delta_pct": delta,
    }
