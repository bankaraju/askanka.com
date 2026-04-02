"""
Anka Research Pipeline -- Asian Market Correlation Engine
Data-driven cross-market correlations replacing hard-coded cascade rules.

Fetches 1 year of daily OHLCV for Asian indices, Asian defence stocks,
commodities, FX, and Indian signal stocks.  Computes Pearson correlations
and conditional-move statistics (median response, hit rate, sample size)
for a configurable set of return thresholds.

Results are cached in data/asian_correlation_cache.json and refreshed
every 24 hours.  A briefing generator checks today's Asian moves against
historical thresholds and formats actionable output for Telegram.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from config import INDIA_SIGNAL_STOCKS, ASIA_DEFENCE_STOCKS, ASIA_INDICES

logger = logging.getLogger("anka.asian_correlation")

DATA_DIR = Path(__file__).parent / "data"
CACHE_FILE = DATA_DIR / "asian_correlation_cache.json"
HIST_DIR = DATA_DIR / "asian_historical"

CORRELATION_CACHE_HOURS = 24
CORRELATION_MIN_EVENTS = 5   # minimum sample for reporting
CORRELATION_THRESHOLDS = [-5.0, -3.0, -2.0, 2.0, 3.0, 5.0]

# ---------------------------------------------------------------------------
# Asian tickers to track (indices + defence + commodities + FX)
# ---------------------------------------------------------------------------
ASIAN_TICKERS: Dict[str, str] = {
    "Nikkei":   "^N225",
    "KOSPI":    "^KS11",
    "ASX":      "^AXJO",
    "STI":      "^STI",
    "Kawasaki": "7012.T",
    "MHI":      "7011.T",
    "Hanwha":   "012450.KS",
    "ST_Eng":   "S63.SI",
    "Brent":    "BZ=F",
    "Gold":     "GC=F",
    "USDINR":   "INR=X",
}

# Indian tickers (must match config.INDIA_SIGNAL_STOCKS keys where needed)
INDIA_TICKERS: Dict[str, str] = {
    "HAL":       "HAL.NS",
    "BEL":       "BEL.NS",
    "BDL":       "BDL.NS",
    "ONGC":      "ONGC.NS",
    "OIL":       "OIL.NS",
    "RELIANCE":  "RELIANCE.NS",
    "COALINDIA": "COALINDIA.NS",
    "TCS":       "TCS.NS",
    "INFY":      "INFY.NS",
    "WIPRO":     "WIPRO.NS",
    "IOC":       "IOC.NS",
    "HPCL":      "HINDPETRO.NS",
    "BPCL":      "BPCL.NS",
}

# Sector groupings for aggregate view
SECTOR_MAP: Dict[str, Dict[str, List[str]]] = {
    "Defence_India": {
        "tickers": ["HAL", "BEL", "BDL"],
        "label": "Indian Defence",
    },
    "Defence_Asia": {
        "tickers": ["Kawasaki", "MHI", "Hanwha"],
        "label": "Asian Defence",
    },
    "Energy_Upstream": {
        "tickers": ["ONGC", "OIL"],
        "label": "Upstream Energy",
    },
    "Energy_Downstream": {
        "tickers": ["IOC", "BPCL", "HPCL"],
        "label": "Downstream OMCs",
    },
    "IT_Services": {
        "tickers": ["TCS", "INFY", "WIPRO"],
        "label": "IT Services",
    },
}


# =========================================================================
#  Data Fetching
# =========================================================================

def _ensure_dirs() -> None:
    """Create data directories if they do not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HIST_DIR.mkdir(parents=True, exist_ok=True)


