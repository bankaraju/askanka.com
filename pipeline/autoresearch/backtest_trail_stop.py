"""Historical backtest + parameter sweep for the trail-stop rule.

For each spread pair in INDIA_SPREAD_PAIRS:
  1. Pull daily OHLC per leg from yfinance (6 months).
  2. Compute daily spread returns + overnight (gap) vs intraday split.
  3. Synthesize N-day trades starting from every day in the window.
  4. For each (budget_mult, arm_factor) combo, simulate the trail stop
     and record exit P&L. Compare against a "no-stop" baseline that
     holds the full N days.
  5. Aggregate per-param: mean / median / win-rate / Sharpe / max loss.

Gap attribution per pair: what fraction of absolute daily move came from
the overnight gap (prev_close -> today_open) vs intraday (open -> close).

Output:
  data/backtest_trail_stop.json — ranked param results + gap-attribution
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INDIA_SPREAD_PAIRS  # type: ignore
from replay_trail_stop import YF_TICKER_ALIASES  # type: ignore


OUTPUT_PATH = PIPELINE_ROOT.parent / "data" / "backtest_trail_stop.json"
HOLD_DAYS = 10           # max hold for synthetic trades
LOOKBACK_MONTHS = 6      # how much history to fetch
PARAM_BUDGETS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
PARAM_ARMS    = [1.0, 2.0, 3.0, 5.0]


def _fetch_ohlc(ticker: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch daily OHLC rows for a ticker. Returns [] on failure."""
    import yfinance as yf  # noqa: WPS433

    mapped = YF_TICKER_ALIASES.get(ticker, ticker)
    yf_symbol = mapped if "." in mapped or "^" in mapped else f"{mapped}.NS"
    try:
        hist = yf.Ticker(yf_symbol).history(start=start, end=end)
    except Exception:
        return []
    if hist.empty:
        return []
    out = []
    for idx, row in hist.iterrows():
        out.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(row["Open"]),
            "close": float(row["Close"]),
        })
    return out


