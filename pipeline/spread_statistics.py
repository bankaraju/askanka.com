"""
Anka Research Pipeline — Spread Statistics
Computes historical spread return distributions for each of 11 India spread
pairs, tagged by macro regime, over 5 years of daily price data from EODHD.

Entry point:  python spread_statistics.py
Output:       data/spread_stats.json

Functions
---------
compute_spread_return(long_prev, long_curr, short_prev, short_curr) -> float
    Equal-weight spread return for one day.

compute_regime_stats(daily_data) -> dict
    Per-regime distribution stats from a list of daily observations.

compute_all_spread_stats() -> dict
    Full 5yr batch run across all 11 INDIA_SPREAD_PAIRS.

Legacy helpers (kept for backward compat with signal_tracker.py callers)
---------
compute_spread_stats, get_spread_stats, get_levels_for_spread,
classify_entry_zone, save_stats, load_stats
"""

import json
import logging
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure bundled lib/ packages are importable when run directly
_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from config import INDIA_SIGNAL_STOCKS, INDIA_SPREAD_PAIRS
from eodhd_client import fetch_eod_series

# Minimum-sample floor — single source of truth is spread_bootstrap.
# Import the constant lazily here to avoid a circular import (spread_bootstrap
# imports from spread_statistics, not the other way around).
def _get_min_samples_provisional() -> int:
    try:
        from spread_bootstrap import MIN_SAMPLES_PROVISIONAL
        return MIN_SAMPLES_PROVISIONAL
    except ImportError:
        return 15  # hard fallback if spread_bootstrap not yet on path

log = logging.getLogger("anka.spread_statistics")

IST = timezone(timedelta(hours=5, minutes=30))

# Paths
_PIPELINE_DIR = Path(__file__).parent
_DATA_DIR     = _PIPELINE_DIR.parent / "data"
DATA_DIR      = _DATA_DIR          # legacy alias used by save_stats / load_stats
_MSI_HISTORY  = _DATA_DIR / "msi_history.json"
_OUTPUT_FILE  = _DATA_DIR / "spread_stats.json"
STATS_FILE    = _OUTPUT_FILE        # legacy alias

# MSI thresholds → regime names
MSI_MACRO_STRESS_MIN  = 65.0   # msi_score >= 65 → MACRO_STRESS
MSI_MACRO_NEUTRAL_MIN = 35.0   # 35 <= msi_score < 65 → MACRO_NEUTRAL
# msi_score < 35 → MACRO_EASY

# Correlation threshold above which we warn that legs move together
CORRELATION_WARNING_THRESHOLD = 0.8

# Stop-loss audit parameters
STOP_AUDIT_STD_MULTIPLIER = 1.0   # consecutive days beyond 1 std
STOP_AUDIT_LOOKAHEAD      = 5     # days to measure return after stop

# Cache duration for legacy helpers
_CACHE_TTL_HOURS = 12


# =============================================================================
# NEW API — regime-tagged 5yr distributions
# =============================================================================

def compute_spread_return(
    long_prev:  dict,
    long_curr:  dict,
    short_prev: dict,
    short_curr: dict,
) -> float:
    """
    Compute one-day spread return using equal-weight averaging per leg.

    Parameters
    ----------
    long_prev, long_curr  : {symbol: price} dicts for the long basket
    short_prev, short_curr: {symbol: price} dicts for the short basket

    Returns
    -------
    float : avg(long_returns) - avg(short_returns)
            where return = (curr - prev) / prev for each symbol.
    """
    def _avg_return(prev: dict, curr: dict) -> float:
        returns = []
        for sym, p in prev.items():
            if sym in curr and p > 0:
                returns.append((curr[sym] - p) / p)
        if not returns:
            return 0.0
        return sum(returns) / len(returns)

    long_ret  = _avg_return(long_prev, long_curr)
    short_ret = _avg_return(short_prev, short_curr)
    return long_ret - short_ret


# ─────────────────────────────────────────────────────────────────────────────
# Statistics helpers (no scipy dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _mean(values: list) -> float:
    return sum(values) / len(values)