def fetch_historical(tickers_map: Dict[str, str], days: int = 365) -> pd.DataFrame:
    """Download daily close prices for *tickers_map*, compute daily returns.

    Parameters
    ----------
    tickers_map : dict
        ``{friendly_name: yfinance_symbol}``
    days : int
        Look-back window in calendar days.

    Returns
    -------
    pd.DataFrame
        Daily **percentage returns** indexed by date (tz-naive), columns = friendly names.
    """
    _ensure_dirs()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    all_close: Dict[str, pd.Series] = {}

    for name, symbol in tickers_map.items():
        cache_path = HIST_DIR / f"{name}_close.parquet"
        # Try parquet cache first (avoids redundant yfinance calls within a day)
        if cache_path.exists():
            age_hours = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 3600
            if age_hours < CORRELATION_CACHE_HOURS:
                try:
                    cached = pd.read_parquet(cache_path)
                    all_close[name] = cached.squeeze()
                    logger.debug("Loaded cached close for %s (%d rows)", name, len(cached))
                    continue
                except Exception:
                    logger.warning("Corrupt parquet cache for %s, re-downloading", name)

        logger.info("Fetching %s (%s) from yfinance ...", name, symbol)
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_str, end=end_str, auto_adjust=True)
            if hist.empty:
                logger.warning("No data returned for %s (%s) -- skipping", name, symbol)
                continue
            close = hist["Close"].dropna()
            close.index = close.index.tz_localize(None)  # normalize to tz-naive
            close.name = name
            # Persist
            close.to_frame().to_parquet(cache_path)
            all_close[name] = close
            logger.info("Fetched %s: %d rows", name, len(close))
        except Exception as exc:
            logger.error("yfinance fetch failed for %s (%s): %s", name, symbol, exc)
            continue

    if not all_close:
        logger.error("No historical data fetched at all -- returning empty DataFrame")
        return pd.DataFrame()

    prices = pd.DataFrame(all_close)
    # Daily pct change -- drop the first row (NaN)
    returns = prices.pct_change().iloc[1:] * 100.0  # percentage
    logger.info("Historical returns shape: %s", returns.shape)
    return returns


# =========================================================================
#  Date Alignment
# =========================================================================

def _align_dates(asian_returns: pd.DataFrame, india_returns: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Restrict both frames to the **intersection** of their date indices (same-day only)."""
    common = asian_returns.index.intersection(india_returns.index)
    if common.empty:
        logger.warning("No overlapping dates between Asian and Indian returns")
    else:
        logger.info("Aligned on %d common trading days", len(common))
    return asian_returns.loc[common], india_returns.loc[common]


# =========================================================================
#  Pearson Correlation Matrix
# =========================================================================

def build_correlation_matrix(asian_returns: pd.DataFrame, india_returns: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation: Asian ticker daily return <-> Indian ticker daily return.

    Returns
    -------
    pd.DataFrame
        Rows = Asian tickers, Columns = Indian tickers, values = correlation.
    """
    asian_aligned, india_aligned = _align_dates(asian_returns, india_returns)
    if asian_aligned.empty or india_aligned.empty:
        logger.warning("Cannot build correlation matrix -- no overlapping data")
        return pd.DataFrame()

    combined = pd.concat([asian_aligned, india_aligned], axis=1)
    full_corr = combined.corr()
    # Slice: rows = asian cols, columns = india cols
    matrix = full_corr.loc[asian_aligned.columns, india_aligned.columns]
    logger.info("Correlation matrix built: %s", matrix.shape)
    return matrix


# =========================================================================
#  Conditional Moves
# =========================================================================

def compute_conditional_moves(
    asian_returns: pd.DataFrame,
    india_returns: pd.DataFrame,
) -> Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]:
    """For each threshold, filter days where an Asian ticker breached it and
    compute how each Indian ticker responded.

    Returns
    -------
    dict
        ``{asian_name: {threshold_str: {india_name: {median, hit_rate, n}}}}``

    ``hit_rate`` = fraction of days the Indian ticker moved in the **same
    direction** as the threshold (positive if threshold > 0, negative if < 0).
    """
    asian_aligned, india_aligned = _align_dates(asian_returns, india_returns)
    if asian_aligned.empty or india_aligned.empty:
        logger.warning("Cannot compute conditional moves -- no overlapping data")
        return {}

    results: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}

    for asian_name in asian_aligned.columns:
        results[asian_name] = {}
        asian_col = asian_aligned[asian_name].dropna()

        for threshold in CORRELATION_THRESHOLDS:
            thr_key = f"{threshold:+.1f}%"
            results[asian_name][thr_key] = {}

            if threshold > 0:
                mask = asian_col >= threshold
            else:
                mask = asian_col <= threshold

            breach_dates = asian_col[mask].index
            n_events = len(breach_dates)

            for india_name in india_aligned.columns:
                india_col = india_aligned[india_name]
                # Get Indian returns on breach dates (only where data exists)
                india_on_breach = india_col.reindex(breach_dates).dropna()
                n = len(india_on_breach)

                if n < CORRELATION_MIN_EVENTS:
                    results[asian_name][thr_key][india_name] = {
                        "median": None,
                        "hit_rate": None,
                        "n": n,
                    }
                    continue

                median_response = float(india_on_breach.median())

                # Hit rate: same direction as threshold
                if threshold > 0:
                    hits = (india_on_breach > 0).sum()
                else:
                    hits = (india_on_breach < 0).sum()
                hit_rate = float(hits / n) if n > 0 else 0.0

                results[asian_name][thr_key][india_name] = {
                    "median": round(median_response, 3),
                    "hit_rate": round(hit_rate, 3),
                    "n": int(n),
                }

        logger.debug("Conditional moves computed for %s", asian_name)

    return results