def _compute_spread_series(
    long_ohlc: Dict[str, List[Dict[str, Any]]],
    short_ohlc: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Merge per-leg OHLC into daily spread returns.

    Returns a list of dicts, one per trading day common to all legs:
      {date, close_return, gap_return, intra_return, close_level}

    close_return is today's spread return vs yesterday's close.
    gap_return is yesterday-close -> today-open.
    intra_return is today-open -> today-close.
    close_level is cumulative spread from series start (for trade simulation).
    """
    # Build per-date dicts keyed by leg
    def _by_date(series: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        return {r["date"]: r for r in series}

    longs  = {tk: _by_date(s) for tk, s in long_ohlc.items()}
    shorts = {tk: _by_date(s) for tk, s in short_ohlc.items()}

    # Common dates across ALL legs
    all_sets = [set(d.keys()) for d in list(longs.values()) + list(shorts.values())]
    if not all_sets:
        return []
    common = sorted(set.intersection(*all_sets))
    if len(common) < 2:
        return []

    series = []
    prev_date = None
    cum_level = 0.0
    for date in common:
        row = {"date": date}
        # Today's per-leg open/close
        if prev_date is None:
            prev_date = date
            continue

        # Long leg daily move (close vs prev close) — average across legs
        def _avg_ret(legs_map, is_long: bool) -> Tuple[float, float, float]:
            """Return (close_ret, gap_ret, intra_ret) averaged across legs."""
            c_rets, g_rets, i_rets = [], [], []
            for tk, by_d in legs_map.items():
                t = by_d.get(date)
                p = by_d.get(prev_date)
                if not t or not p or p["close"] <= 0 or t["open"] <= 0:
                    continue
                # Close return: prev_close -> today_close
                c_ret = (t["close"] / p["close"] - 1) * 100
                # Gap: prev_close -> today_open
                g_ret = (t["open"] / p["close"] - 1) * 100
                # Intraday: today_open -> today_close
                i_ret = (t["close"] / t["open"] - 1) * 100
                # For short legs, invert sign so positive = profit
                if not is_long:
                    c_ret, g_ret, i_ret = -c_ret, -g_ret, -i_ret
                c_rets.append(c_ret)
                g_rets.append(g_ret)
                i_rets.append(i_ret)
            if not c_rets:
                return (0.0, 0.0, 0.0)
            return (
                sum(c_rets) / len(c_rets),
                sum(g_rets) / len(g_rets),
                sum(i_rets) / len(i_rets),
            )

        long_c, long_g, long_i = _avg_ret(longs, is_long=True)
        short_c, short_g, short_i = _avg_ret(shorts, is_long=False)

        close_ret = long_c + short_c
        gap_ret   = long_g + short_g
        intra_ret = long_i + short_i

        cum_level += close_ret
        series.append({
            "date": date,
            "close_return": round(close_ret, 4),
            "gap_return":   round(gap_ret, 4),
            "intra_return": round(intra_ret, 4),
            "close_level":  round(cum_level, 4),
        })
        prev_date = date

    return series


def _gap_attribution(series: List[Dict[str, Any]]) -> Dict[str, float]:
    """Fraction of absolute daily move explained by overnight gap.

    Metric: sum(|gap|) / sum(|gap| + |intra|).
    Also returns the raw sums and sample counts so low-N pairs are flagged.
    """
    gaps = [abs(r["gap_return"])   for r in series]
    intras = [abs(r["intra_return"]) for r in series]
    total_gap = sum(gaps)
    total_intra = sum(intras)
    denom = total_gap + total_intra
    pct = (total_gap / denom * 100) if denom > 0 else 0.0
    return {
        "gap_pct_of_move": round(pct, 1),
        "sum_abs_gap":     round(total_gap, 2),
        "sum_abs_intra":   round(total_intra, 2),
        "n_days":          len(series),
    }


def _simulate_trade(
    series: List[Dict[str, Any]],
    start_idx: int,
    hold_days: int,
    avg_favorable: float,
    budget_mult: float,
    arm_factor: float,
) -> Dict[str, Any]:
    """Open a synthetic trade at close of series[start_idx], hold for up to
    hold_days trading days, apply parametrised trail stop each day.

    Returns {exit_pnl, exit_idx, reason}.
    """
    entry_level = series[start_idx]["close_level"]
    peak = 0.0
    last_date = series[start_idx]["date"]

    for offset in range(1, hold_days + 1):
        i = start_idx + offset
        if i >= len(series):
            break
        row = series[i]
        cum = row["close_level"] - entry_level
        if cum > peak:
            peak = cum

        # Days since last observation (holidays widen the budget)
        from datetime import datetime as _dt
        d0 = _dt.strptime(last_date, "%Y-%m-%d")
        d1 = _dt.strptime(row["date"], "%Y-%m-%d")
        days_since = max(1, (d1 - d0).days)
        last_date = row["date"]

        budget = avg_favorable * budget_mult * math.sqrt(days_since)
        if budget > 0 and peak >= budget * arm_factor and cum <= (peak - budget):
            return {"exit_pnl": round(cum, 2), "exit_idx": i, "reason": "TRAIL"}

    # Held to expiry
    last_i = min(start_idx + hold_days, len(series) - 1)
    cum = series[last_i]["close_level"] - entry_level
    return {"exit_pnl": round(cum, 2), "exit_idx": last_i, "reason": "EXPIRY"}


def _aggregate(pnls: List[float]) -> Dict[str, float]:
    if not pnls:
        return {"n": 0, "mean": 0.0, "median": 0.0, "win_rate": 0.0, "sharpe": 0.0, "worst": 0.0, "best": 0.0}
    mean = statistics.mean(pnls)
    std = statistics.pstdev(pnls) if len(pnls) > 1 else 0.0
    sharpe = (mean / std * math.sqrt(252 / HOLD_DAYS)) if std > 0 else 0.0
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n":        len(pnls),
        "mean":     round(mean, 3),
        "median":   round(statistics.median(pnls), 3),
        "win_rate": round(wins / len(pnls) * 100, 1),
        "sharpe":   round(sharpe, 2),
        "worst":    round(min(pnls), 2),
        "best":     round(max(pnls), 2),
    }


def run_backtest() -> Dict[str, Any]:
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=LOOKBACK_MONTHS * 31)).strftime("%Y-%m-%d")

    load_stats = json.loads((PIPELINE_ROOT.parent / "data" / "spread_stats.json").read_text(encoding="utf-8"))

    per_pair: Dict[str, Any] = {}
    # Per-param aggregates across all pairs
    pool: Dict[Tuple[float, float], List[float]] = {
        (bm, af): [] for bm in PARAM_BUDGETS for af in PARAM_ARMS
    }
    baseline_pool: List[float] = []

    for pair in INDIA_SPREAD_PAIRS:
        name = pair["name"]
        stats = load_stats.get(name, {})
        avg_fav = float(stats.get("avg_favorable_move") or 0)
        if avg_fav <= 0:
            print(f"  skip {name}: no avg_favorable")
            continue

        print(f"  fetching {name} ...", end=" ", flush=True)
        long_ohlc  = {tk: _fetch_ohlc(tk, start_date, end_date) for tk in pair["long"]}
        short_ohlc = {tk: _fetch_ohlc(tk, start_date, end_date) for tk in pair["short"]}

        # Skip pairs with any leg returning zero rows
        missing = [tk for tk, s in {**long_ohlc, **short_ohlc}.items() if not s]
        if missing:
            print(f"skip — missing: {missing}")
            continue

        series = _compute_spread_series(long_ohlc, short_ohlc)
        if len(series) < HOLD_DAYS + 5:
            print(f"skip — only {len(series)} days")
            continue

        gap = _gap_attribution(series)

        # Synthesize trades starting from every day that has HOLD_DAYS ahead
        pair_per_param: Dict[str, Dict[str, float]] = {}
        pair_baseline: List[float] = []
        n_trades = len(series) - HOLD_DAYS

        for bm in PARAM_BUDGETS:
            for af in PARAM_ARMS:
                exits = []
                for start_idx in range(n_trades):
                    r = _simulate_trade(series, start_idx, HOLD_DAYS, avg_fav, bm, af)
                    exits.append(r["exit_pnl"])
                    pool[(bm, af)].append(r["exit_pnl"])
                pair_per_param[f"bm={bm}_af={af}"] = _aggregate(exits)

        # Baseline: no stop, hold full HOLD_DAYS
        for start_idx in range(n_trades):
            last_i = min(start_idx + HOLD_DAYS, len(series) - 1)
            pnl = series[last_i]["close_level"] - series[start_idx]["close_level"]
            pair_baseline.append(round(pnl, 2))
            baseline_pool.append(round(pnl, 2))

        per_pair[name] = {
            "avg_favorable":     avg_fav,
            "n_days":            len(series),
            "n_trades":          n_trades,
            "gap_attribution":   gap,
            "baseline_no_stop":  _aggregate(pair_baseline),
            "param_results":     pair_per_param,
        }
        print(f"{len(series)} days, {n_trades} trades, gap%={gap['gap_pct_of_move']}")

    # Global ranking
    rankings = []
    for (bm, af), pnls in pool.items():
        agg = _aggregate(pnls)
        rankings.append({"budget_mult": bm, "arm_factor": af, **agg})
    baseline_agg = _aggregate(baseline_pool)
    # Add baseline as a pseudo-entry for comparison
    rankings_sorted_mean   = sorted(rankings, key=lambda r: -r["mean"])
    rankings_sorted_sharpe = sorted(rankings, key=lambda r: -r["sharpe"])

    out = {
        "updated_at":     datetime.now().isoformat(),
        "hold_days":      HOLD_DAYS,
        "lookback_months": LOOKBACK_MONTHS,
        "window":         f"{start_date} .. {end_date}",
        "n_pairs":        len(per_pair),
        "baseline_no_stop_pooled": baseline_agg,
        "top_by_mean":    rankings_sorted_mean[:10],
        "top_by_sharpe":  rankings_sorted_sharpe[:10],
        "all_params":     rankings_sorted_mean,
        "per_pair":       per_pair,
    }
    OUTPUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"Baseline (no stop, hold {HOLD_DAYS}d): mean {baseline_agg['mean']:+.2f}%  sharpe {baseline_agg['sharpe']:.2f}  win {baseline_agg['win_rate']:.0f}%  n={baseline_agg['n']}")
    print(f"\nTop 5 by mean P&L:")
    for r in rankings_sorted_mean[:5]:
        print(f"  bm={r['budget_mult']} af={r['arm_factor']}: mean {r['mean']:+.2f}%  sharpe {r['sharpe']:.2f}  win {r['win_rate']:.0f}%  worst {r['worst']:+.2f}%")
    print(f"\nTop 5 by Sharpe:")
    for r in rankings_sorted_sharpe[:5]:
        print(f"  bm={r['budget_mult']} af={r['arm_factor']}: mean {r['mean']:+.2f}%  sharpe {r['sharpe']:.2f}  win {r['win_rate']:.0f}%  worst {r['worst']:+.2f}%")
    print(f"\nGap attribution (top drivers):")
    gap_ranked = sorted(per_pair.items(), key=lambda kv: -kv[1]["gap_attribution"]["gap_pct_of_move"])
    for name, p in gap_ranked[:8]:
        g = p["gap_attribution"]
        print(f"  {name:<30} gap% of move: {g['gap_pct_of_move']}%  (abs_gap {g['sum_abs_gap']} vs abs_intra {g['sum_abs_intra']})")
    return out


if __name__ == "__main__":
    run_backtest()
