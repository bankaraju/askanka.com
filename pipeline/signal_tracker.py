"""
Anka Research Pipeline -- Signal Tracker
P&L tracking, lifecycle management, and monitoring for trading signals.
"""

import json
import logging
import math

# Trail-stop live config. Validated by backtest 2026-04-15 across 1223
# synthetic 10-day trades from 11 spread pairs (6mo OHLC). bm=1.0 af=1.0
# lifted Sharpe from 1.21 → 1.29 (+7%), win rate 57% → 59%, mean return
# essentially unchanged (+1.43% vs +1.47% baseline). Trail fires on ~32%
# of trades, locking in avg +2.46% on those exits.
# Tail risk (max -15.57%) is NOT addressed by any trail setting — that
# loss mode is an overnight gap that a Layer-0 gap predictor must catch.
# See data/backtest_trail_stop.json and pipeline/autoresearch/backtest_trail_stop.py.
TRAIL_STOP_ENABLED   = True
TRAIL_BUDGET_MULT    = 1.0     # budget = avg_favorable_move * mult * sqrt(days)
TRAIL_ARM_FACTOR     = 1.0     # arm when peak >= budget * arm_factor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

from config import (
    INDIA_SIGNAL_STOCKS, SIGNAL_STOP_LOSS_PCT,
    SIGNAL_TRAILING_STOP_ACTIVATE_PCT, SIGNAL_TRAILING_STOP_DISTANCE_PCT,
    SIGNAL_ENRICHMENT_ENABLED, SIGNAL_GATE_ENABLED,
)
from spread_statistics import get_levels_for_spread

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


def get_weekly_closed_signals(days: int = 7) -> List[Dict[str, Any]]:
    """Return signals closed within the last N days."""
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    cutoff = datetime.now(IST) - timedelta(days=days)
    result = []
    for sig in load_closed_signals():
        ts = sig.get("close_timestamp") or sig.get("closed_at", "")
        if not ts:
            continue
        try:
            closed_dt = datetime.fromisoformat(ts)
            if closed_dt.tzinfo is None:
                closed_dt = closed_dt.replace(tzinfo=IST)
            if closed_dt >= cutoff:
                result.append(sig)
        except (ValueError, TypeError):
            continue
    return result


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


def _apply_enrichment(signal: dict) -> dict:
    """Attach trust/rank/break/OI + conviction score. No-op if flag off."""
    if not SIGNAL_ENRICHMENT_ENABLED:
        return signal
    try:
        from signal_enrichment import (
            load_trust_scores, load_correlation_breaks, load_regime_profile,
            load_oi_anomalies, enrich_signal, gate_signal,
        )
        trust = load_trust_scores()
        breaks = load_correlation_breaks()
        profile = load_regime_profile()
        oi = load_oi_anomalies()
        enriched = enrich_signal(signal, trust, breaks, profile, oi)
        blocked, reason, score = gate_signal(enriched)
        enriched["conviction_score"] = score
        enriched["gate_reason"] = reason
        enriched["gate_blocked"] = blocked if SIGNAL_GATE_ENABLED else False
        return enriched
    except Exception as e:
        log.warning("Enrichment failed, saving signal unenriched: %s", e)
        return signal


def save_signal(signal: Dict[str, Any]) -> None:
    """Append a new signal to *open_signals.json* with enrichment applied."""
    signal = _apply_enrichment(signal)
    if signal.get("gate_blocked"):
        log.warning("Signal %s blocked by gate: %s", signal.get("signal_id"), signal.get("gate_reason"))
        return
    signals = load_open_signals()
    signals.append(signal)
    save_open_signals(signals)
    log.info("Saved new signal %s (conviction=%.0f)", signal.get("signal_id", "?"), signal.get("conviction_score", 0))


