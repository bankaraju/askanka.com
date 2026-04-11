"""
Anka Research Pipeline — Pattern Engine
Historical pattern analysis: fetches 1 year of Indian stock data,
correlates political events with stock movements, and builds a pattern lookup table.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from config import EVENT_TAXONOMY, INDIA_SIGNAL_STOCKS, INDIA_SPREAD_PAIRS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
HIST_DIR = DATA_DIR / "india_historical"
EVENTS_FILE = DATA_DIR / "historical_events.json"
PATTERN_OUTPUT = DATA_DIR / "pattern_lookup.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pattern_engine.log", delay=True, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("pattern_engine")

# ---------------------------------------------------------------------------
# Cache staleness threshold (hours)
# ---------------------------------------------------------------------------
CACHE_MAX_AGE_HOURS = 12


# ============================= DATA FETCHING ===============================

def _csv_path(ticker: str) -> Path:
    """Return the CSV cache path for a given ticker key."""
    safe = ticker.replace("/", "_").replace(".", "_")
    return HIST_DIR / f"{safe}.csv"


def _is_cache_fresh(path: Path, max_age_hours: int = CACHE_MAX_AGE_HOURS) -> bool:
    """Return True if *path* exists and was modified less than *max_age_hours* ago."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(hours=max_age_hours)