# =========================================================================
#  Sector-Level Correlations
# =========================================================================

def get_sector_correlations() -> Dict[str, Any]:
    """Aggregate stock-level correlations into sector-level view.

    Sector pairs computed:
        - Indian Defence (HAL+BEL+BDL avg) vs Asian Defence (Kawasaki+MHI+Hanwha avg)
        - Energy Upstream (ONGC+OIL) vs Brent
        - IT Services (TCS+INFY+WIPRO) vs broad Asian indices (Nikkei, KOSPI, ASX)
        - Downstream OMCs (IOC+BPCL+HPCL) vs Brent (expecting inverse)

    Returns
    -------
    dict
        ``{pair_label: {correlation: float, conditional_moves: dict}}``
    """
    data = load_or_build_correlations()
    corr_matrix = data.get("correlation_matrix")
    cond_moves = data.get("conditional_moves")
    if not corr_matrix or not cond_moves:
        logger.warning("No correlation data available for sector aggregation")
        return {}

    corr_df = pd.DataFrame(corr_matrix)

    sector_results: Dict[str, Any] = {}

    # 1) Indian Defence vs Asian Defence
    india_def = ["HAL", "BEL", "BDL"]
    asia_def = ["Kawasaki", "MHI", "Hanwha"]
    sector_results["Defence_India_vs_Asia"] = _sector_pair_stats(
        corr_df, cond_moves, asia_def, india_def, "Indian Defence vs Asian Defence"
    )

    # 2) Upstream vs Brent
    upstream = ["ONGC", "OIL"]
    sector_results["Upstream_vs_Brent"] = _sector_pair_stats(
        corr_df, cond_moves, ["Brent"], upstream, "Upstream Energy vs Brent"
    )

    # 3) IT vs broad Asian
    it_stocks = ["TCS", "INFY", "WIPRO"]
    broad_asia = ["Nikkei", "KOSPI", "ASX"]
    sector_results["IT_vs_Asia_Broad"] = _sector_pair_stats(
        corr_df, cond_moves, broad_asia, it_stocks, "IT Services vs Asian Indices"
    )

    # 4) Downstream vs Brent (expect inverse)
    downstream = ["IOC", "BPCL", "HPCL"]
    sector_results["Downstream_vs_Brent"] = _sector_pair_stats(
        corr_df, cond_moves, ["Brent"], downstream, "Downstream OMCs vs Brent"
    )

    return sector_results