def snap_entry_to_market_open(signals: List[Dict[str, Any]]) -> bool:
    """Update entry prices to today's open for signals generated outside
    market hours (overnight, weekends, holidays).

    This ensures P&L reflects executable prices, not stale closes from
    a prior session. Only runs once per signal — sets 'entry_snapped'
    flag to prevent re-snapping.

    Returns True if any signals were updated.
    """
    from eodhd_client import fetch_realtime
    updated = False
    for sig in signals:
        if sig.get("entry_snapped"):
            continue

        # Fetch today's open prices for all tickers in this signal
        all_tickers = (
            [l["ticker"] for l in sig.get("long_legs", [])]
            + [s["ticker"] for s in sig.get("short_legs", [])]
        )
        try:
            for leg in sig.get("long_legs", []) + sig.get("short_legs", []):
                ticker   = leg["ticker"]
                stock_info = INDIA_SIGNAL_STOCKS.get(ticker, {})
                eodhd_sym  = stock_info.get("eodhd", "")
                yf_sym     = stock_info.get("yf", f"{ticker}.NS")

                open_price = None

                # 1. EODHD real-time open field
                if eodhd_sym:
                    rt = fetch_realtime(eodhd_sym)
                    if rt and rt.get("open"):
                        open_price = float(rt["open"])

                # 2. Fallback: yfinance (timeout-bounded — see _yf_history_with_timeout)
                if open_price is None:
                    try:
                        hist = _yf_history_with_timeout(yf_sym)
                        if hist is not None and not hist.empty:
                            open_price = float(hist["Open"].iloc[-1])
                        elif hist is None:
                            log.warning("yfinance snap timeout for %s", yf_sym)
                    except Exception as e:
                        log.error("yfinance snap error for %s: %s", yf_sym, e)

                if open_price is not None:
                    old = leg["price"]
                    leg["price"] = open_price
                    log.info("Snapped %s entry: ₹%.2f → ₹%.2f (today's open)", ticker, old, open_price)

            sig["entry_snapped"] = True
            sig["open_timestamp"] = datetime.now(timezone.utc).isoformat()
            updated = True
            log.info(f"Signal {sig.get('signal_id')}: entry prices snapped to today's open")

        except Exception as e:
            log.error(f"Failed to snap entry for {sig.get('signal_id')}: {e}")

    return updated


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def _yf_history_with_timeout(yf_sym: str, timeout_s: float = 8.0):
    """yfinance history call with a hard wall-clock timeout.

    yfinance has no first-class timeout on .history(); a hung remote can
    block the whole signals cycle indefinitely. Submitting via a 1-worker
    ThreadPoolExecutor lets us cap the call. The thread is abandoned on
    timeout (no thread.kill in CPython), but daemon=True ensures it does
    not block process exit.
    """
    import concurrent.futures

    def _call():
        return yf.Ticker(yf_sym).history(period="1d")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="yf") as ex:
        future = ex.submit(_call)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            return None


def fetch_current_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """Fetch current prices for Indian stock tickers.

    Primary: EODHD real-time API (eodhd_client.fetch_realtime).
    Fallback: yfinance .history(period="1d") with hard 8s timeout.

    Tickers are plain names like "HAL", "BPCL" — resolved via INDIA_SIGNAL_STOCKS.
    """
    from eodhd_client import fetch_realtime

    prices: Dict[str, Optional[float]] = {}
    for ticker in tickers:
        stock_info = INDIA_SIGNAL_STOCKS.get(ticker, {})
        eodhd_sym  = stock_info.get("eodhd", "")
        yf_sym     = stock_info.get("yf", f"{ticker}.NS")

        price = None

        # 1. Try EODHD real-time
        if eodhd_sym:
            rt = fetch_realtime(eodhd_sym)
            if rt and rt.get("close"):
                price = float(rt["close"])
                log.debug("Price %s = %.2f (EODHD RT)", ticker, price)

        # 2. Fallback: yfinance with 8s hard timeout (cross-platform)
        if price is None:
            try:
                hist = _yf_history_with_timeout(yf_sym, timeout_s=8.0)
                if hist is None:
                    log.warning("yfinance timed out for %s after 8s — skipping", yf_sym)
                elif not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    log.debug("Price %s = %.2f (yfinance fallback)", ticker, price)
                else:
                    log.warning("No price data for %s (yfinance returned empty)", ticker)
            except Exception as e:
                log.error("yfinance error for %s: %s", yf_sym, e)

        prices[ticker] = price

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
    """Count of trading days since the signal opened (Mon-Fri only).

    Inclusive of the open day itself — a signal opened today is "day 1".
    """
    try:
        open_date = datetime.fromisoformat(open_date_str).date()
    except (ValueError, TypeError):
        return 1  # default to 1 if we can't parse
    today = datetime.utcnow().date()
    if open_date > today:
        return 1
    # Count trading days from open_date to today inclusive
    count = 0
    current = open_date
    while current <= today:
        if current.weekday() < 5:  # Mon-Fri
            count += 1
        current += timedelta(days=1)
    return max(count, 1)