def fetch_india_historical(days: int = 365) -> dict[str, pd.DataFrame]:
    """Fetch 1-year daily OHLCV for all INDIA_SIGNAL_STOCKS via yfinance.

    Saves each ticker as CSV in ``india_historical/``.
    Returns ``{ticker_key: DataFrame}`` with columns
    ``[Date, Open, High, Low, Close, Volume]``.
    """
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    end = datetime.now()
    start = end - timedelta(days=days)
    result: dict[str, pd.DataFrame] = {}

    for key, meta in INDIA_SIGNAL_STOCKS.items():
        yf_ticker = meta["yf"]
        csv = _csv_path(key)

        # Use cache if fresh
        if _is_cache_fresh(csv):
            logger.info("Cache hit for %s (%s)", key, csv.name)
            try:
                df = pd.read_csv(csv, parse_dates=["Date"])
                result[key] = df
                continue
            except Exception:
                logger.warning("Failed to read cached CSV for %s, re-fetching.", key)

        # Fetch from yfinance
        logger.info("Fetching %s (%s) …", key, yf_ticker)
        try:
            raw = yf.download(
                yf_ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                logger.warning("No data returned for %s", key)
                continue

            # Flatten MultiIndex columns if present (yfinance >=0.2.31)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            df = raw.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            df = df.sort_values("Date").reset_index(drop=True)
            df.to_csv(csv, index=False)
            result[key] = df
            logger.info("Saved %d rows for %s", len(df), key)
        except Exception as exc:
            logger.error("Error fetching %s: %s", key, exc)

    logger.info("Historical data ready: %d / %d tickers loaded.", len(result), len(INDIA_SIGNAL_STOCKS))
    return result


# ========================== EVENT LOADING ==================================

def load_historical_events() -> list[dict[str, Any]]:
    """Load curated events from ``data/historical_events.json``.

    Returns list of dicts with keys:
    ``date, event, category, source, oil_move_next_day_pct``
    """
    if not EVENTS_FILE.exists():
        logger.error("Events file not found: %s", EVENTS_FILE)
        return []

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            events = json.load(f)
        logger.info("Loaded %d historical events.", len(events))
        return events
    except Exception as exc:
        logger.error("Failed to load events: %s", exc)
        return []


# ====================== EVENT RESPONSE MATRIX ==============================

def build_event_response_matrix(
    events: list[dict[str, Any]],
    price_data: dict[str, pd.DataFrame],
    forward_windows: list[int] | None = None,
) -> pd.DataFrame:
    """Compute forward returns for each Indian stock around each event.

    For each event, finds the event date (or next trading day) in each
    stock's price history and calculates the forward return over each
    window in *forward_windows* (default ``[1, 3, 5]``).

    Returns a DataFrame where each row is an event and columns include
    event metadata plus ``{ticker}_{N}d_return`` pairs.
    """
    if forward_windows is None:
        forward_windows = [1, 3, 5]

    rows: list[dict[str, Any]] = []

    for ev in events:
        row: dict[str, Any] = {
            "date": ev["date"],
            "event": ev["event"],
            "category": ev["category"],
            "source": ev.get("source", ""),
            "oil_move_next_day_pct": ev.get("oil_move_next_day_pct", None),
        }

        ev_date = pd.Timestamp(ev["date"])

        for ticker, df in price_data.items():
            if df.empty:
                continue

            dates = pd.to_datetime(df["Date"])
            # Find the event date or next available trading day
            mask = dates >= ev_date
            if not mask.any():
                for w in forward_windows:
                    row[f"{ticker}_{w}d_return"] = None
                continue

            t0_idx = mask.idxmax()  # first index where date >= ev_date
            close_t0 = df.loc[t0_idx, "Close"]

            for w in forward_windows:
                t_end = t0_idx + w
                if t_end < len(df):
                    close_tw = df.loc[t_end, "Close"]
                    try:
                        ret = (float(close_tw) / float(close_t0) - 1) * 100
                    except (ZeroDivisionError, TypeError):
                        ret = None
                    row[f"{ticker}_{w}d_return"] = round(ret, 3) if ret is not None else None
                else:
                    row[f"{ticker}_{w}d_return"] = None

        rows.append(row)

    matrix = pd.DataFrame(rows)
    logger.info("Event response matrix: %d events x %d columns.", len(matrix), len(matrix.columns))
    return matrix


# ======================== PATTERN LOOKUP ====================================

def _expected_direction(ticker: str, category: str) -> str | None:
    """Return the expected direction ('up' or 'down') for *ticker* under *category*.

    Uses EVENT_TAXONOMY and INDIA_SIGNAL_STOCKS group membership.
    """
    group = INDIA_SIGNAL_STOCKS.get(ticker, {}).get("group")
    sector = INDIA_SIGNAL_STOCKS.get(ticker, {}).get("sector", "")
    taxonomy = EVENT_TAXONOMY.get(category, {})

    if not taxonomy or not group:
        return None

    # Map stock sector to taxonomy key
    sector_lower = sector.lower()
    if "defense" in sector_lower:
        tax_key = "defense"
    elif "downstream" in sector_lower:
        tax_key = "downstream"
    elif "it" in sector_lower:
        tax_key = "it"
    else:
        tax_key = "oil"

    direction = taxonomy.get(tax_key)
    if direction == "flat":
        return None
    return direction


def build_pattern_lookup(response_matrix: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Aggregate event response matrix by category.

    Returns::

        {
            "escalation": {
                "ONGC": {
                    "1d_median": 2.1, "1d_mean": 1.8,
                    "3d_median": 4.5, "3d_mean": 3.9,
                    "5d_median": 5.2, "5d_mean": 4.7,
                    "hit_rate_1d": 0.75,
                    "n_events": 8
                },
                ...
            },
            ...
        }

    ``hit_rate`` = fraction of events where the stock moved in the expected
    direction (positive for winners, negative for losers).
    """
    categories = response_matrix["category"].unique()
    tickers = list(INDIA_SIGNAL_STOCKS.keys())
    windows = [1, 3, 5]
    lookup: dict[str, dict[str, Any]] = {}

    for cat in categories:
        cat_df = response_matrix[response_matrix["category"] == cat]
        lookup[cat] = {}

        for ticker in tickers:
            stats: dict[str, Any] = {}
            valid_returns: dict[int, list[float]] = {w: [] for w in windows}

            for _, row in cat_df.iterrows():
                for w in windows:
                    col = f"{ticker}_{w}d_return"
                    val = row.get(col)
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        valid_returns[w].append(float(val))

            if not valid_returns[1]:
                continue

            for w in windows:
                arr = valid_returns[w]
                if arr:
                    stats[f"{w}d_median"] = round(float(np.median(arr)), 3)
                    stats[f"{w}d_mean"] = round(float(np.mean(arr)), 3)

            # Hit rate: did the stock move in the expected direction?
            expected = _expected_direction(ticker, cat)
            if expected and valid_returns[1]:
                if expected == "up":
                    hits = sum(1 for r in valid_returns[1] if r > 0)
                else:  # down
                    hits = sum(1 for r in valid_returns[1] if r < 0)
                stats["hit_rate_1d"] = round(hits / len(valid_returns[1]), 3)

            stats["n_events"] = len(valid_returns[1])
            lookup[cat][ticker] = stats

    logger.info("Pattern lookup built for %d categories.", len(lookup))
    return lookup


# ====================== SPREAD BACKTEST =====================================

def compute_spread_backtest(
    pattern_lookup: dict[str, dict[str, Any]],
    spread_pairs: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute historical spread performance per event category.

    Spread return = mean(long-leg returns) - mean(short-leg returns).

    Returns::

        {
            "Upstream vs Downstream": {
                "escalation": {
                    "1d_spread_median": 3.6,
                    "3d_spread_median": 5.1,
                    "5d_spread_median": 6.8,
                    "hit_rate": 0.80,
                    "n": 8
                },
                ...
            },
            ...
        }
    """
    if spread_pairs is None:
        spread_pairs = INDIA_SPREAD_PAIRS

    windows = [1, 3, 5]
    results: dict[str, dict[str, Any]] = {}

    for pair in spread_pairs:
        pair_name = pair["name"]
        results[pair_name] = {}

        for cat, cat_data in pattern_lookup.items():
            # Gather median returns for long and short legs
            spread_stats: dict[str, Any] = {}
            long_counts: list[int] = []
            short_counts: list[int] = []

            for w in windows:
                long_rets = []
                short_rets = []

                for tk in pair["long"]:
                    tk_stats = cat_data.get(tk, {})
                    val = tk_stats.get(f"{w}d_median")
                    if val is not None:
                        long_rets.append(val)
                        if w == 1:
                            long_counts.append(tk_stats.get("n_events", 0))

                for tk in pair["short"]:
                    tk_stats = cat_data.get(tk, {})
                    val = tk_stats.get(f"{w}d_median")
                    if val is not None:
                        short_rets.append(val)
                        if w == 1:
                            short_counts.append(tk_stats.get("n_events", 0))

                if long_rets and short_rets:
                    spread = round(float(np.mean(long_rets)) - float(np.mean(short_rets)), 3)
                    spread_stats[f"{w}d_spread_median"] = spread

            # Hit rate: average of long-leg hit rates
            hit_rates = []
            for tk in pair["long"]:
                hr = cat_data.get(tk, {}).get("hit_rate_1d")
                if hr is not None:
                    hit_rates.append(hr)
            for tk in pair["short"]:
                hr = cat_data.get(tk, {}).get("hit_rate_1d")
                if hr is not None:
                    hit_rates.append(hr)

            if hit_rates:
                spread_stats["hit_rate"] = round(float(np.mean(hit_rates)), 3)

            n_vals = long_counts + short_counts
            spread_stats["n"] = int(np.min(n_vals)) if n_vals else 0

            if spread_stats.get("1d_spread_median") is not None:
                results[pair_name][cat] = spread_stats

    logger.info("Spread backtest complete for %d pairs.", len(results))
    return results


# ========================== MAIN ENTRYPOINT =================================

def run_full_backtest() -> dict[str, dict[str, Any]]:
    """Orchestrate the full backtest pipeline.

    Steps:
        1. Fetch historical data (or load from cache).
        2. Load curated events.
        3. Build event response matrix.
        4. Generate pattern lookup.
        5. Compute spread backtests.
        6. Save ``pattern_lookup.json``.
        7. Log summary stats.

    Returns the pattern_lookup dict.
    """
    logger.info("=" * 60)
    logger.info("PATTERN ENGINE — full backtest starting")
    logger.info("=" * 60)

    # 1. Historical price data
    price_data = fetch_india_historical()
    if not price_data:
        logger.error("No price data available. Aborting.")
        return {}

    # 2. Events
    events = load_historical_events()
    if not events:
        logger.error("No events loaded. Aborting.")
        return {}

    # 3. Response matrix
    response_matrix = build_event_response_matrix(events, price_data)

    # 4. Pattern lookup
    pattern_lookup = build_pattern_lookup(response_matrix)

    # 5. Spread backtests
    spread_results = compute_spread_backtest(pattern_lookup)

    # 6. Save outputs
    output = {
        "generated_at": datetime.now().isoformat(),
        "n_events": len(events),
        "n_tickers": len(price_data),
        "pattern_lookup": pattern_lookup,
        "spread_backtests": spread_results,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(PATTERN_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        logger.info("Saved pattern lookup to %s", PATTERN_OUTPUT)
    except Exception as exc:
        logger.error("Failed to save pattern_lookup.json: %s", exc)

    # 7. Summary stats
    logger.info("-" * 40)
    logger.info("SUMMARY")
    logger.info("  Events processed : %d", len(events))
    logger.info("  Tickers loaded   : %d", len(price_data))
    logger.info("  Categories       : %s", list(pattern_lookup.keys()))
    for pair_name, pair_data in spread_results.items():
        for cat, stats in pair_data.items():
            spread_1d = stats.get("1d_spread_median", "n/a")
            hr = stats.get("hit_rate", "n/a")
            logger.info("  %s | %s | 1d spread: %s | hit: %s", pair_name, cat, spread_1d, hr)
    logger.info("=" * 60)

    return pattern_lookup


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_full_backtest()