def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)  # sample std
    return math.sqrt(variance)


def _percentile(sorted_values: list, p: float) -> float:
    """Linear interpolation percentile (same as numpy default)."""
    n = len(sorted_values)
    if n == 0:
        return float("nan")
    if n == 1:
        return sorted_values[0]
    idx = (p / 100.0) * (n - 1)
    lo  = int(idx)
    hi  = lo + 1
    if hi >= n:
        return sorted_values[-1]
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _pearson(x: list, y: list) -> float:
    """Manual Pearson correlation; returns 0.0 if degenerate."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = _mean(x)
    my = _mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return cov / (sx * sy)


def _max_drawdown(returns: list) -> float:
    """
    Maximum drawdown on cumulative return series.
    Returns a non-positive float (e.g. -0.15 means 15% drawdown).
    """
    if not returns:
        return 0.0
    cum   = 0.0
    peak  = 0.0
    worst = 0.0
    for r in returns:
        cum  += r
        if cum > peak:
            peak = cum
        dd = cum - peak
        if dd < worst:
            worst = dd
    return worst


def _stop_audit(returns: list, std: float) -> dict:
    """
    Simulate a 2-consecutive-day stop-out rule.

    Rule: if the spread return is negative and its absolute value > 1 std
    for 2 days in a row, that's a stop trigger. Report:
      - trigger_count  : how many times this occurred
      - avg_next5_return: average of the cumulative 5-day return
                          starting the day after the stop trigger
    """
    threshold = std  # 1 std
    trigger_count = 0
    next5_returns = []
    n = len(returns)

    i = 1
    while i < n:
        day1 = returns[i - 1]
        day2 = returns[i]
        if day1 < -threshold and day2 < -threshold:
            trigger_count += 1
            # Measure next 5 days
            window = returns[i + 1 : i + 1 + STOP_AUDIT_LOOKAHEAD]
            next5_returns.append(sum(window))
            i += 2  # skip both trigger days
        else:
            i += 1

    avg_next5 = _mean(next5_returns) if next5_returns else 0.0
    return {"stop_trigger_count": trigger_count, "stop_avg_next5_return": avg_next5}


def compute_regime_stats(daily_data: list) -> dict:
    """
    Compute per-regime statistics from a list of daily observations.

    Parameters
    ----------
    daily_data : list of dicts with keys:
        date, regime, spread_return, long_avg, short_avg

    Returns
    -------
    dict keyed by regime name -> {
        count, mean, std,
        p5, p10, p25, p50, p75, p90, p95,
        max_drawdown,
        correlated_warning,
        stop_trigger_count, stop_avg_next5_return
    }
    """
    # Group by regime (preserving insertion order for stop audit)
    by_regime: dict = defaultdict(lambda: {"returns": [], "long_avgs": [], "short_avgs": []})
    for row in daily_data:
        r = row["regime"]
        by_regime[r]["returns"].append(row["spread_return"])
        by_regime[r]["long_avgs"].append(row["long_avg"])
        by_regime[r]["short_avgs"].append(row["short_avg"])

    result = {}
    for regime, buckets in by_regime.items():
        rets   = buckets["returns"]
        longs  = buckets["long_avgs"]
        shorts = buckets["short_avgs"]

        sorted_rets = sorted(rets)
        mu  = _mean(rets)
        sig = _std(rets)

        # Correlation check
        corr = _pearson(longs, shorts)
        correlated_warning = corr > CORRELATION_WARNING_THRESHOLD

        # Max drawdown
        dd = _max_drawdown(rets)

        # Stop audit
        stop = _stop_audit(rets, sig)

        result[regime] = {
            "count":                 len(rets),
            "mean":                  mu,
            "std":                   sig,
            "p5":                    _percentile(sorted_rets, 5),
            "p10":                   _percentile(sorted_rets, 10),
            "p25":                   _percentile(sorted_rets, 25),
            "p50":                   _percentile(sorted_rets, 50),
            "p75":                   _percentile(sorted_rets, 75),
            "p90":                   _percentile(sorted_rets, 90),
            "p95":                   _percentile(sorted_rets, 95),
            "max_drawdown":          dd,
            "correlated_warning":    correlated_warning,
            "stop_trigger_count":    stop["stop_trigger_count"],
            "stop_avg_next5_return": stop["stop_avg_next5_return"],
        }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Regime tagging helpers
# ─────────────────────────────────────────────────────────────────────────────

def _msi_score_to_regime(score: float) -> str:
    if score >= MSI_MACRO_STRESS_MIN:
        return "MACRO_STRESS"
    if score >= MSI_MACRO_NEUTRAL_MIN:
        return "MACRO_NEUTRAL"
    return "MACRO_EASY"


def _load_regime_map() -> dict:
    """
    Load msi_history.json and return {date_str: regime_name}.
    Returns empty dict if file doesn't exist or is malformed.
    """
    if not _MSI_HISTORY.exists():
        log.warning("msi_history.json not found at %s — no regime tagging", _MSI_HISTORY)
        return {}

    try:
        with open(_MSI_HISTORY, "r") as f:
            records = json.load(f)
    except Exception as exc:
        log.warning("Failed to load msi_history.json: %s", exc)
        return {}

    regime_map = {}
    for row in records:
        date = row.get("date")
        if not date:
            continue
        if "regime" in row and row["regime"]:
            regime_map[date] = row["regime"]
        elif "msi_score" in row:
            regime_map[date] = _msi_score_to_regime(float(row["msi_score"]))

    return regime_map


# ─────────────────────────────────────────────────────────────────────────────
# Price series helpers
# ─────────────────────────────────────────────────────────────────────────────

def _symbol_to_eodhd(symbol: str) -> str:
    """Convert bare NSE ticker to EODHD format (e.g. HAL -> HAL.NSE)."""
    return f"{symbol}.NSE"


def _fetch_price_series(symbol: str, days: int = 1825) -> dict:
    """
    Fetch EOD price series for a single symbol.
    Returns {date_str: close_price}.
    """
    eodhd_sym = _symbol_to_eodhd(symbol)
    series = fetch_eod_series(eodhd_sym, days=days)
    return {row["date"]: row["close"] for row in series}


def _collect_all_prices(spread: dict, days: int = 1825) -> dict:
    """
    Fetch prices for all symbols in a spread pair (long + short).
    Returns {symbol: {date: close}}.
    """
    all_symbols = spread["long"] + spread["short"]
    prices = {}
    for sym in all_symbols:
        log.info("Fetching price series for %s ...", sym)
        prices[sym] = _fetch_price_series(sym, days=days)
    return prices


def _get_common_dates(prices: dict) -> list:
    """Return sorted list of dates present in ALL price series."""
    if not prices:
        return []
    date_sets = [set(v.keys()) for v in prices.values()]
    common = date_sets[0]
    for s in date_sets[1:]:
        common &= s
    return sorted(common)


def compute_all_spread_stats() -> dict:
    """
    Compute 5yr regime-tagged spread return distributions for all 11 spreads.

    Steps:
    1. Load regime history from data/msi_history.json
    2. For each spread, fetch 5yr daily prices for every constituent
    3. For each day where regime is known, compute spread return
    4. Compute per-regime statistics
    5. Save results to data/spread_stats.json

    Returns the full results dict keyed by spread name -> regime stats.
    """
    regime_map = _load_regime_map()
    log.info("Loaded %d regime-tagged dates", len(regime_map))

    all_results = {}

    for spread in INDIA_SPREAD_PAIRS:
        name = spread["name"]
        log.info("Processing spread: %s", name)

        prices = _collect_all_prices(spread)

        if not prices:
            log.warning("No price data for spread '%s' — skipping", name)
            all_results[name] = {}
            continue

        all_dates = _get_common_dates(prices)
        if len(all_dates) < 2:
            log.warning("Insufficient dates for spread '%s' — skipping", name)
            all_results[name] = {}
            continue

        daily_data = []
        for i in range(1, len(all_dates)):
            prev_date = all_dates[i - 1]
            curr_date = all_dates[i]

            regime = regime_map.get(curr_date)
            if not regime:
                continue  # no regime tag for this date -> skip

            long_syms  = spread["long"]
            short_syms = spread["short"]

            long_prev  = {s: prices[s][prev_date] for s in long_syms  if prev_date in prices.get(s, {})}
            long_curr  = {s: prices[s][curr_date] for s in long_syms  if curr_date in prices.get(s, {})}
            short_prev = {s: prices[s][prev_date] for s in short_syms if prev_date in prices.get(s, {})}
            short_curr = {s: prices[s][curr_date] for s in short_syms if curr_date in prices.get(s, {})}

            if not long_prev or not short_prev:
                continue

            spread_ret = compute_spread_return(long_prev, long_curr, short_prev, short_curr)

            # Compute leg averages (for correlation check)
            def _avg_ret(prev_d, curr_d):
                rets = []
                for sym, p in prev_d.items():
                    if sym in curr_d and p > 0:
                        rets.append((curr_d[sym] - p) / p)
                return sum(rets) / len(rets) if rets else 0.0

            long_avg  = _avg_ret(long_prev, long_curr)
            short_avg = _avg_ret(short_prev, short_curr)

            daily_data.append({
                "date":          curr_date,
                "regime":        regime,
                "spread_return": spread_ret,
                "long_avg":      long_avg,
                "short_avg":     short_avg,
            })

        log.info("  %d regime-tagged days for '%s'", len(daily_data), name)

        if not daily_data:
            log.warning("No regime-tagged observations for spread '%s'", name)
            all_results[name] = {}
            continue

        all_results[name] = compute_regime_stats(daily_data)

    # Persist to disk
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w") as f:
        json.dump(all_results, f, indent=2)

    log.info("Saved spread stats to %s", _OUTPUT_FILE)
    return all_results


# =============================================================================
# LEGACY API — kept for backward compatibility with callers in signal_tracker.py
# These use the older 1-month window, not regime-tagged.
# =============================================================================

def _fetch_spread_history_legacy(pair: dict, period: str = "1mo") -> Optional[list]:
    """Legacy: fetch 1-month spread history as a list of daily floats (%)."""
    days = 30 if period == "1mo" else 60
    today = datetime.now(IST).date()
    date_range = [
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days + 15)
    ]

    closes: Dict[str, Dict[str, float]] = {}
    all_tickers = pair["long"] + pair["short"]
    for date_str in date_range:
        dump_file = DATA_DIR / "daily" / f"{date_str}.json"
        if not dump_file.exists():
            continue
        try:
            dump = json.loads(dump_file.read_text(encoding="utf-8"))
            day_closes: Dict[str, float] = {}
            for ticker in all_tickers:
                stock_data = dump.get("stocks", {}).get(ticker, {})
                close = stock_data.get("close") or stock_data.get("adjusted_close")
                if close:
                    day_closes[ticker] = float(close)
            if len(day_closes) == len(all_tickers):
                closes[date_str] = day_closes
        except Exception as e:
            log.warning("Failed to read dump %s: %s", date_str, e)

    ticker_counts = {t: sum(1 for d in closes.values() if t in d) for t in all_tickers}
    if any(cnt < 10 for cnt in ticker_counts.values()):
        log.info("Supplementing from EODHD for %s", pair["name"])
        for ticker in all_tickers:
            info = INDIA_SIGNAL_STOCKS.get(ticker, {})
            eodhd_sym = info.get("eodhd", "")
            if not eodhd_sym:
                continue
            series = fetch_eod_series(eodhd_sym, days=days + 15)
            for row in series:
                d = row["date"]
                if d not in closes:
                    closes[d] = {}
                closes[d][ticker] = row["close"]

    sorted_dates = sorted(d for d in closes if len(closes[d]) == len(all_tickers))
    if len(sorted_dates) < 5:
        return None

    spread_daily = []
    prev_closes: Dict[str, float] = {}
    for date_str in sorted_dates:
        day = closes[date_str]
        if not prev_closes:
            prev_closes = day
            continue
        long_rets  = [(day[t] / prev_closes[t] - 1) * 100 for t in pair["long"]
                      if t in day and t in prev_closes and prev_closes[t] > 0]
        short_rets = [(day[t] / prev_closes[t] - 1) * 100 for t in pair["short"]
                      if t in day and t in prev_closes and prev_closes[t] > 0]
        if long_rets and short_rets:
            spread_daily.append(
                sum(long_rets) / len(long_rets) - sum(short_rets) / len(short_rets)
            )
        prev_closes = day

    return spread_daily if len(spread_daily) >= 5 else None


def _empty_stats(name: str) -> Dict[str, Any]:
    return {
        "name": name, "n_days": 0, "computed_at": None,
        "daily_mean": 0, "daily_std": 0, "daily_min": 0, "daily_max": 0,
        "daily_p10": 0, "daily_p25": 0, "daily_p75": 0, "daily_p90": 0,
        "cum_current": 0, "cum_peak": 0, "cum_trough": 0, "cum_mean": 0,
        "cum_percentile": 50.0,
        "entry_level": 0, "stop_level": -1.0,
        "avg_favorable_move": 0, "worst_day": 0, "best_day": 0,
    }


def compute_spread_stats(pair: dict, period: str = "1mo") -> Dict[str, Any]:
    """Legacy: compute 1-month weighted stats for a single spread pair."""
    spread_daily_list = _fetch_spread_history_legacy(pair, period)
    if not spread_daily_list:
        return _empty_stats(pair["name"])

    vals = spread_daily_list
    n = len(vals)
    sorted_vals = sorted(vals)

    # Simple unweighted stats (numpy not required)
    mu = sum(vals) / n
    sig = math.sqrt(sum((v - mu) ** 2 for v in vals) / max(n - 1, 1))

    daily_min = sorted_vals[0]
    daily_max = sorted_vals[-1]
    daily_p10 = _percentile(sorted_vals, 10)
    daily_p25 = _percentile(sorted_vals, 25)
    daily_p75 = _percentile(sorted_vals, 75)
    daily_p90 = _percentile(sorted_vals, 90)

    cum = []
    c = 0.0
    for v in vals:
        c += v
        cum.append(c)
    cum_current = cum[-1]
    cum_peak    = max(cum)
    cum_trough  = min(cum)
    cum_mean    = sum(cum) / len(cum)
    cum_range   = cum_peak - cum_trough
    cum_percentile = (
        (cum_current - cum_trough) / cum_range * 100 if cum_range > 0 else 50.0
    )

    fav = [v for v in vals if v > 0]
    avg_favorable_move = sum(fav) / len(fav) if fav else sig
    stop_level = -(avg_favorable_move * 0.50)
    entry_level = cum_mean

    now_ist = datetime.now(IST)
    return {
        "name": pair["name"],
        "n_days": n,
        "computed_at": now_ist.isoformat(),
        "daily_mean":  round(mu, 4),
        "daily_std":   round(sig, 4),
        "daily_min":   round(daily_min, 4),
        "daily_max":   round(daily_max, 4),
        "daily_p10":   round(daily_p10, 4),
        "daily_p25":   round(daily_p25, 4),
        "daily_p75":   round(daily_p75, 4),
        "daily_p90":   round(daily_p90, 4),
        "cum_current": round(cum_current, 3),
        "cum_peak":    round(cum_peak, 3),
        "cum_trough":  round(cum_trough, 3),
        "cum_mean":    round(cum_mean, 3),
        "cum_percentile": round(cum_percentile, 1),
        "entry_level": round(entry_level, 3),
        "stop_level":  round(stop_level, 3),
        "avg_favorable_move": round(avg_favorable_move, 4),
        "worst_day":   round(daily_min, 4),
        "best_day":    round(daily_max, 4),
    }


def save_stats(stats: Dict[str, Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    log.info("Saved spread stats for %d pairs", len(stats))


def load_stats() -> Dict[str, Dict[str, Any]]:
    """Return cached spread stats, dropping any individual entry that is
    stale or missing a ``computed_at`` timestamp.

    A single bad entry must NOT invalidate the whole cache — that turned
    every signal cycle into a fresh EODHD recompute storm (one 502 from
    a single ticker would then hang the cycle for tens of minutes). The
    nightly aggregator and weekly recompute are responsible for keeping
    entries fresh; the hot read path stays fast.
    """
    if not STATS_FILE.exists():
        return {}
    try:
        stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}
    now = datetime.now(IST)
    fresh: Dict[str, Dict[str, Any]] = {}
    for name, s in stats.items():
        computed = s.get("computed_at")
        if not computed:
            continue
        try:
            ts = datetime.fromisoformat(computed)
            if (now - ts).total_seconds() > _CACHE_TTL_HOURS * 3600:
                continue
        except (ValueError, TypeError):
            continue
        fresh[name] = s
    return fresh


def get_spread_stats(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    if not force_refresh:
        cached = load_stats()
        if cached:
            return cached
    stats: Dict[str, Dict[str, Any]] = {}
    for pair in INDIA_SPREAD_PAIRS:
        s = compute_spread_stats(pair)
        stats[pair["name"]] = s
    save_stats(stats)
    return stats


def get_levels_for_spread(spread_name: str) -> Dict[str, float]:
    stats = get_spread_stats()
    s = stats.get(spread_name, {})
    if not s or s.get("n_days", 0) < 5:
        return {
            "entry_level": 0.0, "stop_level": -1.5, "daily_std": 2.0,
            "avg_favorable_move": 2.0, "cum_percentile": 50.0,
            "cum_peak": 5.0, "cum_trough": -2.0,
        }
    return {
        "entry_level": s["entry_level"], "stop_level": s["stop_level"],
        "daily_std": s["daily_std"], "avg_favorable_move": s["avg_favorable_move"],
        "cum_percentile": s.get("cum_percentile", 50.0),
        "cum_peak": s.get("cum_peak", 5.0), "cum_trough": s.get("cum_trough", -2.0),
    }


def classify_entry_zone(spread_name: str, current_spread_pnl: float) -> Dict[str, Any]:
    levels = get_levels_for_spread(spread_name)
    entry     = levels["entry_level"]
    stop      = levels["stop_level"]
    daily_std = levels["daily_std"]
    cum_peak  = levels["cum_peak"]
    cum_trough = levels["cum_trough"]

    distance = current_spread_pnl - entry
    cum_range = cum_peak - cum_trough
    percentile = (
        max(0.0, min(100.0, (current_spread_pnl - cum_trough) / cum_range * 100))
        if cum_range > 0 else 50.0
    )

    if distance <= daily_std:
        zone = "ENTER"
        reason = (f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
                  f"-- at fair value, data supports entry")
    elif distance <= daily_std * 2:
        zone = "PARTIAL"
        reason = (f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
                  f"-- extended, half position recommended")
    else:
        zone = "WAIT"
        reason = (f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
                  f"-- too far from fair value, wait for pullback")

    def _ordinal(n: float) -> str:
        n = int(n)
        suf = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"

    percentile_warning = None
    if percentile >= 80:
        percentile_warning = (
            f"You are entering at the {_ordinal(percentile)} percentile of the "
            f"1-month spread range ({cum_trough:+.2f}% to {cum_peak:+.2f}%). "
            f"This is a momentum trade -- daily stop protects you if it reverses."
        )

    return {
        "zone": zone, "reason": reason,
        "entry_level": round(entry, 2), "stop_level": round(stop, 2),
        "distance_from_entry": round(distance, 2), "daily_std": round(daily_std, 2),
        "percentile": round(percentile, 1), "percentile_warning": percentile_warning,
    }


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s -- %(message)s",
        datefmt="%H:%M:%S",
    )
    results = compute_all_spread_stats()
    spreads_computed = sum(1 for v in results.values() if v)
    print(f"\nDone. {spreads_computed}/{len(results)} spreads have regime stats.")
    for spread_name, regimes in results.items():
        if regimes:
            summary = {r: f"n={s['count']}, mean={s['mean']:.4f}" for r, s in regimes.items()}
            print(f"  {spread_name}: {summary}")
        else:
            print(f"  {spread_name}: no data")