def _compute_todays_spread_move(
    signal: Dict[str, Any],
    current_prices: Dict[str, Optional[float]],
) -> float:
    """Compute TODAY's spread move only (not cumulative from entry).

    Uses the previous close snapshot stored on the signal as reference.
    If no previous close exists (day 1), uses entry prices.
    Returns today's spread move in % (positive = favorable).
    """
    prev_long = signal.get("_prev_close_long", {})
    prev_short = signal.get("_prev_close_short", {})

    # Day 1: no prev close yet, use entry prices
    use_entry = not prev_long

    long_moves = []
    for leg in signal.get("long_legs", []):
        ticker = leg["ticker"]
        ref_price = prev_long.get(ticker, leg["price"]) if not use_entry else leg["price"]
        curr = current_prices.get(ticker)
        if curr and ref_price and ref_price > 0:
            long_moves.append((curr / ref_price - 1) * 100)

    short_moves = []
    for leg in signal.get("short_legs", []):
        ticker = leg["ticker"]
        ref_price = prev_short.get(ticker, leg["price"]) if not use_entry else leg["price"]
        curr = current_prices.get(ticker)
        if curr and ref_price and ref_price > 0:
            # Short P&L: profit when price falls
            short_moves.append((1 - curr / ref_price) * 100)

    avg_long = sum(long_moves) / len(long_moves) if long_moves else 0.0
    avg_short = sum(short_moves) / len(short_moves) if short_moves else 0.0

    return round(avg_long + avg_short, 4)


def snapshot_eod_prices(
    signals: List[Dict[str, Any]],
    current_prices: Dict[str, Optional[float]],
) -> None:
    """Snapshot current prices as 'previous close' for next day's daily move calc.

    Called at EOD (15:45 IST). Stores:
    1. Closing prices per leg → tomorrow's daily stop compares vs these
    2. Today's spread move → tomorrow's 2-day running stop needs it

    The 2-day running stop checks: was yesterday a loss AND is today a loss?
    So we store today's move as ``_prev_day_move`` for tomorrow's check.
    """
    for sig in signals:
        # 1. Store today's spread move for 2-day running stop
        todays_move = _compute_todays_spread_move(sig, current_prices)
        sig["_prev_day_move"] = round(todays_move, 4)

        # 2. Store closing prices for tomorrow's daily move calc
        prev_long = {}
        for leg in sig.get("long_legs", []):
            ticker = leg["ticker"]
            price = current_prices.get(ticker)
            if price:
                prev_long[ticker] = price
        sig["_prev_close_long"] = prev_long

        prev_short = {}
        for leg in sig.get("short_legs", []):
            ticker = leg["ticker"]
            price = current_prices.get(ticker)
            if price:
                prev_short[ticker] = price
        sig["_prev_close_short"] = prev_short


def compute_trail_budget(
    avg_favorable: float,
    days_since_check: int,
    budget_mult: float = None,
) -> float:
    """Historic-basis trailing budget scaled for elapsed days.

    Budget = avg_favorable_move * budget_mult * sqrt(max(1, days_since_check)).
    The sqrt scaler accounts for variance accumulating across holiday gaps:
    on a 3-day re-open, the spread has had 3 days of action to cover, so
    the single-day budget is widened accordingly.

    ``budget_mult`` defaults to module-level ``TRAIL_BUDGET_MULT``. Passing
    an explicit value lets replay / sweep / backtest scripts override it
    without touching the live constant.

    Returns 0.0 when avg_favorable is 0 (no historical data -> no trail).
    """
    if avg_favorable <= 0:
        return 0.0
    mult = TRAIL_BUDGET_MULT if budget_mult is None else budget_mult
    days = max(1, days_since_check)
    return avg_favorable * mult * math.sqrt(days)


