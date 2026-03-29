"""
Anka Research Pipeline -- Signal Tracker
P&L tracking, lifecycle management, and monitoring for trading signals.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

from config import INDIA_SIGNAL_STOCKS, SIGNAL_STOP_LOSS_PCT

log = logging.getLogger("anka.signal_tracker")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
SIGNALS_DIR = DATA_DIR / "signals"
OPEN_FILE = SIGNALS_DIR / "open_signals.json"
CLOSED_FILE = SIGNALS_DIR / "closed_signals.json"


def _ensure_files() -> None:
    """Create the signals directory and seed JSON files if they don't exist."""
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    for fp in (OPEN_FILE, CLOSED_FILE):
        if not fp.exists():
            fp.write_text("[]", encoding="utf-8")
            log.info(f"Created {fp}")


# Run on import so the files are always available.
_ensure_files()


# ---------------------------------------------------------------------------
# JSON persistence helpers
# ---------------------------------------------------------------------------

def load_open_signals() -> List[Dict[str, Any]]:
    """Load all OPEN signals from *open_signals.json*."""
    try:
        data = OPEN_FILE.read_text(encoding="utf-8")
        signals = json.loads(data)
        log.debug(f"Loaded {len(signals)} open signal(s)")
        return signals
    except (json.JSONDecodeError, FileNotFoundError) as e:
        log.error(f"Failed to load open signals: {e}")
        return []


def load_closed_signals() -> List[Dict[str, Any]]:
    """Load all closed signals from *closed_signals.json*."""
    try:
        data = CLOSED_FILE.read_text(encoding="utf-8")
        signals = json.loads(data)
        log.debug(f"Loaded {len(signals)} closed signal(s)")
        return signals
    except (json.JSONDecodeError, FileNotFoundError) as e:
        log.error(f"Failed to load closed signals: {e}")
        return []


def save_open_signals(signals: List[Dict[str, Any]]) -> None:
    """Persist the open signals list to JSON (pretty-printed)."""
    try:
        OPEN_FILE.write_text(
            json.dumps(signals, indent=2, default=str), encoding="utf-8"
        )
        log.debug(f"Saved {len(signals)} open signal(s)")
    except Exception as e:
        log.error(f"Failed to save open signals: {e}")


def save_closed_signals(signals: List[Dict[str, Any]]) -> None:
    """Persist the closed signals list to JSON (pretty-printed)."""
    try:
        CLOSED_FILE.write_text(
            json.dumps(signals, indent=2, default=str), encoding="utf-8"
        )
        log.debug(f"Saved {len(signals)} closed signal(s)")
    except Exception as e:
        log.error(f"Failed to save closed signals: {e}")


def save_signal(signal: Dict[str, Any]) -> None:
    """Append a new signal to *open_signals.json*."""
    signals = load_open_signals()
    signals.append(signal)
    save_open_signals(signals)
    log.info(f"Saved new signal {signal.get('signal_id', '?')}")


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def fetch_current_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """Fetch current prices for Indian stock tickers via *yfinance*.

    Each plain ticker (e.g. ``"HAL"``) is mapped to its ``.NS`` Yahoo
    Finance symbol using :data:`INDIA_SIGNAL_STOCKS`.  If the ticker
    already contains a dot it is used as-is.

    Returns ``{ticker: current_price}`` (price is ``None`` on failure).
    """
    prices: Dict[str, Optional[float]] = {}
    for ticker in tickers:
        # Resolve Yahoo Finance symbol
        if "." in ticker:
            yf_symbol = ticker
        else:
            stock_info = INDIA_SIGNAL_STOCKS.get(ticker, {})
            yf_symbol = stock_info.get("yf", f"{ticker}.NS")

        try:
            data = yf.Ticker(yf_symbol)
            hist = data.history(period="1d")
            if hist.empty:
                log.warning(f"No price data for {yf_symbol}")
                prices[ticker] = None
            else:
                prices[ticker] = float(hist["Close"].iloc[-1])
        except Exception as e:
            log.error(f"yfinance error for {yf_symbol}: {e}")
            prices[ticker] = None

    return prices