def _sector_pair_stats(
    corr_df: pd.DataFrame,
    cond_moves: dict,
    asian_names: List[str],
    india_names: List[str],
    label: str,
) -> Dict[str, Any]:
    """Helper: average correlation and conditional moves for a sector pair."""
    # Average correlation across the grid of (asian, india) pairs
    corr_vals = []
    for a in asian_names:
        for i in india_names:
            try:
                val = corr_df.loc[a, i]
                if pd.notna(val):
                    corr_vals.append(float(val))
            except KeyError:
                continue

    avg_corr = round(float(np.mean(corr_vals)), 4) if corr_vals else None

    # Aggregate conditional moves: average median, average hit_rate across pairs
    agg_cond: Dict[str, Dict[str, Any]] = {}
    for thr in [f"{t:+.1f}%" for t in CORRELATION_THRESHOLDS]:
        medians = []
        hit_rates = []
        ns = []
        for a in asian_names:
            if a not in cond_moves:
                continue
            if thr not in cond_moves[a]:
                continue
            for i in india_names:
                entry = cond_moves[a][thr].get(i, {})
                if entry.get("median") is not None:
                    medians.append(entry["median"])
                    hit_rates.append(entry["hit_rate"])
                    ns.append(entry["n"])

        if medians:
            agg_cond[thr] = {
                "avg_median": round(float(np.mean(medians)), 3),
                "avg_hit_rate": round(float(np.mean(hit_rates)), 3),
                "total_n": int(np.sum(ns)),
            }

    return {
        "label": label,
        "correlation": avg_corr,
        "conditional_moves": agg_cond,
    }


# =========================================================================
#  Cache Management
# =========================================================================

def _is_cache_fresh() -> bool:
    """Return True if cache exists and is younger than CORRELATION_CACHE_HOURS."""
    if not CACHE_FILE.exists():
        return False
    age_hours = (datetime.now().timestamp() - CACHE_FILE.stat().st_mtime) / 3600
    return age_hours < CORRELATION_CACHE_HOURS