def trail_stop_triggered(
    cumulative: float,
    peak: float,
    trail_budget: float,
    arm_factor: float = None,
) -> bool:
    """Peak-relative trailing stop check.

    Fires when cumulative P&L has given back more than ``trail_budget`` from
    the running peak. Arm guard: does not fire until peak has exceeded
    ``trail_budget * arm_factor`` — prevents fresh trades with noisy early
    moves from tripping instantly (daily_stop handles that regime).

    ``arm_factor`` defaults to module-level ``TRAIL_ARM_FACTOR``.

    Returns False when trail_budget is 0 (no historical basis -> skip).
    """
    if trail_budget <= 0:
        return False
    af = TRAIL_ARM_FACTOR if arm_factor is None else arm_factor
    if peak < trail_budget * af:
        return False
    return cumulative <= (peak - trail_budget)


def check_signal_status(
    signal: Dict[str, Any],
    current_prices: Dict[str, Optional[float]],
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Determine whether an open signal should be closed.

    STOPS-ONLY PHILOSOPHY: Winners run until stopped. We never voluntarily
    take profits — the only exits are stops. This keeps winning positions
    compounding. Losses are cut short by data-driven daily thresholds.

    Three exit conditions (all data-driven from 1-month spread statistics):

      0. TRAIL STOP: Peak-relative give-back. Budget =
         avg_favorable_move * 0.50 * sqrt(days_since_last_check).
         Locks in profit as cumulative P&L ratchets up. Checked first so
         it protects gains before the static daily stop allows flat-day
         slippage. Has a guard: doesn't fire until peak exceeds budget
         (daily stop handles the fresh-trade regime).

      1. DAILY STOP: Today's spread move breaches -(avg_favorable × 50%).
         Flat-trade safety net — catches bad days when trail stop hasn't
         armed yet.

      2. 2-DAY RUNNING STOP: Two consecutive losing days AND combined
         2-day loss exceeds 2 × daily_stop. Catches persistent
         deterioration that individual daily stops might miss.

    Returns ``("OPEN", None)`` or ``(reason, pnl_dict)``.
    """
    # Cumulative P&L from entry (what the trader has made overall)
    pnl = compute_signal_pnl(signal, current_prices)
    cumulative_spread = pnl["spread_pnl_pct"]

    # Today's spread move only (vs previous close or entry on day 1)
    todays_move = _compute_todays_spread_move(signal, current_prices)

    spread_name = signal.get("spread_name", "")

    # Get data-driven levels for this specific spread
    levels = get_levels_for_spread(spread_name)
    daily_std = levels["daily_std"]
    avg_favorable = levels["avg_favorable_move"]

    # Per-ticker ATR stop for correlation-break single-ticker trades.
    # Pair spreads continue using spread_statistics; the ATR stop is only
    # applied when it was computed for real (source != 'fallback').
    atr_stop = signal.get("_atr_stop") or {}
    use_atr = (
        signal.get("source") == "CORRELATION_BREAK"
        and atr_stop.get("stop_source", "").startswith("atr_")
        and atr_stop.get("stop_pct") is not None
    )
    if use_atr:
        daily_stop = atr_stop["stop_pct"]          # ATR-derived single-day stop
    else:
        daily_stop = -(avg_favorable * 0.50)       # spread-stats single-day stop
    two_day_stop = daily_stop * 2                  # 2-day stop = 2 × daily stop

    # Track consecutive losing days
    prev_day_move = signal.get("_prev_day_move")   # yesterday's spread move
    is_today_loss = todays_move < 0
    was_yesterday_loss = (prev_day_move is not None and prev_day_move < 0)
    two_day_combined = (todays_move + prev_day_move) if prev_day_move is not None else None

    # Update peak cumulative (for reporting AND trail stop)
    peak_pnl = signal.get("peak_spread_pnl_pct", 0.0)
    if cumulative_spread > peak_pnl:
        signal["peak_spread_pnl_pct"] = cumulative_spread
        peak_pnl = cumulative_spread

    # Trail stop: peak-relative, historic-basis, holiday-scaled
    last_check_iso = signal.get("_last_trail_check")
    days_since = 1
    if last_check_iso:
        try:
            from datetime import datetime as _dt
            last_check = _dt.fromisoformat(last_check_iso.replace("Z", "+00:00"))
            now = _dt.now(last_check.tzinfo) if last_check.tzinfo else _dt.now()
            delta_days = (now - last_check).days
            days_since = max(1, delta_days)
        except Exception:
            days_since = 1
    trail_budget = compute_trail_budget(avg_favorable, days_since)
    trail_stop = peak_pnl - trail_budget if trail_budget > 0 else None

    # Store levels on the signal for Telegram display + replay
    signal["_data_levels"] = {
        "daily_stop": round(daily_stop, 2),
        "two_day_stop": round(two_day_stop, 2),
        "trail_stop": round(trail_stop, 2) if trail_stop is not None else None,
        "trail_budget": round(trail_budget, 2),
        "todays_move": round(todays_move, 2),
        "cumulative": round(cumulative_spread, 2),
        "peak": round(peak_pnl, 2),
        "daily_std": round(daily_std, 2),
        "avg_favorable": round(avg_favorable, 2),
        "consecutive_losses": 2 if (is_today_loss and was_yesterday_loss) else (1 if is_today_loss else 0),
        "two_day_combined": round(two_day_combined, 2) if two_day_combined is not None else None,
        # Provenance tag for the UI fallback indicator.
        #   "atr_14"       → ATR-derived single-ticker stop (Phase C / correlation break)
        #   "fallback"     → ATR was attempted but unavailable; using spread-stats default
        #                    (UI renders a muted dot next to the Stop cell)
        #   "spread_stats" → Spread trade; classic avg_favorable × 0.50 stop. No ATR attempt.
        "stop_source": (
            atr_stop.get("stop_source", "atr_14") if use_atr
            else ("fallback" if signal.get("source") == "CORRELATION_BREAK" and atr_stop
                  else "spread_stats")
        ),
    }

    # Stamp the trail-check timestamp for the next invocation
    from datetime import datetime as _dt2
    signal["_last_trail_check"] = _dt2.now().isoformat()

    # ── EXIT 0: TRAIL STOP ─────────────────────────────────
    # Peak-relative give-back using historic favorable-move distribution.
    # Gated behind TRAIL_STOP_ENABLED — off by default until parameters
    # are validated on a real backtest sample. See module-level comment.
    if TRAIL_STOP_ENABLED and trail_stop_triggered(cumulative_spread, peak_pnl, trail_budget):
        log.info(
            f"Signal {signal.get('signal_id')}: TRAIL STOP "
            f"(cum {cumulative_spread:+.2f}% <= trail {trail_stop:+.2f}%, "
            f"peak {peak_pnl:+.2f}% - budget {trail_budget:.2f}%)"
        )
        return ("STOPPED_OUT_TRAIL", pnl)

    # ── EXIT 1: DAILY STOP ──────────────────────────────────
    # Today's spread move breaches 50% of avg daily favorable move.
    # Flat-trade safety net — fires when peak hasn't accumulated yet.
    if todays_move <= daily_stop:
        log.info(
            f"Signal {signal.get('signal_id')}: DAILY STOP "
            f"(today {todays_move:+.2f}% <= stop {daily_stop:+.2f}%, "
            f"cumulative {cumulative_spread:+.2f}%)"
        )
        return ("STOPPED_OUT", pnl)

    # ── EXIT 2: 2-DAY RUNNING STOP ──────────────────────────
    if is_today_loss and was_yesterday_loss and two_day_combined is not None:
        if two_day_combined <= two_day_stop:
            log.info(
                f"Signal {signal.get('signal_id')}: 2-DAY RUNNING STOP "
                f"(day1 {prev_day_move:+.2f}% + day2 {todays_move:+.2f}% "
                f"= {two_day_combined:+.2f}% <= stop {two_day_stop:+.2f}%, "
                f"cumulative {cumulative_spread:+.2f}%)"
            )
            return ("STOPPED_OUT_2DAY", pnl)

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
    # Populate days_open from the actual open→close span (bug: this was
    # defaulting to 0, so the track record showed all closed trades as 0-day).
    try:
        open_ts = signal.get("open_timestamp") or signal.get("timestamp", "")
        if open_ts:
            opened = datetime.fromisoformat(open_ts.replace("Z", "+00:00"))
            closed = datetime.fromisoformat(signal["close_timestamp"].replace("Z", "+00:00"))
            signal["days_open"] = max(0, (closed.replace(tzinfo=None) - opened.replace(tzinfo=None)).days)
    except Exception:
        pass  # fall back to whatever was set; don't block the close path

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

    print(f"  [trace.mon] start ({len(open_sigs)} sigs)", flush=True)

    # Snap entry prices to today's open for signals generated outside
    # market hours (only runs once per signal, idempotent)
    if snap_entry_to_market_open(open_sigs):
        save_open_signals(open_sigs)
        log.info("Entry prices snapped to today's open")
    print(f"  [trace.mon] snap done", flush=True)

    # Collect all tickers across open signals
    all_tickers: List[str] = []
    for sig in open_sigs:
        for leg in sig.get("long_legs", []):
            all_tickers.append(leg["ticker"])
        for leg in sig.get("short_legs", []):
            all_tickers.append(leg["ticker"])
    all_tickers = list(set(all_tickers))

    log.info(f"Fetching prices for {len(all_tickers)} tickers")
    print(f"  [trace.mon] fetch start ({len(all_tickers)} tickers)", flush=True)
    try:
        current_prices = fetch_current_prices(all_tickers)
    except Exception as e:
        log.error(f"Price fetch failed, skipping monitor cycle: {e}")
        return []
    print(f"  [trace.mon] fetch done", flush=True)

    closed_results: List[Tuple[Dict[str, Any], str, Dict[str, Any]]] = []
    peaks_updated = False

    for sig in open_sigs:
        sid = sig.get("signal_id", "?")
        print(f"  [trace.mon] check {sid}", flush=True)
        try:
            old_peak = sig.get("peak_spread_pnl_pct", 0.0)
            status, pnl = check_signal_status(sig, current_prices)
            if status != "OPEN" and pnl is not None:
                closed = close_signal(sig, status, pnl)
                closed_results.append((closed, status, pnl))
            elif sig.get("peak_spread_pnl_pct", 0.0) != old_peak:
                peaks_updated = True
        except Exception as e:
            log.error(f"Error checking signal {sig.get('signal_id')}: {e}")

    # Persist peak P&L updates for still-open signals
    if peaks_updated:
        remaining = [s for s in open_sigs
                     if s.get("signal_id") not in
                     {c[0].get("signal_id") for c in closed_results}]
        save_open_signals(remaining)

    log.info(
        f"Monitor complete: {len(closed_results)} signal(s) closed, "
        f"{len(open_sigs) - len(closed_results)} still open"
    )
    return closed_results


def run_eod_review() -> Dict[str, Any]:
    """End-of-day review at 3:45 PM IST.

    1. Runs the signal monitor one final time.
    2. Snapshots closing prices + today's move for next day's stops.
    3. Computes and returns the dashboard dict for Telegram delivery.
    """
    log.info("Running EOD review")
    closed = run_signal_monitor()
    if closed:
        log.info(f"EOD monitor closed {len(closed)} signal(s)")

    # Snapshot EOD prices for next day's daily stop / 2-day running stop
    remaining = load_open_signals()
    if remaining:
        all_tickers = []
        for sig in remaining:
            all_tickers += [l["ticker"] for l in sig.get("long_legs", [])]
            all_tickers += [s["ticker"] for s in sig.get("short_legs", [])]
        all_tickers = list(set(all_tickers))
        try:
            eod_prices = fetch_current_prices(all_tickers)
            snapshot_eod_prices(remaining, eod_prices)
            save_open_signals(remaining)
            log.info("EOD price snapshot saved for %d signal(s)", len(remaining))
        except Exception as e:
            log.error(f"EOD snapshot failed: {e}")

    dashboard = get_signal_dashboard()
    log.info(
        f"EOD dashboard: {dashboard.get('total_signals')} total, "
        f"{dashboard.get('open_signals')} open, "
        f"win rate {dashboard.get('win_rate_pct')}%"
    )
    return dashboard


# ---------------------------------------------------------------------------
# V2: Portfolio snapshot & cumulative P&L
# ---------------------------------------------------------------------------

def get_portfolio_snapshot() -> Dict[str, Any]:
    """Compute aggregate P&L across all open positions.

    Returns dict with:
        - open_positions: list of {signal_id, spread_name, tier, spread_pnl_pct, days_open}
        - portfolio_pnl_pct: weighted average P&L across open positions
        - signal_tier_pnl: avg P&L for SIGNAL tier trades
        - exploring_tier_pnl: avg P&L for EXPLORING tier trades
    """
    open_sigs = load_open_signals()
    if not open_sigs:
        return {
            "open_positions": [],
            "portfolio_pnl_pct": 0.0,
            "signal_tier_pnl": 0.0,
            "exploring_tier_pnl": 0.0,
        }

    # Collect all tickers
    all_tickers: List[str] = []
    for sig in open_sigs:
        # V2 signal cards have "spreads" list
        if "spreads" in sig:
            for spread in sig.get("spreads", []):
                for leg in spread.get("long_leg", []):
                    all_tickers.append(leg["ticker"])
                for leg in spread.get("short_leg", []):
                    all_tickers.append(leg["ticker"])
        else:
            # V1 signal format
            for leg in sig.get("long_legs", []):
                all_tickers.append(leg["ticker"])
            for leg in sig.get("short_legs", []):
                all_tickers.append(leg["ticker"])

    all_tickers = list(set(all_tickers))
    try:
        current_prices = fetch_current_prices(all_tickers)
    except Exception as e:
        log.error(f"Price fetch failed for portfolio snapshot: {e}")
        return {"open_positions": [], "portfolio_pnl_pct": 0.0}

    positions: List[Dict[str, Any]] = []
    signal_pnls: List[float] = []
    exploring_pnls: List[float] = []

    for sig in open_sigs:
        days_open = _trading_days_elapsed(sig.get("timestamp", sig.get("open_timestamp", "")))

        if "spreads" in sig:
            # V2: iterate over all spreads in the card
            for spread in sig.get("spreads", []):
                tier = spread.get("tier", "EXPLORING")
                pnl = _compute_spread_pnl_from_legs(
                    spread.get("long_leg", []),
                    spread.get("short_leg", []),
                    current_prices,
                )
                positions.append({
                    "signal_id": sig.get("signal_id", "?"),
                    "spread_name": spread.get("spread_name", "?"),
                    "tier": tier,
                    "spread_pnl_pct": pnl,
                    "days_open": days_open,
                })
                if tier == "SIGNAL":
                    signal_pnls.append(pnl)
                elif tier == "EXPLORING":
                    exploring_pnls.append(pnl)
        else:
            # V1: single spread
            pnl_dict = compute_signal_pnl(sig, current_prices)
            pnl_val = pnl_dict.get("spread_pnl_pct", 0.0)
            tier = sig.get("tier", "SIGNAL" if sig.get("trade", {}).get("backtest_validated") else "EXPLORING")
            spread_name = sig.get("trade", {}).get("spread_name", sig.get("spread_name", "?"))
            positions.append({
                "signal_id": sig.get("signal_id", "?"),
                "spread_name": spread_name,
                "tier": tier,
                "spread_pnl_pct": pnl_val,
                "days_open": days_open,
            })
            if tier == "SIGNAL":
                signal_pnls.append(pnl_val)
            else:
                exploring_pnls.append(pnl_val)

    all_pnls = [p["spread_pnl_pct"] for p in positions]
    portfolio_pnl = round(sum(all_pnls) / len(all_pnls), 2) if all_pnls else 0.0

    return {
        "open_positions": positions,
        "portfolio_pnl_pct": portfolio_pnl,
        "signal_tier_pnl": round(sum(signal_pnls) / len(signal_pnls), 2) if signal_pnls else 0.0,
        "exploring_tier_pnl": round(sum(exploring_pnls) / len(exploring_pnls), 2) if exploring_pnls else 0.0,
    }


def _compute_spread_pnl_from_legs(
    long_legs: List[Dict],
    short_legs: List[Dict],
    current_prices: Dict[str, Optional[float]],
) -> float:
    """Quick P&L computation from leg dicts (for V2 signal cards)."""
    long_pnls = []
    for leg in long_legs:
        entry = leg.get("price", 0)
        current = current_prices.get(leg.get("ticker"), entry)
        if entry and current:
            long_pnls.append((current / entry - 1) * 100)

    short_pnls = []
    for leg in short_legs:
        entry = leg.get("price", 0)
        current = current_prices.get(leg.get("ticker"), entry)
        if entry and current:
            short_pnls.append((1 - current / entry) * 100)

    avg_long = sum(long_pnls) / len(long_pnls) if long_pnls else 0.0
    avg_short = sum(short_pnls) / len(short_pnls) if short_pnls else 0.0
    return round(avg_long + avg_short, 2)


def get_cumulative_pnl() -> Dict[str, Any]:
    """Compute running total P&L from all closed signals.

    Returns dict with:
        - cumulative_pnl_pct: sum of all closed spread P&Ls
        - total_closed: number of closed signals
        - wins/losses count
        - signal_stats: {wins, losses, avg_pnl} for SIGNAL tier
        - exploring_stats: {wins, losses, avg_pnl} for EXPLORING tier
        - days_active: trading days since first signal
        - weekly_pnls: list of {week, pnl} for trending
    """
    closed = load_closed_signals()

    if not closed:
        return {
            "cumulative_pnl_pct": 0.0,
            "total_closed": 0,
            "wins": 0,
            "losses": 0,
            "signal_stats": {"wins": 0, "losses": 0, "avg_pnl": 0.0},
            "exploring_stats": {"wins": 0, "losses": 0, "avg_pnl": 0.0},
            "days_active": 0,
        }

    all_pnls = []
    signal_pnls = []
    exploring_pnls = []
    sig_wins = sig_losses = exp_wins = exp_losses = 0

    for sig in closed:
        fp = sig.get("final_pnl", {})
        pnl = fp.get("spread_pnl_pct", 0.0)
        all_pnls.append(pnl)
        tier = sig.get("tier", "SIGNAL")
        is_win = pnl > 0

        if tier == "SIGNAL":
            signal_pnls.append(pnl)
            if is_win:
                sig_wins += 1
            else:
                sig_losses += 1
        else:
            exploring_pnls.append(pnl)
            if is_win:
                exp_wins += 1
            else:
                exp_losses += 1

    cumulative = sum(all_pnls)
    wins = sum(1 for p in all_pnls if p > 0)
    losses = sum(1 for p in all_pnls if p <= 0)

    # Days active since first signal
    first_ts = closed[0].get("timestamp", closed[0].get("open_timestamp", ""))
    days_active = _trading_days_elapsed(first_ts) if first_ts else 0

    return {
        "cumulative_pnl_pct": round(cumulative, 2),
        "total_closed": len(closed),
        "wins": wins,
        "losses": losses,
        "signal_stats": {
            "wins": sig_wins,
            "losses": sig_losses,
            "avg_pnl": round(sum(signal_pnls) / len(signal_pnls), 2) if signal_pnls else 0.0,
        },
        "exploring_stats": {
            "wins": exp_wins,
            "losses": exp_losses,
            "avg_pnl": round(sum(exploring_pnls) / len(exploring_pnls), 2) if exploring_pnls else 0.0,
        },
        "days_active": days_active,
    }


def check_tier_promotions() -> List[Dict[str, Any]]:
    """Check if any EXPLORING category/spread combos should be promoted to SIGNAL.

    Promotion criteria: 20+ closed EXPLORING signals AND win_rate >= 65%.
    Returns list of {category, spread_name, win_rate, n_closed} dicts.
    """
    from config import TIER_PROMOTION_MIN_SIGNALS, TIER_PROMOTION_WIN_RATE

    closed = load_closed_signals()
    # Group by (category, spread_name) for EXPLORING tier only
    combos: Dict[str, Dict[str, Any]] = {}
    for sig in closed:
        tier = sig.get("tier", "SIGNAL")
        if tier != "EXPLORING":
            continue
        cat = sig.get("category", sig.get("event", {}).get("category", ""))
        spread = sig.get("spread_name", sig.get("trade", {}).get("spread_name", ""))
        key = f"{cat}|{spread}"
        if key not in combos:
            combos[key] = {"wins": 0, "total": 0}
        combos[key]["total"] += 1
        pnl = sig.get("final_pnl", {}).get("spread_pnl_pct", 0)
        if pnl > 0:
            combos[key]["wins"] += 1

    promotions = []
    for key, stats in combos.items():
        if stats["total"] < TIER_PROMOTION_MIN_SIGNALS:
            continue
        win_rate = stats["wins"] / stats["total"]
        if win_rate >= TIER_PROMOTION_WIN_RATE:
            cat, spread = key.split("|", 1)
            promotions.append({
                "category": cat,
                "spread_name": spread,
                "win_rate": round(win_rate, 3),
                "n_closed": stats["total"],
            })
            log.info(
                f"PROMOTION candidate: {spread} for {cat} "
                f"({win_rate:.0%} win rate, {stats['total']} trades)"
            )

    return promotions