# ---------------------------------------------------------------------------
# P&L computation
# ---------------------------------------------------------------------------

def compute_signal_pnl(
    signal: Dict[str, Any],
    current_prices: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    """Compute current P&L for an open signal.

    Returns a dict with ``long_pnl_pct``, ``short_pnl_pct``,
    ``spread_pnl_pct``, ``long_legs``, and ``short_legs`` detail lists.
    """
    long_legs: List[Dict[str, Any]] = []
    short_legs: List[Dict[str, Any]] = []

    for leg in signal.get("long_legs", []):
        ticker = leg["ticker"]
        entry = leg["price"]
        current = current_prices.get(ticker)
        if current is not None and entry:
            pnl_pct = (current / entry - 1) * 100
        else:
            pnl_pct = 0.0
            current = entry  # fallback
        long_legs.append(
            {"ticker": ticker, "entry": entry, "current": current, "pnl_pct": pnl_pct}
        )

    for leg in signal.get("short_legs", []):
        ticker = leg["ticker"]
        entry = leg["price"]
        current = current_prices.get(ticker)
        if current is not None and entry:
            pnl_pct = (1 - current / entry) * 100  # profit when price falls
        else:
            pnl_pct = 0.0
            current = entry
        short_legs.append(
            {"ticker": ticker, "entry": entry, "current": current, "pnl_pct": pnl_pct}
        )

    long_pnl = (
        sum(lg["pnl_pct"] for lg in long_legs) / len(long_legs) if long_legs else 0.0
    )
    short_pnl = (
        sum(sg["pnl_pct"] for sg in short_legs) / len(short_legs)
        if short_legs
        else 0.0
    )

    return {
        "long_pnl_pct": round(long_pnl, 2),
        "short_pnl_pct": round(short_pnl, 2),
        "spread_pnl_pct": round(long_pnl + short_pnl, 2),
        "long_legs": long_legs,
        "short_legs": short_legs,
    }


# ---------------------------------------------------------------------------
# Status checks
# ---------------------------------------------------------------------------

def _trading_days_elapsed(open_date_str: str) -> int:
    """Rough count of trading days since the signal opened (Mon-Fri only)."""
    try:
        open_date = datetime.fromisoformat(open_date_str).date()
    except (ValueError, TypeError):
        return 0
    today = datetime.utcnow().date()
    count = 0
    current = open_date
    while current < today:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            count += 1
    return count


def check_signal_status(
    signal: Dict[str, Any],
    current_prices: Dict[str, Optional[float]],
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Determine whether an open signal should be closed.

    Close conditions (checked in order):
      1. Any long leg down > ``SIGNAL_STOP_LOSS_PCT`` from entry -> STOPPED_OUT
      2. Any short leg up  > ``SIGNAL_STOP_LOSS_PCT`` from entry -> STOPPED_OUT
      3. Signal age > 5 trading days -> EXPIRED
      4. Spread P&L > +15% -> TARGET_HIT (optional early exit)

    Returns ``("OPEN", None)`` or ``(reason, pnl_dict)``.
    """
    pnl = compute_signal_pnl(signal, current_prices)

    # 1. Stop-loss on long legs (price fell too much)
    for leg in pnl["long_legs"]:
        if leg["pnl_pct"] <= -SIGNAL_STOP_LOSS_PCT:
            log.info(
                f"Signal {signal.get('signal_id')}: long leg {leg['ticker']} "
                f"hit stop ({leg['pnl_pct']:.1f}%)"
            )
            return ("STOPPED_OUT", pnl)

    # 2. Stop-loss on short legs (price rose too much)
    for leg in pnl["short_legs"]:
        if leg["pnl_pct"] <= -SIGNAL_STOP_LOSS_PCT:
            log.info(
                f"Signal {signal.get('signal_id')}: short leg {leg['ticker']} "
                f"hit stop ({leg['pnl_pct']:.1f}%)"
            )
            return ("STOPPED_OUT", pnl)

    # 3. Expiry (5 trading days)
    days = _trading_days_elapsed(signal.get("open_timestamp", ""))
    if days > 5:
        log.info(
            f"Signal {signal.get('signal_id')}: expired after {days} trading days"
        )
        return ("EXPIRED", pnl)

    # 4. Target hit (spread P&L > +15%)
    if pnl["spread_pnl_pct"] >= 15.0:
        log.info(
            f"Signal {signal.get('signal_id')}: target hit "
            f"(spread +{pnl['spread_pnl_pct']:.1f}%)"
        )
        return ("TARGET_HIT", pnl)

    return ("OPEN", None)


# ---------------------------------------------------------------------------
# Signal lifecycle
# ---------------------------------------------------------------------------

def close_signal(
    signal: Dict[str, Any],
    reason: str,
    pnl_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Close a signal: move it from open -> closed with final P&L."""
    signal["status"] = reason
    signal["close_timestamp"] = datetime.utcnow().isoformat()
    signal["final_pnl"] = pnl_dict

    # Remove from open
    open_signals = load_open_signals()
    open_signals = [
        s for s in open_signals if s.get("signal_id") != signal.get("signal_id")
    ]
    save_open_signals(open_signals)

    # Add to closed
    closed_signals = load_closed_signals()
    closed_signals.append(signal)
    save_closed_signals(closed_signals)

    log.info(
        f"Closed signal {signal.get('signal_id')} -> {reason} "
        f"(spread P&L: {pnl_dict.get('spread_pnl_pct', 0):+.1f}%)"
    )
    return signal


# ---------------------------------------------------------------------------
# Dashboard / analytics
# ---------------------------------------------------------------------------

def get_signal_dashboard() -> Dict[str, Any]:
    """Compute summary statistics across all signals (open + closed).

    Returns a dict suitable for :func:`telegram_bot.format_daily_dashboard`.
    """
    open_sigs = load_open_signals()
    closed_sigs = load_closed_signals()
    all_sigs = open_sigs + closed_sigs

    total = len(all_sigs)
    if total == 0:
        return {
            "total_signals": 0,
            "open_signals": 0,
            "closed_signals": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "avg_spread_pnl_pct": 0.0,
            "best_signal": {},
            "worst_signal": {},
            "by_category": {},
            "by_spread": {},
        }

    wins = [
        s for s in closed_sigs if s.get("status") == "TARGET_HIT"
    ]
    losses = [
        s for s in closed_sigs if s.get("status") in ("STOPPED_OUT", "EXPIRED")
    ]
    n_closed = len(closed_sigs)
    win_rate = (len(wins) / n_closed * 100) if n_closed else 0.0

    # Gather spread P&Ls from closed signals
    pnls: List[Tuple[str, float]] = []
    for s in closed_sigs:
        fp = s.get("final_pnl", {})
        pnl_val = fp.get("spread_pnl_pct", 0.0)
        pnls.append((s.get("signal_id", "?"), pnl_val))

    avg_pnl = sum(p[1] for p in pnls) / len(pnls) if pnls else 0.0

    best = max(pnls, key=lambda x: x[1]) if pnls else ("N/A", 0.0)
    worst = min(pnls, key=lambda x: x[1]) if pnls else ("N/A", 0.0)

    # Breakdown by category
    by_category: Dict[str, Dict[str, Any]] = {}
    for s in closed_sigs:
        cat = s.get("category", "unknown")
        if cat not in by_category:
            by_category[cat] = {"n": 0, "wins": 0, "pnls": []}
        by_category[cat]["n"] += 1
        fp = s.get("final_pnl", {})
        by_category[cat]["pnls"].append(fp.get("spread_pnl_pct", 0.0))
        if s.get("status") == "TARGET_HIT":
            by_category[cat]["wins"] += 1

    by_category_out = {}
    for cat, info in by_category.items():
        by_category_out[cat] = {
            "n": info["n"],
            "win_rate": round(info["wins"] / info["n"] * 100, 1) if info["n"] else 0,
            "avg_pnl": round(sum(info["pnls"]) / len(info["pnls"]), 2)
            if info["pnls"]
            else 0,
        }

    # Breakdown by spread name
    by_spread: Dict[str, Dict[str, Any]] = {}
    for s in closed_sigs:
        sp = s.get("spread_name", "unknown")
        if sp not in by_spread:
            by_spread[sp] = {"n": 0, "wins": 0, "pnls": []}
        by_spread[sp]["n"] += 1
        fp = s.get("final_pnl", {})
        by_spread[sp]["pnls"].append(fp.get("spread_pnl_pct", 0.0))
        if s.get("status") == "TARGET_HIT":
            by_spread[sp]["wins"] += 1

    by_spread_out = {}
    for sp, info in by_spread.items():
        by_spread_out[sp] = {
            "n": info["n"],
            "win_rate": round(info["wins"] / info["n"] * 100, 1) if info["n"] else 0,
            "avg_pnl": round(sum(info["pnls"]) / len(info["pnls"]), 2)
            if info["pnls"]
            else 0,
        }

    return {
        "total_signals": total,
        "open_signals": len(open_sigs),
        "closed_signals": n_closed,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "avg_spread_pnl_pct": round(avg_pnl, 2),
        "best_signal": {"id": best[0], "pnl": best[1]},
        "worst_signal": {"id": worst[0], "pnl": worst[1]},
        "by_category": by_category_out,
        "by_spread": by_spread_out,
    }


# ---------------------------------------------------------------------------
# Monitoring loops
# ---------------------------------------------------------------------------

def run_signal_monitor() -> List[Tuple[Dict[str, Any], str, Dict[str, Any]]]:
    """Monitor open signals, close any that hit exit conditions.

    Called every 30 minutes during market hours.

    Returns a list of ``(closed_signal, reason, pnl_dict)`` tuples for
    downstream Telegram follow-ups.
    """
    open_sigs = load_open_signals()
    if not open_sigs:
        log.info("No open signals to monitor")
        return []

    # Collect all tickers across open signals
    all_tickers: List[str] = []
    for sig in open_sigs:
        for leg in sig.get("long_legs", []):
            all_tickers.append(leg["ticker"])
        for leg in sig.get("short_legs", []):
            all_tickers.append(leg["ticker"])
    all_tickers = list(set(all_tickers))

    log.info(f"Fetching prices for {len(all_tickers)} tickers")
    try:
        current_prices = fetch_current_prices(all_tickers)
    except Exception as e:
        log.error(f"Price fetch failed, skipping monitor cycle: {e}")
        return []

    closed_results: List[Tuple[Dict[str, Any], str, Dict[str, Any]]] = []

    for sig in open_sigs:
        try:
            status, pnl = check_signal_status(sig, current_prices)
            if status != "OPEN" and pnl is not None:
                closed = close_signal(sig, status, pnl)
                closed_results.append((closed, status, pnl))
        except Exception as e:
            log.error(f"Error checking signal {sig.get('signal_id')}: {e}")

    log.info(
        f"Monitor complete: {len(closed_results)} signal(s) closed, "
        f"{len(open_sigs) - len(closed_results)} still open"
    )
    return closed_results


def run_eod_review() -> Dict[str, Any]:
    """End-of-day review at 3:45 PM IST.

    1. Runs the signal monitor one final time.
    2. Computes and returns the dashboard dict for Telegram delivery.
    """
    log.info("Running EOD review")
    closed = run_signal_monitor()
    if closed:
        log.info(f"EOD monitor closed {len(closed)} signal(s)")

    dashboard = get_signal_dashboard()
    log.info(
        f"EOD dashboard: {dashboard.get('total_signals')} total, "
        f"{dashboard.get('open_signals')} open, "
        f"win rate {dashboard.get('win_rate_pct')}%"
    )
    return dashboard
