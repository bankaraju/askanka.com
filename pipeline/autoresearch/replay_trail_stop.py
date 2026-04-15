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


import json
from datetime import datetime, timedelta


PIPELINE_ROOT = Path(__file__).resolve().parent.parent
CLOSED_SIGS_PATH = PIPELINE_ROOT / "data" / "signals" / "closed_signals.json"
SPREAD_STATS_PATH = PIPELINE_ROOT / "data" / "spread_stats.json"
OUTPUT_PATH = PIPELINE_ROOT.parent / "data" / "trail_stop_replay.json"


def _fetch_daily_closes(
    tickers: List[str],
    start_date: str,
    end_date: str,
) -> Dict[str, List[Tuple[str, float]]]:
    """Fetch daily closes for each ticker via yfinance.

    Tickers without a dot or caret are treated as NSE names and suffixed
    with ``.NS``. start_date/end_date are YYYY-MM-DD strings (inclusive).
    """
    import yfinance as yf  # noqa: WPS433

    result: Dict[str, List[Tuple[str, float]]] = {}
    end_dt = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")

    for tk in tickers:
        yf_symbol = tk if "." in tk or "^" in tk else f"{tk}.NS"
        hist = yf.Ticker(yf_symbol).history(start=start_date, end=end_dt)
        if hist.empty:
            result[tk] = []
            continue
        series = []
        for idx, row in hist.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            close = float(row["Close"])
            series.append((date_str, close))
        result[tk] = series
    return result


def _load_levels_for(spread_name: str, stats_all: dict) -> Dict[str, float]:
    """Pull avg_favorable + daily_std from spread_stats.json for one spread.

    Handles multiple shapes:
    - Flat: {name: {avg_favorable_move: ..., daily_std: ...}}
    - Nested overall: {name: {overall: {avg_favorable_move: ..., daily_std: ...}}}
    - Regime-keyed: {name: {MACRO_NEUTRAL: {mean: ..., std: ...}, ...}}
      In this case we average mean/std across all regimes and map to the
      expected field names (mean -> avg_favorable_move, std -> daily_std).
    """
    entry = stats_all.get(spread_name)
    if entry is None:
        entry = stats_all.get("spreads", {}).get(spread_name, {})
    if not isinstance(entry, dict):
        return {"avg_favorable_move": 0.0, "daily_std": 0.0}

    # Nested overall shape
    if "overall" in entry:
        entry = entry["overall"]
        if not isinstance(entry, dict):
            return {"avg_favorable_move": 0.0, "daily_std": 0.0}

    # Flat shape: has avg_favorable_move directly
    if "avg_favorable_move" in entry:
        return {
            "avg_favorable_move": float(entry.get("avg_favorable_move", 0.0) or 0.0),
            "daily_std": float(entry.get("daily_std", 0.0) or 0.0),
        }

    # Flat shape: has mean directly (no nested regimes)
    if "mean" in entry and not any(
        isinstance(v, dict) for v in entry.values()
    ):
        return {
            "avg_favorable_move": float(entry.get("mean", 0.0) or 0.0),
            "daily_std": float(entry.get("std", 0.0) or 0.0),
        }

    # Regime-keyed shape: {MACRO_NEUTRAL: {mean: ..., std: ...}, ...}
    # Average across all regimes weighted equally.
    means = []
    stds = []
    for regime_val in entry.values():
        if not isinstance(regime_val, dict):
            continue
        m = regime_val.get("mean", 0.0)
        s = regime_val.get("std", 0.0)
        if m is not None:
            means.append(float(m))
        if s is not None:
            stds.append(float(s))
    if not means:
        return {"avg_favorable_move": 0.0, "daily_std": 0.0}
    return {
        "avg_favorable_move": sum(means) / len(means),
        "daily_std": sum(stds) / len(stds) if stds else 0.0,
    }


def run_replay() -> Dict[str, Any]:
    """Replay every closed signal; write result to data/trail_stop_replay.json."""
    closed = json.loads(CLOSED_SIGS_PATH.read_text(encoding="utf-8"))
    stats_all = json.loads(SPREAD_STATS_PATH.read_text(encoding="utf-8")) if SPREAD_STATS_PATH.exists() else {}

    trades: List[Dict[str, Any]] = []
    actual_sum = 0.0
    sim_sum = 0.0
    improved = 0
    worse = 0

    for sig in closed:
        tickers = [l["ticker"] for l in sig.get("long_legs", []) + sig.get("short_legs", [])]
        open_date = (sig.get("open_timestamp") or "")[:10]
        close_date = (sig.get("close_timestamp") or "")[:10]
        if not (open_date and close_date and tickers):
            continue

        try:
            prices = _fetch_daily_closes(tickers, open_date, close_date)
        except Exception as e:
            print(f"  skip {sig.get('signal_id')}: fetch failed ({e})")
            continue

        levels = _load_levels_for(sig.get("spread_name", ""), stats_all)
        if levels["avg_favorable_move"] == 0:
            print(f"  skip {sig.get('signal_id')}: no stats for {sig.get('spread_name')}")
            continue

        result = simulate_signal(sig, prices, levels)
        trades.append(result)

        actual_sum += result["actual_exit"]["pnl_pct"]
        sim_sum    += result["simulated_exit"]["pnl_pct"]
        if result["delta_pct"] > 0:
            improved += 1
        elif result["delta_pct"] < 0:
            worse += 1

    out = {
        "updated_at": datetime.now().isoformat(),
        "total_trades": len(trades),
        "trades_improved": improved,
        "trades_worse": worse,
        "actual_pnl_sum_pct": round(actual_sum, 2),
        "simulated_pnl_sum_pct": round(sim_sum, 2),
        "delta_sum_pct": round(sim_sum - actual_sum, 2),
        "trades": trades,
    }

    OUTPUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  Trades: {len(trades)}  improved: {improved}  worse: {worse}")
    print(f"  Actual sum: {actual_sum:+.2f}%  Simulated: {sim_sum:+.2f}%  Delta: {sim_sum - actual_sum:+.2f}%")
    return out


if __name__ == "__main__":
    run_replay()
