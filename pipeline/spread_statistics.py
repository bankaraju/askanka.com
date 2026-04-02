"""
Anka Research Pipeline -- Data-Driven Spread Statistics
Computes 1-month spread distribution for each pair to derive entry and stop levels.

All trading parameters are derived from actual market data, never arbitrary percentages.
Weekly weighted average: last week gets 4x weight, week before 3x, etc.
Winners run until stopped — no target exit, no trailing stop, no expiry.

Framework:
  - Entry level:  Weekly-weighted 1-month average cumulative spread = "fair value"
  - Daily stop:   50% of weighted avg daily favorable move, on the wrong side
  - 2-day stop:   daily_std² × 50% — fires on 2 consecutive losing days
  - Percentile zone: warns late entrants if spread is in top 20% of 1-month range
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from config import INDIA_SIGNAL_STOCKS, INDIA_SPREAD_PAIRS

log = logging.getLogger("anka.spread_stats")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
STATS_FILE = DATA_DIR / "spread_stats.json"

# Cache duration: recompute once per trading day
_CACHE_TTL_HOURS = 12


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _fetch_spread_history(pair: dict, period: str = "1mo") -> Optional[pd.Series]:
    """Compute daily spread return series using saved daily dump files.

    Priority:
      1. Read data/daily/YYYY-MM-DD.json files (already fetched by EODHD nightly dump)
      2. Fill missing dates from EODHD EOD API
      3. Last resort: yfinance download (with parquet disabled)

    Spread = avg(long leg daily returns %) - avg(short leg daily returns %)
    Returns a Series of daily spread differentials, or None if insufficient data.
    """
    import json

    # Determine date range: 1mo ≈ 30 calendar days
    days = 30 if period == "1mo" else 60
    today = datetime.now(IST).date()
    date_range = [
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days + 15)  # +15 buffer for weekends/holidays
    ]

    # ── 1. Load from saved daily dump files ───────────────────────────────
    closes: dict[str, dict[str, float]] = {}  # {date: {ticker: close}}

    all_tickers = pair["long"] + pair["short"]
    for date_str in date_range:
        dump_file = DATA_DIR / "daily" / f"{date_str}.json"
        if not dump_file.exists():
            continue
        try:
            dump = json.loads(dump_file.read_text(encoding="utf-8"))
            day_closes: dict[str, float] = {}
            for ticker in all_tickers:
                stock_data = dump.get("stocks", {}).get(ticker, {})
                close = stock_data.get("close") or stock_data.get("adjusted_close")
                if close:
                    day_closes[ticker] = float(close)
            if len(day_closes) == len(all_tickers):  # only include days with full data
                closes[date_str] = day_closes
        except Exception as e:
            log.warning("Failed to read dump %s: %s", date_str, e)

    # ── 2. Gap-fill from EODHD EOD API for tickers with missing days ──────
    # Gap-fill if any ticker has fewer than 10 trading-day records in the dumps
    ticker_counts = {t: sum(1 for d in closes.values() if t in d) for t in all_tickers}
    if any(cnt < 10 for cnt in ticker_counts.values()):
        log.info("Insufficient dump data for %s (%d days), supplementing from EODHD", pair["name"], len(closes))
        from eodhd_client import fetch_eod_series
        from config import INDIA_SIGNAL_STOCKS
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

    # ── 3. Last resort: yfinance (parquet disabled via environment variable) ──
    ticker_counts = {t: sum(1 for d in closes.values() if t in d) for t in all_tickers}
    if any(cnt < 10 for cnt in ticker_counts.values()):
        log.warning("EODHD data thin for %s, falling back to yfinance", pair["name"])
        from config import INDIA_SIGNAL_STOCKS
        import os
        os.environ["YFINANCE_CACHE_DISABLED"] = "1"  # suppress parquet cache
        try:
            yf_tickers = {t: INDIA_SIGNAL_STOCKS.get(t, {}).get("yf", f"{t}.NS") for t in all_tickers}
            ticker_str = " ".join(yf_tickers.values())
            data = yf.download(ticker_str, period=period, interval="1d",
                               progress=False, auto_adjust=True)
            if not data.empty:
                close_df = data["Close"] if "Close" in data else data
                for date_val, row in close_df.iterrows():
                    d = date_val.strftime("%Y-%m-%d")
                    if d not in closes:
                        closes[d] = {}
                    for ticker, yf_sym in yf_tickers.items():
                        col = yf_sym if yf_sym in close_df.columns else None
                        if col and not pd.isna(row.get(col)):
                            closes[d][ticker] = float(row[col])
        except Exception as e:
            log.error("yfinance fallback failed for %s: %s", pair["name"], e)

    # ── Build spread series ────────────────────────────────────────────────
    sorted_dates = sorted(d for d in closes if len(closes[d]) == len(all_tickers))
    if len(sorted_dates) < 5:
        log.warning("Insufficient complete-data days for %s: %d", pair["name"], len(sorted_dates))
        return None

    spread_daily = []
    prev_closes: dict[str, float] = {}

    for date_str in sorted_dates:
        day = closes[date_str]
        if not prev_closes:
            prev_closes = day
            continue
        long_rets  = [(day[t] / prev_closes[t] - 1) * 100 for t in pair["long"]  if t in day and t in prev_closes and prev_closes[t] > 0]
        short_rets = [(day[t] / prev_closes[t] - 1) * 100 for t in pair["short"] if t in day and t in prev_closes and prev_closes[t] > 0]
        if long_rets and short_rets:
            spread_daily.append(sum(long_rets) / len(long_rets) - sum(short_rets) / len(short_rets))
        prev_closes = day

    if len(spread_daily) < 5:
        log.warning("Too few spread observations for %s: %d", pair["name"], len(spread_daily))
        return None

    return pd.Series(spread_daily, dtype=float)


def _build_weekly_weights(spread_daily: pd.Series) -> np.ndarray:
    """Assign recency weights: last week = 4x, week before = 3x, etc.

    For a ~22-day month: days 1-5 get weight 1, 6-10 get 2, 11-15 get 3, 16+ get 4.
    This makes recent market behavior dominate stop/entry calculations.
    """
    n = len(spread_daily)
    week_size = max(n // 4, 1)
    weights = np.ones(n)
    for i in range(n):
        week_num = min(i // week_size, 3)  # 0,1,2,3
        weights[i] = week_num + 1           # 1,2,3,4
    # Normalize so weights sum to n (preserves scale of weighted mean)
    weights = weights * (n / weights.sum())
    return weights


def compute_spread_stats(pair: dict, period: str = "1mo") -> Dict[str, Any]:
    """Compute full statistical profile for a single spread pair.

    Uses weekly weighted average: last week gets highest weight (4x),
    making stops and entry levels more responsive to recent conditions.

    Returns dict with:
        name, daily_mean, daily_std, daily_min, daily_max,
        daily_p10, daily_p25, daily_p75, daily_p90,
        cum_current, cum_peak, cum_trough, cum_mean,
        entry_level, stop_level, cum_percentile,
        n_days, computed_at
    """
    spread_daily = _fetch_spread_history(pair, period)

    if spread_daily is None or len(spread_daily) < 5:
        log.warning("Insufficient data for %s", pair["name"])
        return _empty_stats(pair["name"])

    spread_cumulative = spread_daily.cumsum()
    weights = _build_weekly_weights(spread_daily)

    # Daily distribution (unweighted — these are descriptive)
    daily_min = float(spread_daily.min())
    daily_max = float(spread_daily.max())
    daily_p10 = float(spread_daily.quantile(0.10))
    daily_p25 = float(spread_daily.quantile(0.25))
    daily_p75 = float(spread_daily.quantile(0.75))
    daily_p90 = float(spread_daily.quantile(0.90))

    # Weighted daily mean and std (these drive stop levels)
    vals = spread_daily.values
    daily_mean = float(np.average(vals, weights=weights))
    daily_std = float(np.sqrt(np.average((vals - daily_mean) ** 2, weights=weights)))

    # Cumulative distribution
    cum_current = float(spread_cumulative.iloc[-1])
    cum_peak = float(spread_cumulative.max())
    cum_trough = float(spread_cumulative.min())

    # Weighted cumulative mean (entry level)
    cum_weights = _build_weekly_weights(spread_cumulative)
    cum_mean = float(np.average(spread_cumulative.values, weights=cum_weights))

    # Percentile: where does current cumulative sit in the 1-month range?
    cum_range = cum_peak - cum_trough
    if cum_range > 0:
        cum_percentile = float((cum_current - cum_trough) / cum_range * 100)
    else:
        cum_percentile = 50.0

    # --- DATA-DRIVEN LEVELS (stops-only, no target exit) ---

    # 1. ENTRY LEVEL: weekly-weighted 1-month avg cumulative spread = fair value
    entry_level = cum_mean

    # 2. DAILY STOP: 50% of weighted avg daily favorable move, wrong side
    #    "favorable" = positive spread days (our direction)
    fav_mask = spread_daily > 0
    if fav_mask.any():
        fav_vals = vals[fav_mask]
        fav_weights = weights[fav_mask]
        fav_weights = fav_weights * (len(fav_vals) / fav_weights.sum())
        avg_favorable_move = float(np.average(fav_vals, weights=fav_weights))
    else:
        avg_favorable_move = daily_std
    stop_level = -(avg_favorable_move * 0.50)

    # 3. Context: worst/best day for risk framing
    worst_day = daily_min
    best_day = daily_max

    now_ist = datetime.now(IST)

    return {
        "name": pair["name"],
        "n_days": len(spread_daily),
        "computed_at": now_ist.isoformat(),
        # Daily distribution
        "daily_mean": round(daily_mean, 4),
        "daily_std": round(daily_std, 4),
        "daily_min": round(daily_min, 4),
        "daily_max": round(daily_max, 4),
        "daily_p10": round(daily_p10, 4),
        "daily_p25": round(daily_p25, 4),
        "daily_p75": round(daily_p75, 4),
        "daily_p90": round(daily_p90, 4),
        # Cumulative
        "cum_current": round(cum_current, 3),
        "cum_peak": round(cum_peak, 3),
        "cum_trough": round(cum_trough, 3),
        "cum_mean": round(cum_mean, 3),
        "cum_percentile": round(cum_percentile, 1),
        # Data-driven levels (stops-only)
        "entry_level": round(entry_level, 3),
        "stop_level": round(stop_level, 3),
        # Context
        "avg_favorable_move": round(avg_favorable_move, 4),
        "worst_day": round(worst_day, 4),
        "best_day": round(best_day, 4),
    }


def _empty_stats(name: str) -> Dict[str, Any]:
    """Return a safe empty stats dict when data is unavailable."""
    return {
        "name": name, "n_days": 0, "computed_at": None,
        "daily_mean": 0, "daily_std": 0, "daily_min": 0, "daily_max": 0,
        "daily_p10": 0, "daily_p25": 0, "daily_p75": 0, "daily_p90": 0,
        "cum_current": 0, "cum_peak": 0, "cum_trough": 0, "cum_mean": 0,
        "cum_percentile": 50.0,
        "entry_level": 0, "stop_level": -1.0,
        "avg_favorable_move": 0, "worst_day": 0, "best_day": 0,
    }


# ---------------------------------------------------------------------------
# Batch computation + caching
# ---------------------------------------------------------------------------

def compute_all_spread_stats(period: str = "1mo") -> Dict[str, Dict[str, Any]]:
    """Compute stats for all configured spread pairs. Returns {name: stats}."""
    all_stats = {}
    for pair in INDIA_SPREAD_PAIRS:
        stats = compute_spread_stats(pair, period)
        all_stats[pair["name"]] = stats
        log.info(
            "%s: entry=%.2f%% stop=%.2f%% percentile=%.0f%%",
            pair["name"], stats["entry_level"], stats["stop_level"], stats.get("cum_percentile", 50),
        )
    return all_stats


def save_stats(stats: Dict[str, Dict[str, Any]]) -> None:
    """Cache computed stats to JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(
        json.dumps(stats, indent=2, default=str), encoding="utf-8"
    )
    log.info("Saved spread stats for %d pairs", len(stats))