def _save_cache(payload: dict) -> None:
    """Write correlation payload to JSON cache."""
    _ensure_dirs()
    payload["cached_at"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        logger.info("Correlation cache saved to %s", CACHE_FILE)
    except Exception as exc:
        logger.error("Failed to save cache: %s", exc)


def _load_cache() -> Optional[dict]:
    """Read correlation cache from disk."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load cache: %s", exc)
        return None


# =========================================================================
#  Orchestrator
# =========================================================================

def load_or_build_correlations(force_refresh: bool = False) -> dict:
    """Load from cache if fresh, otherwise build from scratch and cache.

    Returns
    -------
    dict
        Keys: ``correlation_matrix``, ``conditional_moves``, ``cached_at``.
    """
    if not force_refresh and _is_cache_fresh():
        cached = _load_cache()
        if cached:
            logger.info("Using cached correlations from %s", cached.get("cached_at", "?"))
            return cached

    logger.info("Building correlations from scratch ...")
    asian_returns = fetch_historical(ASIAN_TICKERS, days=365)
    india_returns = fetch_historical(INDIA_TICKERS, days=365)

    if asian_returns.empty or india_returns.empty:
        logger.error("Insufficient data to build correlations")
        return {"correlation_matrix": {}, "conditional_moves": {}, "cached_at": None}

    corr_matrix = build_correlation_matrix(asian_returns, india_returns)
    cond_moves = compute_conditional_moves(asian_returns, india_returns)

    payload = {
        "correlation_matrix": corr_matrix.to_dict() if not corr_matrix.empty else {},
        "conditional_moves": cond_moves,
    }
    _save_cache(payload)
    return payload


# =========================================================================
#  Today's Briefing
# =========================================================================

def _fetch_today_asian_moves() -> Dict[str, float]:
    """Fetch the latest available daily return for each Asian ticker.

    Uses a 5-day window to find the most recent trading day's return.
    """
    moves: Dict[str, float] = {}
    for name, symbol in ASIAN_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", auto_adjust=True)
            if hist.empty or len(hist) < 2:
                logger.warning("Not enough recent data for %s", name)
                continue
            close = hist["Close"].dropna()
            if len(close) < 2:
                continue
            pct_change = (close.iloc[-1] / close.iloc[-2] - 1) * 100.0
            moves[name] = round(float(pct_change), 2)
        except Exception as exc:
            logger.error("Failed to fetch today's move for %s: %s", name, exc)
    return moves


def generate_correlation_briefing(today_asian_data: Optional[Dict[str, float]] = None) -> str:
    """Check which Asian tickers are breaching thresholds TODAY.
    Look up historical Indian responses.  Format as table for Telegram.

    Parameters
    ----------
    today_asian_data : dict, optional
        ``{asian_name: pct_change_today}``.  If None, fetches live data.

    Returns
    -------
    str
        Formatted briefing text (monospace-friendly for Telegram).
    """
    if today_asian_data is None:
        today_asian_data = _fetch_today_asian_moves()

    if not today_asian_data:
        return "No Asian market data available for correlation briefing."

    data = load_or_build_correlations()
    cond_moves = data.get("conditional_moves", {})

    if not cond_moves:
        return "No correlation data available. Run load_or_build_correlations(force_refresh=True)."

    lines: List[str] = []
    lines.append("ASIAN CORRELATION BRIEFING")
    lines.append("=" * 40)
    lines.append("")

    # Summary of today's Asian moves
    lines.append("Today's Asian Moves:")
    for name, move in sorted(today_asian_data.items(), key=lambda x: abs(x[1]), reverse=True):
        arrow = "+" if move > 0 else ""
        lines.append(f"  {name:<12} {arrow}{move:.2f}%")
    lines.append("")

    # Find threshold breaches and report historical Indian responses
    breaches_found = False
    for asian_name, move in sorted(today_asian_data.items(), key=lambda x: abs(x[1]), reverse=True):
        if asian_name not in cond_moves:
            continue

        # Determine which thresholds are breached
        breached_thresholds = []
        for thr in CORRELATION_THRESHOLDS:
            if thr > 0 and move >= thr:
                breached_thresholds.append(thr)
            elif thr < 0 and move <= thr:
                breached_thresholds.append(thr)

        if not breached_thresholds:
            continue

        breaches_found = True
        # Use the most extreme threshold breached
        extreme_thr = max(breached_thresholds, key=abs)
        thr_key = f"{extreme_thr:+.1f}%"

        lines.append(f"BREACH: {asian_name} at {move:+.2f}% (threshold {thr_key})")
        lines.append(f"  {'Indian Stock':<12} {'Median':>7} {'Hit%':>6} {'N':>4}")
        lines.append(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*4}")

        thr_data = cond_moves[asian_name].get(thr_key, {})
        # Sort by absolute median response descending
        sorted_india = sorted(
            thr_data.items(),
            key=lambda x: abs(x[1].get("median", 0) or 0),
            reverse=True,
        )

        for india_name, stats in sorted_india:
            if stats.get("median") is None:
                continue
            median = stats["median"]
            hit_rate = stats["hit_rate"]
            n = stats["n"]
            med_str = f"{median:+.2f}%"
            hit_str = f"{hit_rate*100:.0f}%"
            lines.append(f"  {india_name:<12} {med_str:>7} {hit_str:>6} {n:>4}")

        lines.append("")

    if not breaches_found:
        lines.append("No threshold breaches detected in today's Asian data.")
        lines.append("All moves within normal range (-2% to +2%).")
        lines.append("")
        # Still show top correlations for context
        corr_matrix = data.get("correlation_matrix", {})
        if corr_matrix:
            lines.append("Strongest correlations for reference:")
            corr_df = pd.DataFrame(corr_matrix)
            # Find top 5 absolute correlations
            top_pairs = []
            for a_col in corr_df.index:
                for i_col in corr_df.columns:
                    val = corr_df.loc[a_col, i_col]
                    if pd.notna(val):
                        top_pairs.append((a_col, i_col, float(val)))
            top_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
            for a_name, i_name, corr_val in top_pairs[:8]:
                lines.append(f"  {a_name:<12} <-> {i_name:<12}  r={corr_val:+.3f}")
            lines.append("")

    # Sector summary
    lines.append("SECTOR SUMMARY:")
    lines.append("-" * 40)
    sector_data = get_sector_correlations()
    for pair_key, info in sector_data.items():
        corr_val = info.get("correlation")
        label = info.get("label", pair_key)
        corr_str = f"r={corr_val:+.4f}" if corr_val is not None else "r=N/A"
        lines.append(f"  {label:<35} {corr_str}")

        # Show conditional moves for breached thresholds only
        agg_cond = info.get("conditional_moves", {})
        for thr_key, agg in agg_cond.items():
            thr_val = float(thr_key.replace("%", ""))
            # Check if any Asian ticker in this sector breached
            relevant_asian = {
                "Defence_India_vs_Asia": ["Kawasaki", "MHI", "Hanwha"],
                "Upstream_vs_Brent": ["Brent"],
                "IT_vs_Asia_Broad": ["Nikkei", "KOSPI", "ASX"],
                "Downstream_vs_Brent": ["Brent"],
            }.get(pair_key, [])

            breached_now = False
            for a in relevant_asian:
                a_move = today_asian_data.get(a, 0)
                if (thr_val > 0 and a_move >= thr_val) or (thr_val < 0 and a_move <= thr_val):
                    breached_now = True
                    break

            if breached_now:
                lines.append(
                    f"    {thr_key}: median {agg['avg_median']:+.2f}%, "
                    f"hit {agg['avg_hit_rate']*100:.0f}%, "
                    f"n={agg['total_n']}"
                )
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    return "\n".join(lines)


# =========================================================================
#  Stock-Level Probability Ranking
# =========================================================================

def rank_stocks_by_probability(
    today_asian_data: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Rank Indian stocks by probability of moving up/down today.

    Uses today's Asian threshold breaches to look up historical conditional
    moves. Each stock gets a composite score from ALL breached Asian tickers.

    Returns
    -------
    list of dict
        Sorted by absolute probability descending. Each dict:
        ``{ticker, direction, prob_pct, median_move_pct, n_signals,
           drivers: [{asian_name, threshold, hit_rate, median, n}]}``
    """
    if today_asian_data is None:
        today_asian_data = _fetch_today_asian_moves()

    if not today_asian_data:
        logger.warning("No Asian data available for stock ranking")
        return []

    data = load_or_build_correlations()
    cond_moves = data.get("conditional_moves", {})
    if not cond_moves:
        logger.warning("No conditional moves data for stock ranking")
        return []

    # Collect all breached thresholds across all Asian tickers
    stock_signals: Dict[str, List[Dict[str, Any]]] = {}  # india_name -> list of signals

    for asian_name, move in today_asian_data.items():
        if asian_name not in cond_moves:
            continue

        # Find the most extreme breached threshold
        breached_thr = None
        for thr in CORRELATION_THRESHOLDS:
            if thr > 0 and move >= thr:
                if breached_thr is None or abs(thr) > abs(breached_thr):
                    breached_thr = thr
            elif thr < 0 and move <= thr:
                if breached_thr is None or abs(thr) > abs(breached_thr):
                    breached_thr = thr

        if breached_thr is None:
            continue

        thr_key = f"{breached_thr:+.1f}%"
        thr_data = cond_moves[asian_name].get(thr_key, {})

        for india_name, stats in thr_data.items():
            if stats.get("median") is None or stats.get("hit_rate") is None:
                continue
            if stats["n"] < CORRELATION_MIN_EVENTS:
                continue

            if india_name not in stock_signals:
                stock_signals[india_name] = []

            stock_signals[india_name].append({
                "asian_name": asian_name,
                "threshold": thr_key,
                "hit_rate": stats["hit_rate"],
                "median": stats["median"],
                "n": stats["n"],
            })

    # Build ranked list with composite probability
    ranked = []
    for india_name, signals in stock_signals.items():
        # Composite: weighted average of hit rates, weighted by sample size
        total_n = sum(s["n"] for s in signals)
        if total_n == 0:
            continue

        weighted_hit = sum(s["hit_rate"] * s["n"] for s in signals) / total_n
        weighted_median = sum(s["median"] * s["n"] for s in signals) / total_n

        # Direction from the median
        direction = "UP" if weighted_median > 0 else "DOWN"

        # Format drivers as human-readable strings
        drivers = sorted(signals, key=lambda s: abs(s["median"]), reverse=True)
        top_driver = drivers[0]["asian_name"] if drivers else ""
        driver_str = f"{top_driver} {drivers[0]['threshold']}" if drivers else ""

        ranked.append({
            "ticker": india_name,
            "direction": direction,
            "prob_pct": round(weighted_hit * 100, 1),
            "median_move_pct": round(weighted_median, 2),
            "n_signals": len(signals),
            "total_n": total_n,
            "drivers": drivers[:3],  # top 3 drivers
            "driver": driver_str,
            "prob_up_pct": round(weighted_hit * 100, 1) if direction == "UP"
                          else round((1 - weighted_hit) * 100, 1),
        })

    # Sort by absolute probability (most confident first)
    ranked.sort(key=lambda x: x["prob_pct"], reverse=True)
    return ranked


def get_stock_ranking_briefing(
    today_asian_data: Optional[Dict[str, float]] = None,
) -> str:
    """Format stock probability ranking for the pre-market briefing."""
    ranked = rank_stocks_by_probability(today_asian_data)
    if not ranked:
        return ""

    lines = [
        "STOCK PROBABILITY RANKING (data-driven):",
        f"  {'Stock':<12} {'Dir':>4} {'Prob':>5} {'Median':>7} {'Driver'}",
        f"  {'-'*12} {'-'*4} {'-'*5} {'-'*7} {'-'*20}",
    ]

    for s in ranked:
        arrow = "\u2191" if s["direction"] == "UP" else "\u2193"
        lines.append(
            f"  {s['ticker']:<12} {arrow:>4} {s['prob_pct']:>4.0f}% "
            f"{s['median_move_pct']:>+6.2f}% {s['driver']}"
        )

    return "\n".join(lines)


# =========================================================================
#  CLI Entry Point
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="Anka Asian Correlation Engine")
    parser.add_argument("--refresh", action="store_true", help="Force cache refresh")
    parser.add_argument("--briefing", action="store_true", help="Print today's briefing")
    parser.add_argument("--sectors", action="store_true", help="Print sector correlations")
    parser.add_argument("--matrix", action="store_true", help="Print full correlation matrix")
    args = parser.parse_args()

    if args.refresh:
        logger.info("Forcing correlation refresh ...")
        load_or_build_correlations(force_refresh=True)
        logger.info("Done.")

    if args.briefing:
        print(generate_correlation_briefing())

    if args.sectors:
        sectors = get_sector_correlations()
        print(json.dumps(sectors, indent=2, default=str))

    if args.matrix:
        data = load_or_build_correlations()
        corr = data.get("correlation_matrix", {})
        if corr:
            df = pd.DataFrame(corr)
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", 200)
            pd.set_option("display.float_format", "{:+.3f}".format)
            print(df)
        else:
            print("No correlation matrix available. Run with --refresh first.")

    if not any([args.refresh, args.briefing, args.sectors, args.matrix]):
        # Default: build/load and print briefing
        print(generate_correlation_briefing())
