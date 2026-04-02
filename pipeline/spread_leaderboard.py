"""
Anka Research Pipeline -- Intraday Spread Leaderboard
Captures NSE open prices and computes live spread P&L for all spreads.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf

from config import INDIA_SIGNAL_STOCKS, INDIA_SPREAD_PAIRS
from trading_calendar import is_trading_day, get_holiday_name

logger = logging.getLogger("anka.spread_leaderboard")

DATA_DIR = Path(__file__).parent / "data"
OPEN_PRICES_FILE = DATA_DIR / "today_open_prices.json"
SIGNALS_DIR = DATA_DIR / "signals"
OPEN_SIGNALS_FILE = SIGNALS_DIR / "open_signals.json"

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Open-price capture (run at 09:22 IST)
# ---------------------------------------------------------------------------

def capture_open_prices() -> dict:
    """Called at 09:22 IST. Fetch opening prices for all INDIA_SIGNAL_STOCKS tickers.
    Uses yfinance 1d interval to get today's Open price.
    Saves to data/today_open_prices.json with timestamp.
    """
    holiday = get_holiday_name()
    if holiday:
        logger.info("Market closed — %s. Skipping open price capture.", holiday)
        return {}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now_ist = datetime.now(IST)
    logger.info("Capturing open prices at %s IST", now_ist.strftime("%H:%M"))

    # Build list of yfinance tickers
    yf_tickers = {name: info["yf"] for name, info in INDIA_SIGNAL_STOCKS.items()}
    ticker_str = " ".join(yf_tickers.values())

    prices: Dict[str, Optional[float]] = {}

    try:
        data = yf.download(ticker_str, period="1d", interval="1d", progress=False)

        if data.empty:
            logger.warning("yfinance returned empty data -- market may be closed")
            return {}

        open_col = data["Open"]

        for name, yf_sym in yf_tickers.items():
            try:
                if yf_sym in open_col.columns:
                    val = open_col[yf_sym].iloc[-1]
                else:
                    val = open_col.iloc[-1] if len(yf_tickers) == 1 else None

                if val is not None and not _is_nan(val):
                    prices[name] = round(float(val), 2)
                else:
                    prices[name] = None
                    logger.warning("No open price for %s (%s)", name, yf_sym)
            except Exception as exc:
                prices[name] = None
                logger.warning("Error reading open for %s: %s", name, exc)

    except Exception as exc:
        logger.error("yfinance download failed: %s", exc)
        return {}

    result = {
        "captured_at": now_ist.isoformat(),
        "date": now_ist.strftime("%Y-%m-%d"),
        "prices": prices,
    }

    OPEN_PRICES_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    valid_count = sum(1 for v in prices.values() if v is not None)
    logger.info("Saved open prices: %d/%d tickers captured", valid_count, len(prices))
    return result


def _is_nan(val) -> bool:
    """Check if a value is NaN without importing numpy."""
    try:
        return val != val  # NaN != NaN is True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_open_prices() -> dict:
    """Load today's open prices from file. Returns empty dict if not available
    or if the saved prices are from a different date."""
    if not OPEN_PRICES_FILE.exists():
        logger.warning("Open prices file not found -- run capture_open_prices() first")
        return {}

    try:
        data = json.loads(OPEN_PRICES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Failed to read open prices file: %s", exc)
        return {}

    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    if data.get("date") != today_str:
        logger.warning(
            "Open prices are stale (file date %s, today %s)",
            data.get("date"),
            today_str,
        )
        return {}

    return data.get("prices", {})


def _load_open_signals() -> List[Dict[str, Any]]:
    """Load open signals from signal_tracker's file."""
    if not OPEN_SIGNALS_FILE.exists():
        return []
    try:
        return json.loads(OPEN_SIGNALS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return []


# ---------------------------------------------------------------------------
# Live price fetch
# ---------------------------------------------------------------------------

def fetch_live_prices() -> dict:
    """Fetch current live prices for all signal stocks.
    Returns {name: price} dict. None values for failed fetches."""
    yf_tickers = {name: info["yf"] for name, info in INDIA_SIGNAL_STOCKS.items()}
    ticker_str = " ".join(yf_tickers.values())

    prices: Dict[str, Optional[float]] = {}

    try:
        data = yf.download(ticker_str, period="1d", interval="1m", progress=False)

        if data.empty:
            logger.warning("Live price fetch returned empty data")
            return {}

        close_col = data["Close"]

        for name, yf_sym in yf_tickers.items():
            try:
                if yf_sym in close_col.columns:
                    val = close_col[yf_sym].dropna().iloc[-1]
                else:
                    val = close_col.dropna().iloc[-1] if len(yf_tickers) == 1 else None

                if val is not None and not _is_nan(val):
                    prices[name] = round(float(val), 2)
                else:
                    prices[name] = None
                    logger.warning("No live price for %s", name)
            except Exception as exc:
                prices[name] = None
                logger.warning("Error reading live price for %s: %s", name, exc)

    except Exception as exc:
        logger.error("Live price download failed: %s", exc)
        return {}

    logger.info("Fetched live prices for %d tickers", sum(1 for v in prices.values() if v))
    return prices


# ---------------------------------------------------------------------------
# Spread P&L computation
# ---------------------------------------------------------------------------

def compute_spread_pnl(open_prices: dict, current_prices: dict, pair: dict) -> dict:
    """Compute long-leg avg return, short-leg avg return, net spread P&L
    for a single spread pair.

    Returns dict with:
        spread_name, long_pnl_pct, short_pnl_pct, spread_pnl_pct,
        long_details: [{ticker, open, current, pnl_pct}],
        short_details: [{ticker, open, current, pnl_pct}]
    """
    spread_name = pair["name"]

    def _leg_details(tickers: list) -> List[dict]:
        details = []
        for ticker in tickers:
            op = open_prices.get(ticker)
            cp = current_prices.get(ticker)
            if op and cp and op > 0:
                pnl_pct = round(((cp - op) / op) * 100, 2)
            else:
                pnl_pct = 0.0
            details.append({
                "ticker": ticker,
                "open": op,
                "current": cp,
                "pnl_pct": pnl_pct,
            })
        return details

    long_details = _leg_details(pair["long"])
    short_details = _leg_details(pair["short"])

    # Average return for each leg (equal-weight)
    long_pnls = [d["pnl_pct"] for d in long_details if d["open"] is not None]
    short_pnls = [d["pnl_pct"] for d in short_details if d["open"] is not None]

    long_pnl_pct = round(sum(long_pnls) / len(long_pnls), 2) if long_pnls else 0.0
    short_pnl_pct = round(sum(short_pnls) / len(short_pnls), 2) if short_pnls else 0.0

    # Net spread: long-leg return minus short-leg return
    # (positive = spread widening in our favour)
    spread_pnl_pct = round(long_pnl_pct - short_pnl_pct, 2)

    return {
        "spread_name": spread_name,
        "long_pnl_pct": long_pnl_pct,
        "short_pnl_pct": short_pnl_pct,
        "spread_pnl_pct": spread_pnl_pct,
        "long_details": long_details,
        "short_details": short_details,
        "triggers": pair.get("triggers", []),
    }


def compute_all_spreads_live() -> list:
    """Load open prices, fetch current prices, compute P&L for ALL 4 spreads.
    Cross-reference with open signals to mark which are currently signaled + tier.
    Sort by spread_pnl_pct descending. Returns list of spread dicts."""
    open_prices = _load_open_prices()
    if not open_prices:
        logger.error("No open prices available -- cannot compute spreads")
        return []

    current_prices = fetch_live_prices()
    if not current_prices:
        logger.error("No live prices available -- cannot compute spreads")
        return []

    # Load open signals for cross-referencing
    open_signals = _load_open_signals()
    signaled_names: Dict[str, str] = {}
    for sig in open_signals:
        # V1 flat format: each signal has "spread_name" at top level
        spread_name = sig.get("spread_name", "")
        if spread_name:
            signaled_names[spread_name] = sig.get("tier", "SIGNAL")
        # V2 card format: signal has "spreads" list
        for spread in sig.get("spreads", []):
            sname = spread.get("spread_name", "")
            if sname:
                signaled_names[sname] = spread.get("tier", "EXPLORING")

    # Compute each spread
    spreads = []
    for pair in INDIA_SPREAD_PAIRS:
        result = compute_spread_pnl(open_prices, current_prices, pair)

        # Mark signal status
        sname = result["spread_name"]
        if sname in signaled_names:
            result["signaled"] = True
            result["signal_tier"] = signaled_names[sname]
        else:
            result["signaled"] = False
            result["signal_tier"] = None

        spreads.append(result)

    # Sort by spread P&L descending (best performer first)
    spreads.sort(key=lambda s: s["spread_pnl_pct"], reverse=True)

    logger.info(
        "Computed %d spreads: best=%s (%.2f%%), worst=%s (%.2f%%)",
        len(spreads),
        spreads[0]["spread_name"] if spreads else "N/A",
        spreads[0]["spread_pnl_pct"] if spreads else 0,
        spreads[-1]["spread_name"] if spreads else "N/A",
        spreads[-1]["spread_pnl_pct"] if spreads else 0,
    )
    return spreads


# ---------------------------------------------------------------------------
# Telegram formatting
# ---------------------------------------------------------------------------

from config import UNIT_SIZE_INR, SIGNAL_UNITS, EXPLORING_UNITS

_TIER_EMOJI = {
    "SIGNAL": "\U0001f7e2",     # green circle
    "TIER 1": "\U0001f7e2",     # green circle (alias)
    "TIER 2": "\U0001f7e1",     # yellow circle
    "EXPLORING": "\U0001f7e1",  # yellow circle
}

_TIER_UNITS = {
    "SIGNAL": SIGNAL_UNITS,
    "EXPLORING": EXPLORING_UNITS,
}


def _auto_insight(spreads: list) -> str:
    """Generate a one-line insight based on the spread results."""
    if not spreads:
        return "No spread data available."

    best = spreads[0]
    worst = spreads[-1]

    # Check if defence vs IT is outperforming
    defence_it = next((s for s in spreads if s["spread_name"] == "Defence vs IT"), None)
    upstream_down = next(
        (s for s in spreads if s["spread_name"] == "Upstream vs Downstream"), None
    )

    if best["spread_pnl_pct"] > 2.0:
        return (
            f"{best['spread_name']} leading strongly at "
            f"+{best['spread_pnl_pct']:.1f}% -- thesis confirmed intraday."
        )
    elif worst["spread_pnl_pct"] < -1.5:
        return (
            f"{worst['spread_name']} underwater at "
            f"{worst['spread_pnl_pct']:.1f}% -- monitor for reversal or stop."
        )
    elif defence_it and upstream_down:
        if defence_it["spread_pnl_pct"] > 0 and upstream_down["spread_pnl_pct"] > 0:
            return "Both defence and energy spreads positive -- broad risk-on for war trades."
        elif defence_it["spread_pnl_pct"] < 0 and upstream_down["spread_pnl_pct"] < 0:
            return "Both key spreads negative -- de-escalation sentiment or rotation out."
    elif all(s["spread_pnl_pct"] > 0 for s in spreads):
        return "All spreads green -- strong directional move in progress."
    elif all(s["spread_pnl_pct"] < 0 for s in spreads):
        return "All spreads red -- consider reducing exposure or hedging."

    return (
        f"Mixed signals: best {best['spread_name']} "
        f"+{best['spread_pnl_pct']:.1f}%, worst {worst['spread_name']} "
        f"{worst['spread_pnl_pct']:.1f}%."
    )


def _inr_pnl(pnl_pct: float, tier: str = "SIGNAL") -> str:
    """Convert % P&L to ₹ at tier unit size."""
    units = _TIER_UNITS.get(tier, SIGNAL_UNITS)
    if units == 0:
        return "paper"
    inr = (pnl_pct / 100.0) * UNIT_SIZE_INR * units
    return f"\u20b9{inr:+,.0f}"


def format_leaderboard(spreads: list, regime: str = "UNKNOWN") -> str:
    """Format the midday leaderboard for Telegram delivery.

    Shows all spreads ranked by P&L with individual stock details.
    Marks which ones are signaled (from open_signals.json).
    Includes ₹ P&L at reference unit sizing.
    """
    now_ist = datetime.now(IST)
    time_str = now_ist.strftime("%H:%M")

    regime_emoji = {
        "RISK_ON": "\U0001f534",
        "RISK ON": "\U0001f534",
        "RISK_OFF": "\U0001f7e2",
        "RISK OFF": "\U0001f7e2",
        "MIXED": "\U0001f7e1",
        "UNKNOWN": "\u26aa",
    }
    r_emoji = regime_emoji.get(regime.upper(), "\u26aa")

    lines = [
        "\u2501" * 22,
        f"\U0001f4ca MIDDAY SPREAD CHECK \u2014 {time_str} IST",
        "\u2501" * 22,
        f"{r_emoji} REGIME: {regime.upper().replace('_', ' ')}",
        f"\U0001f4b0 Unit: \u20b9{UNIT_SIZE_INR:,}/side",
        "",
    ]

    for rank, spread in enumerate(spreads, 1):
        name = spread["spread_name"]
        net = spread["spread_pnl_pct"]
        net_sign = "+" if net >= 0 else ""

        # Signal badge + ₹ P&L
        tier = spread.get("signal_tier", "SIGNAL") if spread.get("signaled") else "SIGNAL"
        badge = ""
        if spread.get("signaled"):
            tier_icon = _TIER_EMOJI.get(tier, "\U0001f7e1")
            badge = f" {tier_icon} {tier}"

        inr = _inr_pnl(net, tier)

        lines.append(
            f"#{rank} {name:<25s} {net_sign}{net:.2f}% ({inr}){badge}"
        )

        # Long leg details
        long_parts = []
        for d in spread["long_details"]:
            pnl = d["pnl_pct"]
            sign = "+" if pnl >= 0 else ""
            long_parts.append(f"{d['ticker']} {sign}{pnl:.2f}%")

        # Short leg details
        short_parts = []
        for d in spread["short_details"]:
            pnl = d["pnl_pct"]
            sign = "+" if pnl >= 0 else ""
            short_parts.append(f"{d['ticker']} {sign}{pnl:.2f}%")

        lines.append(
            f"   {' | '.join(long_parts)} vs {' | '.join(short_parts)}"
        )
        lines.append("")

    insight = _auto_insight(spreads)
    lines.append(f"\U0001f4a1 LESSON: {insight}")
    lines.append("\u2501" * 22)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_midday_leaderboard(regime: str = "UNKNOWN") -> str:
    """Main entry: compute all spreads and format leaderboard. Returns formatted text."""
    logger.info("Running midday spread leaderboard")

    spreads = compute_all_spreads_live()

    if not spreads:
        now_ist = datetime.now(IST)
        msg = (
            f"\u2501" * 22 + "\n"
            f"\U0001f4ca MIDDAY SPREAD CHECK \u2014 {now_ist.strftime('%H:%M')} IST\n"
            f"\u2501" * 22 + "\n"
            f"\u26a0\ufe0f No spread data available.\n"
            f"Open prices may not have been captured today.\n"
            f"Run capture_open_prices() after 09:15 IST.\n"
            f"\u2501" * 22
        )
        logger.warning("Leaderboard empty -- no spread data")
        return msg

    result = format_leaderboard(spreads, regime=regime)
    logger.info("Leaderboard formatted with %d spreads", len(spreads))
    return result


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        result = capture_open_prices()
        if result:
            print(f"Captured open prices for {len(result.get('prices', {}))} tickers")
        else:
            print("Failed to capture open prices (market closed?)")
    else:
        board = run_midday_leaderboard(regime="RISK ON")
        print(board)