def load_stats() -> Dict[str, Dict[str, Any]]:
    """Load cached stats. Returns empty dict if stale or missing."""
    if not STATS_FILE.exists():
        return {}
    try:
        stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}

    # Check staleness: any entry older than _CACHE_TTL_HOURS
    now = datetime.now(IST)
    for name, s in stats.items():
        computed = s.get("computed_at")
        if not computed:
            return {}
        try:
            ts = datetime.fromisoformat(computed)
            if (now - ts).total_seconds() > _CACHE_TTL_HOURS * 3600:
                log.info("Stats for %s are stale, recomputing", name)
                return {}
        except (ValueError, TypeError):
            return {}

    return stats


def get_spread_stats(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """Get stats for all spreads (cached or fresh)."""
    if not force_refresh:
        cached = load_stats()
        if cached:
            return cached

    stats = compute_all_spread_stats()
    save_stats(stats)
    return stats


def get_levels_for_spread(spread_name: str) -> Dict[str, float]:
    """Quick accessor: get entry/stop levels for a named spread.

    Returns dict with keys: entry_level, stop_level, daily_std,
    avg_favorable_move, cum_percentile, cum_peak, cum_trough.
    Falls back to conservative defaults if data unavailable.
    """
    stats = get_spread_stats()
    s = stats.get(spread_name, {})

    if not s or s.get("n_days", 0) < 5:
        return {
            "entry_level": 0.0,
            "stop_level": -1.5,
            "daily_std": 2.0,
            "avg_favorable_move": 2.0,
            "cum_percentile": 50.0,
            "cum_peak": 5.0,
            "cum_trough": -2.0,
        }

    return {
        "entry_level": s["entry_level"],
        "stop_level": s["stop_level"],
        "daily_std": s["daily_std"],
        "avg_favorable_move": s["avg_favorable_move"],
        "cum_percentile": s.get("cum_percentile", 50.0),
        "cum_peak": s.get("cum_peak", 5.0),
        "cum_trough": s.get("cum_trough", -2.0),
    }


# ---------------------------------------------------------------------------
# Entry zone classification (for Telegram guidance)
# ---------------------------------------------------------------------------

def classify_entry_zone(
    spread_name: str,
    current_spread_pnl: float,
) -> Dict[str, Any]:
    """Classify whether a spread is in entry zone, based on 1-month data.

    Uses weekly-weighted statistics. Computes where the current spread
    sits in the 1-month cumulative range (0-100 percentile) and warns
    late entrants if they're in the top 20% of the range.

    Returns dict with:
        zone: "ENTER" | "PARTIAL" | "WAIT"
        reason: human-readable explanation
        entry_level: the weighted 1-month mean (fair value)
        distance_from_entry: how far current spread is from fair value
        stop_level: data-driven daily stop
        percentile: where current spread sits in 1-month range (0-100)
        percentile_warning: disclaimer text for late entrants (or None)
    """
    levels = get_levels_for_spread(spread_name)
    entry = levels["entry_level"]
    stop = levels["stop_level"]
    daily_std = levels["daily_std"]
    cum_peak = levels["cum_peak"]
    cum_trough = levels["cum_trough"]

    # Distance from the weighted 1-month mean (entry level)
    distance = current_spread_pnl - entry

    # Percentile: where does current spread sit in 1-month range?
    cum_range = cum_peak - cum_trough
    if cum_range > 0:
        percentile = (current_spread_pnl - cum_trough) / cum_range * 100
        percentile = max(0.0, min(100.0, percentile))
    else:
        percentile = 50.0

    # Entry zone: within 1 daily std of the mean
    if distance <= daily_std:
        zone = "ENTER"
        reason = (
            f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
            f"-- at fair value, data supports entry"
        )
    # Partial: between 1-2 daily stds above mean
    elif distance <= daily_std * 2:
        zone = "PARTIAL"
        reason = (
            f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
            f"-- extended, half position recommended"
        )
    # Wait: more than 2 daily stds above mean
    else:
        zone = "WAIT"
        reason = (
            f"Spread at {current_spread_pnl:+.2f}% vs 1mo avg {entry:+.2f}% "
            f"-- too far from fair value, wait for pullback"
        )

    # Percentile warning for late entrants (top 20% of 1-month range)
    def _ordinal(n: float) -> str:
        n = int(n)
        suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    percentile_warning = None
    if percentile >= 80:
        percentile_warning = (
            f"You are entering at the {_ordinal(percentile)} percentile of the "
            f"1-month spread range ({cum_trough:+.2f}% to {cum_peak:+.2f}%). "
            f"This is a momentum trade -- daily stop protects you if it reverses."
        )

    return {
        "zone": zone,
        "reason": reason,
        "entry_level": round(entry, 2),
        "stop_level": round(stop, 2),
        "distance_from_entry": round(distance, 2),
        "daily_std": round(daily_std, 2),
        "percentile": round(percentile, 1),
        "percentile_warning": percentile_warning,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    force = "--refresh" in sys.argv
    stats = get_spread_stats(force_refresh=force)

    print("=" * 70)
    print("DATA-DRIVEN SPREAD LEVELS")
    print("=" * 70)

    for name, s in stats.items():
        if s.get("n_days", 0) == 0:
            print(f"\n{name}: NO DATA")
            continue
        print(f"\n{name} ({s['n_days']} days):")
        print(f"  Daily: mean {s['daily_mean']:+.3f}%  std {s['daily_std']:.3f}%  "
              f"range [{s['daily_min']:+.3f}%, {s['daily_max']:+.3f}%]")
        print(f"  1mo cumulative: current {s['cum_current']:+.2f}%  "
              f"peak {s['cum_peak']:+.2f}%  trough {s['cum_trough']:+.2f}%")
        print(f"  Percentile (current in 1mo range): {s.get('cum_percentile', 50):.0f}%")
        print(f"  --- LEVELS (weekly-weighted) ---")
        print(f"  Entry (weighted 1mo mean):  {s['entry_level']:+.2f}%")
        print(f"  Daily stop (50% fav move):  {s['stop_level']:+.2f}%")
        print(f"  2-day stop (std^2 x 50%):   {-(s['daily_std']**2 * 0.50):+.2f}%")
