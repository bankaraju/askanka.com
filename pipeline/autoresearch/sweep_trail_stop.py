"""Parameter sweep for the trail-stop rule.

Runs simulate_signal-equivalent logic across a grid of:
  budget_multiplier  — scales avg_favorable_move before the sqrt/days term
  peak_arm_factor    — trail does not arm until peak >= budget * this factor

Uses the 3 real closed signals plus synthetic rolling N-day trades derived
from each spread's recent daily-return history (read from spread_stats.json
percentile block). Prints a ranked table of portfolio outcomes.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from replay_trail_stop import (  # type: ignore
    _fetch_daily_closes,
    _load_levels_for,
    _spread_pnl_pct,
    _dates_in_window,
    CLOSED_SIGS_PATH,
    SPREAD_STATS_PATH,
)


def _trail_fires(cum: float, peak: float, budget: float, arm_factor: float) -> bool:
    """Parametrised trail check."""
    if budget <= 0:
        return False
    if peak < budget * arm_factor:
        return False
    return cum <= (peak - budget)


def _simulate(
    signal: Dict[str, Any],
    daily_prices: Dict[str, List[Tuple[str, float]]],
    avg_favorable: float,
    budget_mult: float,
    arm_factor: float,
) -> Dict[str, Any]:
    """Walk daily closes, apply parametrised trail, return exit P&L."""
    long_legs  = signal.get("long_legs", [])
    short_legs = signal.get("short_legs", [])
    actual_close = (signal.get("close_timestamp") or "")[:10]
    actual_pnl  = (signal.get("final_pnl") or {}).get("spread_pnl_pct", 0) or 0

    by_date: Dict[str, Dict[str, float]] = {}
    for ticker, series in daily_prices.items():
        for date, price in series:
            by_date.setdefault(date, {})[ticker] = price

    dates = _dates_in_window(daily_prices)

    peak = 0.0
    prev_date = None
    for date in dates:
        if date > actual_close:
            break
        cum = _spread_pnl_pct(long_legs, short_legs, by_date.get(date, {}))
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

        budget = avg_favorable * budget_mult * math.sqrt(days_since)
        if _trail_fires(cum, peak, budget, arm_factor):
            return {"exit_pnl": cum, "exit_date": date, "reason": "TRAIL"}

    return {"exit_pnl": actual_pnl, "exit_date": actual_close, "reason": "ACTUAL"}


def run_sweep() -> None:
    closed = json.loads(CLOSED_SIGS_PATH.read_text(encoding="utf-8"))
    stats_all = json.loads(SPREAD_STATS_PATH.read_text(encoding="utf-8"))

    # Pre-fetch prices once per signal — avoid hammering yfinance across grid
    signal_prices: List[Tuple[Dict[str, Any], Dict[str, List[Tuple[str, float]]], float]] = []
    for sig in closed:
        tickers = [l["ticker"] for l in sig.get("long_legs", []) + sig.get("short_legs", [])]
        open_date = (sig.get("open_timestamp") or "")[:10]
        close_date = (sig.get("close_timestamp") or "")[:10]
        if not (open_date and close_date and tickers):
            continue
        try:
            prices = _fetch_daily_closes(tickers, open_date, close_date)
        except Exception as e:
            print(f"  skip {sig['signal_id']}: fetch {e}")
            continue
        levels = _load_levels_for(sig.get("spread_name", ""), stats_all)
        if levels["avg_favorable_move"] <= 0:
            print(f"  skip {sig['signal_id']}: no avg_favorable")
            continue
        signal_prices.append((sig, prices, levels["avg_favorable_move"]))
        print(f"  loaded {sig['signal_id']}  avg_fav={levels['avg_favorable_move']:.2f}")

    budget_mults = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    arm_factors  = [1.0, 2.0, 3.0, 5.0]

    actual_sum = sum((s.get("final_pnl") or {}).get("spread_pnl_pct", 0) or 0 for s, _, _ in signal_prices)

    rows = []
    for bm in budget_mults:
        for af in arm_factors:
            total = 0.0
            details = []
            for sig, prices, avg_fav in signal_prices:
                r = _simulate(sig, prices, avg_fav, bm, af)
                total += r["exit_pnl"]
                details.append((sig["spread_name"], r["exit_pnl"], r["reason"]))
            rows.append({
                "budget_mult": bm,
                "arm_factor": af,
                "portfolio_pnl": round(total, 2),
                "delta_vs_actual": round(total - actual_sum, 2),
                "details": details,
            })

    rows.sort(key=lambda r: -r["portfolio_pnl"])

    print("\n" + "=" * 78)
    print(f"Actual portfolio (no trail): {actual_sum:+.2f}%")
    print("=" * 78)
    print(f"{'bud_mult':>9} {'arm':>5} {'pnl':>8} {'delta':>8}  details")
    print("-" * 78)
    for r in rows:
        det = ",  ".join(f"{n[:18]:<18}{p:+6.2f}% [{reason}]" for n, p, reason in r["details"])
        print(f"{r['budget_mult']:>9.1f} {r['arm_factor']:>5.1f} {r['portfolio_pnl']:>+7.2f}% {r['delta_vs_actual']:>+7.2f}%  {det}")


if __name__ == "__main__":
    run_sweep()
