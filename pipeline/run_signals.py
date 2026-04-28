"""
Anka Research Pipeline — Signal Monitor V2
Runs every 30 minutes during IST market hours to detect events and generate signals.

V2 features:
  - Multi-spread signal cards (all spreads per event, with tiers)
  - Risk ON / Risk OFF regime detection
  - Midday spread leaderboard
  - Enhanced EOD dashboard with portfolio P&L + success rates
  - Regime flip alerts

Usage:
    python run_signals.py                      # one-shot: detect + signal + print
    python run_signals.py --telegram           # one-shot + send to Telegram
    python run_signals.py --monitor            # continuous 30-min loop (market hours only)
    python run_signals.py --monitor --telegram # continuous + Telegram delivery
    python run_signals.py --leaderboard        # midday spread leaderboard only
    python run_signals.py --eod                # end-of-day review only
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from political_signals import run_signal_check
from signal_tracker import (
    load_open_signals, check_signal_status, close_signal,
    fetch_current_prices, get_signal_dashboard, run_signal_monitor,
    get_portfolio_snapshot, get_cumulative_pnl, check_tier_promotions,
    save_signal, run_eod_review,
)
from telegram_bot import (
    format_signal_card, format_followup_message, send_message,
    format_multi_spread_card, format_regime_card, format_eod_dashboard,
    format_entry_call, format_stop_loss_call, format_exit_call,
    format_alert, format_position_update,
)
from config import (
    MARKET_HOURS_IST, POLL_INTERVAL_MINUTES, INDIA_SIGNAL_STOCKS,
    MIDDAY_WINDOW_IST,
)
from trading_calendar import is_trading_day, get_holiday_name
from risk_guardrails import check_risk_gates
from shadow_pnl import create_shadow_trade, update_shadow_trade, generate_daily_strip


IST = timezone(timedelta(hours=5, minutes=30))

# Hard cutoff for opening NEW signal positions intraday.
# Signals firing after this leave under 60 min of execution window before
# the 14:30 IST mechanical close, so they are not realistically tradeable.
# Existing open positions are still monitored, P&L still updates, closes
# still fire — only NEW OPENs are blocked past this line.
NEW_SIGNAL_CUTOFF_IST = time(14, 30)

_LOCK_FILE = Path(__file__).parent / "logs" / "signals.lock"
_LOCK_MAX_AGE_MINUTES = 25  # if lock is older than this, it's stale (previous run crashed)


def _pid_alive(pid: int) -> bool:
    """Cross-platform: True if process with `pid` exists. False on any error."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_lock() -> bool:
    """Return True if lock acquired (safe to run), False if another instance is running.

    The lock is considered stale (and removed) if EITHER of:
      * file age exceeds _LOCK_MAX_AGE_MINUTES, OR
      * the PID written inside the file no longer corresponds to a live process.

    Checking PID liveness is critical — a hung run that gets killed externally
    (Windows Task Scheduler, manual kill) leaves the lockfile behind without
    releasing it, blocking every subsequent cycle until the age threshold passes.
    """
    if _LOCK_FILE.exists():
        age_seconds = time.time() - _LOCK_FILE.stat().st_mtime
        try:
            held_pid = int(_LOCK_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            held_pid = -1
        if age_seconds < _LOCK_MAX_AGE_MINUTES * 60 and _pid_alive(held_pid):
            return False  # fresh lock + holder is alive — another instance running
        # Stale lock: either age exceeded, or PID is dead. Reclaim.
        _LOCK_FILE.unlink(missing_ok=True)
    try:
        _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return False  # can't write lock — be safe, don't run


def _release_lock() -> None:
    _LOCK_FILE.unlink(missing_ok=True)


def _ist_now():
    return datetime.now(IST)


def _in_market_hours():
    now = _ist_now()
    if not is_trading_day(now):
        return False
    market_open = datetime.strptime(MARKET_HOURS_IST["open"], "%H:%M").time()
    market_close = datetime.strptime(MARKET_HOURS_IST["close"], "%H:%M").time()
    return market_open <= now.time() <= market_close


def _in_midday_window():
    """Check if current IST time is within the midday leaderboard window."""
    now = _ist_now()
    mid_start = datetime.strptime(MIDDAY_WINDOW_IST["start"], "%H:%M").time()
    mid_end = datetime.strptime(MIDDAY_WINDOW_IST["end"], "%H:%M").time()
    return mid_start <= now.time() <= mid_end and is_trading_day(now)


def _load_current_regime():
    """Load today's regime from file."""
    try:
        from premarket_scanner import load_current_regime
        return load_current_regime()
    except Exception:
        return "MIXED"


def _format_for_telegram(signal):
    """Convert internal signal dict to Telegram card format (V1 compat)."""
    return {
        "headline": signal["event"]["headline"],
        "category": signal["event"]["category"],
        "confidence_pct": int(signal["event"]["confidence"] * 100),
        "spread_name": signal["trade"]["spread_name"],
        "long_legs": signal["trade"]["long_leg"],
        "short_legs": signal["trade"]["short_leg"],
        "hit_rate_pct": int(signal["trade"]["historical_hit_rate"] * 100),
        "hit_n": round(signal["trade"]["historical_hit_rate"] * signal["trade"]["n_precedents"]),
        "hit_total": signal["trade"]["n_precedents"],
        "expected_1d_spread_pct": signal["trade"]["expected_1d_spread"],
        "signal_id": signal["signal_id"],
    }


def _dedup_signals(signals):
    """Keep only the highest-confidence signal per category.

    V2: deduplicate by category only (not category+spread),
    since each card now contains all spreads for that category.
    """
    best = {}
    for sig in signals:
        key = sig["event"]["category"]
        existing = best.get(key)
        if existing is None or sig["event"]["confidence"] > existing["event"]["confidence"]:
            best[key] = sig
    return list(best.values())


def _load_stock_probs():
    """Load stock probability ranking from asian correlation engine."""
    try:
        from asian_correlation import rank_stocks_by_probability
        return rank_stocks_by_probability()
    except Exception:
        return []


def run_once(send_telegram=False):
    """Single detection + signal generation cycle."""
    holiday = get_holiday_name()
    if holiday:
        print(f"\n[{_ist_now().strftime('%H:%M IST')}] Market closed — {holiday}. No signals generated.")
        return []

    if not _acquire_lock():
        print(f"[{_ist_now().strftime('%H:%M IST')}] Another instance is running — skipping this cycle.")
        return []

    try:
        return _run_once_inner(send_telegram)
    finally:
        _release_lock()


def _run_once_inner(send_telegram=False):
    """Inner body of run_once — called only when lock is held."""
    print(f"\n[{_ist_now().strftime('%H:%M IST')}] Running signal check...")

    regime = _load_current_regime()
    stock_probs = _load_stock_probs()

    # Hard cutoff: do not OPEN new positions after 14:30 IST.
    # Phase C closes mechanically at 14:30; spread/news fires later than
    # this leave too little execution window to be a real trade.
    now_ist_t = _ist_now().time()
    past_new_signal_cutoff = now_ist_t >= NEW_SIGNAL_CUTOFF_IST

    # Skip new signal detection if we already have open positions —
    # focus on monitoring existing trades, not churning new ideas.
    existing_open = load_open_signals()
    if past_new_signal_cutoff:
        print(f"  ⏸  Past 14:30 IST cutoff (now {now_ist_t.strftime('%H:%M')}) "
              f"— blocking new OPENs, monitoring existing positions only")
        new_signals = []
        raw_signals = []
    elif existing_open:
        print(f"  {len(existing_open)} open position(s) — skipping new signal scan, monitoring only")
        new_signals = []
        raw_signals = []
    else:
        # 1. Detect events and generate new signals (V2: multi-spread cards)
        raw_signals = run_signal_check()
        new_signals = _dedup_signals(raw_signals) if raw_signals else []

    if new_signals:
        print(f"  New signals: {len(new_signals)} (deduped from {len(raw_signals)})")
        sent_count = 0
        for sig in new_signals:
            # V2: use multi-spread card format
            if "spreads" in sig:
                card = format_multi_spread_card(sig, regime=regime)
                # card is empty string if no SIGNAL-tier spreads exist
                if not card:
                    n_exploring = sum(1 for s in sig.get("spreads", []) if s.get("tier") == "EXPLORING")
                    print(f"  {sig['signal_id']} ({sig['event']['category']}): "
                          f"{n_exploring} exploring spreads below 65% gate — suppressed from Telegram")
                    continue

                # Also generate ENTRY service calls for each SIGNAL-tier spread
                # and register them for P&L tracking.
                # IMPORTANT: suppress Telegram if ALL signal-tier spreads
                # in this card are already being tracked (avoid spam).
                existing_open = load_open_signals()
                existing_spreads = {
                    s.get("spread_name") for s in existing_open
                }

                signal_spreads = [
                    sp for sp in sig.get("spreads", [])
                    if sp.get("tier") == "SIGNAL"
                ]
                new_spreads = [
                    sp for sp in signal_spreads
                    if sp.get("spread_name", "") not in existing_spreads
                ]

                if not new_spreads:
                    print(f"  {sig['signal_id']}: all SIGNAL spreads already tracked — "
                          f"suppressing duplicate Telegram send")
                    continue

                # ── Risk gate check before any new entries ──
                _closed_path = Path(__file__).parent / "data" / "signals" / "closed_signals.json"
                risk_gate = check_risk_gates(_closed_path)
                if not risk_gate["allowed"]:
                    print(f"  🛑 CIRCUIT BREAKER {risk_gate['level']}: {risk_gate['reason']}")
                    if send_telegram:
                        try:
                            send_message(f"🛑 CIRCUIT BREAKER: {risk_gate['level']}\n{risk_gate['reason']}", parse_mode=None)
                        except Exception:
                            pass
                    continue  # skip all new entries for this signal card

                if risk_gate["level"] != "NORMAL":
                    print(f"  ⚠️ Risk gate {risk_gate['level']}: sizing reduced to {risk_gate['sizing_factor']:.0%}")

                for spread in signal_spreads:
                    spread_name = spread.get("spread_name", "")
                    long_tickers = [lg["ticker"] for lg in spread.get("long_leg", [])]
                    short_tickers = [sg["ticker"] for sg in spread.get("short_leg", [])]

                    # Only send ENTRY + register for NEW spreads
                    if spread_name in existing_spreads:
                        print(f"  {spread_name} already tracked — skipping")
                        continue

                    # Filter stock_probs to relevant tickers
                    relevant_probs = [
                        sp for sp in stock_probs
                        if sp["ticker"] in long_tickers or sp["ticker"] in short_tickers
                    ]
                    entry_card = format_entry_call(
                        signal_id=sig["signal_id"],
                        category=sig["event"]["category"],
                        spread_name=spread_name,
                        long_tickers=long_tickers,
                        short_tickers=short_tickers,
                        hit_rate_pct=spread.get("hit_rate", 0) * 100,
                        expected_spread_pct=spread.get("expected_1d_spread", 0),
                        stock_probs=relevant_probs if relevant_probs else None,
                        regime=regime,
                    )
                    print(entry_card)
                    if send_telegram:
                        try:
                            send_message(entry_card, parse_mode=None)
                            print(f"  Sent ENTRY call for {spread_name} to Telegram")
                        except Exception as e:
                            print(f"  Failed to send ENTRY call: {e}")

                    # ── Register for P&L tracking ────────────────────
                    trackable = {
                        "signal_id": f"{sig['signal_id']}-{spread_name.replace(' ', '_')}",
                        "open_timestamp": sig.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "status": "OPEN",
                        "spread_name": spread_name,
                        "category": sig["event"]["category"],
                        "tier": "SIGNAL",
                        "event_headline": sig["event"]["headline"][:120],
                        "hit_rate": spread.get("hit_rate", 0),
                        "expected_1d_spread": spread.get("expected_1d_spread", 0),
                        "long_legs": spread.get("long_leg", []),
                        "short_legs": spread.get("short_leg", []),
                        "peak_spread_pnl_pct": 0.0,
                        "days_open": 0,
                    }
                    save_signal(trackable)
                    existing_spreads.add(spread_name)
                    print(f"  ✅ Registered {spread_name} for P&L tracking")

                    # ── Shadow trade with full provenance ──
                    try:
                        shadow_signal = {
                            "signal_id": trackable["signal_id"],
                            "type": "spread",
                            "spread_name": spread_name,
                            "direction": "LONG",
                            "conviction": spread.get("hit_rate", 0) * 100,
                            "long_legs": spread.get("long_leg", []),
                            "short_legs": spread.get("short_leg", []),
                            "event_headline": sig["event"]["headline"][:120],
                            "z_score": spread.get("z_score"),
                        }
                        shadow = create_shadow_trade(
                            signal=shadow_signal,
                            entry_price=1.0,
                            regime=regime,
                            sizing_factor=risk_gate["sizing_factor"],
                        )
                        shadow["confirmation"] = {
                            "hit_rate": spread.get("hit_rate", 0),
                            "expected_1d_spread": spread.get("expected_1d_spread", 0),
                            "tier": "SIGNAL",
                            "category": sig["event"]["category"],
                        }
                        # Save shadow trade alongside the regular signal
                        shadow_path = Path(__file__).parent / "data" / "signals" / "shadow_trades.json"
                        shadow_path.parent.mkdir(parents=True, exist_ok=True)
                        existing_shadows = []
                        if shadow_path.exists():
                            try:
                                existing_shadows = json.loads(shadow_path.read_text(encoding="utf-8"))
                            except Exception:
                                existing_shadows = []
                        existing_shadows.append(shadow)
                        shadow_path.write_text(json.dumps(existing_shadows, indent=2, default=str), encoding="utf-8")
                        print(f"  📊 Shadow trade created: {spread_name} (sizing {risk_gate['sizing_factor']:.0%})")
                    except Exception as e:
                        print(f"  Shadow trade creation failed: {e}")
                    # ── Synthetic options shadow ──
                    try:
                        from pipeline.synthetic_options import build_leverage_matrix, record_shadow_entry
                        import json as _json
                        profile_path = Path(__file__).parent / "autoresearch" / "reverse_regime_profile.json"
                        profiles = _json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
                        positioning_path = Path(__file__).parent / "data" / "positioning.json"
                        oi_data = _json.loads(positioning_path.read_text(encoding="utf-8")) if positioning_path.exists() else {}
                        opt_signal = {
                            "signal_id": trackable["signal_id"],
                            "spread_name": spread_name,
                            "conviction": spread.get("hit_rate", 0) * 100,
                            "long_legs": spread.get("long_leg", []),
                            "short_legs": spread.get("short_leg", []),
                        }
                        matrix = build_leverage_matrix(opt_signal, profiles, oi_data=oi_data)
                        entry = record_shadow_entry(opt_signal, matrix, regime)
                        if entry:
                            print(f"  🎯 Synthetic options shadow: {entry['shadow_id']}")
                        elif matrix.get("grounding_ok"):
                            print(f"  ⚪ Synthetic options: all tiers negative carry")
                        else:
                            print(f"  ⚪ Synthetic options: {matrix.get('reason', 'vol unavailable')}")
                    except Exception as e:
                        print(f"  Synthetic options shadow failed: {e}")
                # Only send the main overview card if new spreads were registered
                print(card)
                sent_count += 1
                if send_telegram:
                    try:
                        send_message(card, parse_mode=None)
                        print(f"  Sent {sig['signal_id']} to Telegram")
                    except Exception as e:
                        print(f"  Failed to send {sig['signal_id']}: {e}")
            else:
                # V1 fallback
                card_data = _format_for_telegram(sig)
                card = format_signal_card(card_data)
                print(card)
                sent_count += 1
                if send_telegram:
                    try:
                        send_message(card, parse_mode=None)
                        print(f"  Sent {sig['signal_id']} to Telegram")
                    except Exception as e:
                        print(f"  Failed to send {sig['signal_id']}: {e}")

        if sent_count == 0:
            print("  All signals below 65% hit rate gate — none sent to subscribers")
    else:
        print("  No new signals")
        if send_telegram:
            # Heartbeat: send a brief "no signals" update
            now = _ist_now()
            heartbeat = (
                f"\u2501" * 22 + "\n"
                f"\U0001f50d ANKA SCAN \u2014 {now.strftime('%H:%M IST, %d %b %Y')}\n"
                f"\u2501" * 22 + "\n\n"
                f"Scanned 7 RSS feeds + Google News.\n"
                f"No new tradeable signals this cycle.\n"
                f"Regime: {regime.replace('_', ' ')}\n\n"
                f"System is active. Next scan in 30 min.\n"
                f"\u2501" * 22
            )
            try:
                send_message(heartbeat, parse_mode=None)
            except Exception:
                pass
        print(f"  [trace] heartbeat done @ {_ist_now().strftime('%H:%M:%S')}", flush=True)

    # 1b. Phase C break → standalone signal candidates
    # Same 14:30 IST cutoff as the news-spread path: do not OPEN new
    # Phase C break positions intraday past 14:30 — too little execution
    # window before the mechanical close.
    if past_new_signal_cutoff:
        print(f"  ⏸  Past 14:30 IST cutoff — skipping Phase C break candidate generation")
    else:
        try:
            from break_signal_generator import generate_break_candidates
            existing_ids = {s.get("signal_id") for s in load_open_signals()}
            for cand in generate_break_candidates():
                if cand["signal_id"] in existing_ids:
                    continue  # already registered — skip dedup
                save_signal(cand)
                existing_ids.add(cand["signal_id"])
                print(f"  📊 Phase C break signal: {cand['spread_name']}")
                if send_telegram:
                    try:
                        msg = f"📊 PHASE C BREAK\n{cand['spread_name']}\n{cand.get('event_headline', '')}"
                        send_message(msg, parse_mode=None)
                    except Exception as e:
                        print(f"  Failed to send break signal: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("break_signal_generator failed: %s", e)
    print(f"  [trace] break_gen done @ {_ist_now().strftime('%H:%M:%S')}", flush=True)

    # 2. Check existing open signals for stop-outs / expiry
    closed_results = run_signal_monitor()
    print(f"  [trace] monitor done @ {_ist_now().strftime('%H:%M:%S')} ({len(closed_results) if closed_results else 0} closes)", flush=True)
    if closed_results:
        for closed_sig, reason, pnl in closed_results:
            pnl_pct = pnl.get("spread_pnl_pct", 0.0)
            sig_id = closed_sig.get("signal_id", "?")
            spread_name = closed_sig.get("spread_name", closed_sig.get("trade", {}).get("spread_name", "?"))
            tier = closed_sig.get("tier", "SIGNAL")
            _data_levels = closed_sig.get("_data_levels", {})

            if reason == "STOPPED_OUT":
                daily_stop = _data_levels.get("daily_stop")
                todays_move = _data_levels.get("todays_move")
                exit_msg = format_stop_loss_call(
                    signal_id=sig_id,
                    spread_name=spread_name,
                    reason=(
                        f"Daily stop \u2014 today's move {todays_move:+.2f}% "
                        f"breached {daily_stop:+.2f}% threshold"
                        if todays_move is not None and daily_stop is not None
                        else "Daily stop triggered"
                    ),
                    current_pnl_pct=pnl_pct,
                    tier=tier,
                    stop_level=daily_stop,
                )
            elif reason == "STOPPED_OUT_2DAY":
                two_day_stop = _data_levels.get("two_day_stop")
                two_day_combined = _data_levels.get("two_day_combined")
                exit_msg = format_stop_loss_call(
                    signal_id=sig_id,
                    spread_name=spread_name,
                    reason=(
                        f"2-day running stop \u2014 consecutive losses "
                        f"({two_day_combined:+.2f}%) breached {two_day_stop:+.2f}%"
                        if two_day_combined is not None and two_day_stop is not None
                        else "2 consecutive losing days"
                    ),
                    current_pnl_pct=pnl_pct,
                    tier=tier,
                    stop_level=two_day_stop,
                )
            else:
                # Fallback for any legacy close reasons
                exit_msg = format_stop_loss_call(
                    signal_id=sig_id,
                    spread_name=spread_name,
                    reason=reason,
                    current_pnl_pct=pnl_pct,
                    tier=tier,
                )
            print(exit_msg)
            if send_telegram:
                try:
                    send_message(exit_msg, parse_mode=None)
                    print(f"  Sent {reason} call for {sig_id} to Telegram")
                except Exception as e:
                    print(f"  Failed to send exit: {e}")

    # 2b. Send P&L snapshot for open positions every cycle
    open_sigs = load_open_signals()
    if open_sigs and send_telegram:
        try:
            all_tickers = []
            for sig in open_sigs:
                all_tickers += [l["ticker"] for l in sig.get("long_legs", [])]
                all_tickers += [s["ticker"] for s in sig.get("short_legs", [])]
            all_tickers = list(set(all_tickers))

            from signal_tracker import fetch_current_prices, compute_signal_pnl
            print(f"  [trace] snapshot fetch start ({len(all_tickers)} tickers) @ {_ist_now().strftime('%H:%M:%S')}", flush=True)
            prices = fetch_current_prices(all_tickers)
            print(f"  [trace] snapshot fetch done @ {_ist_now().strftime('%H:%M:%S')}", flush=True)

            now = _ist_now()
            lines = [
                "\u2501" * 22,
                f"\U0001f4ca ANKA P&L UPDATE \u2014 {now.strftime('%H:%M IST')}",
                "\u2501" * 22,
            ]
            total_spread_pnl = 0.0
            for sig in open_sigs:
                pnl = compute_signal_pnl(sig, prices)
                emoji = "\U0001f7e2" if pnl["spread_pnl_pct"] >= 0 else "\U0001f534"
                lines.append("")
                lines.append(
                    f"{emoji} {sig['spread_name']}: "
                    f"Spread {pnl['spread_pnl_pct']:+.2f}%"
                )
                # Show per-leg detail with entry prices
                lines.append("\U0001f7e9 LONG:")
                for leg in pnl["long_legs"]:
                    lines.append(
                        f"  {leg['ticker']}: \u20b9{leg['entry']:,.2f} \u2192 "
                        f"\u20b9{leg['current']:,.2f} ({leg['pnl_pct']:+.2f}%)"
                    )
                lines.append("\U0001f7e5 SHORT:")
                for leg in pnl["short_legs"]:
                    # Short P&L: positive = price fell (profit), negative = price rose (loss)
                    move_pct = (leg['current'] / leg['entry'] - 1) * 100
                    lines.append(
                        f"  {leg['ticker']}: \u20b9{leg['entry']:,.2f} \u2192 "
                        f"\u20b9{leg['current']:,.2f} (price {move_pct:+.2f}%, P&L {leg['pnl_pct']:+.2f}%)"
                    )
                total_spread_pnl += pnl["spread_pnl_pct"]

            avg_pnl = total_spread_pnl / len(open_sigs)
            entry_label = "today's open" if open_sigs[0].get("entry_snapped") else "signal time"
            lines.append("")
            lines.append(f"\U0001f4bc Portfolio avg: {avg_pnl:+.2f}% across {len(open_sigs)} spread(s)")
            lines.append(f"\U0001f4cd Entry ref: {entry_label}")

            # Show data-driven stop levels per spread
            from spread_statistics import get_levels_for_spread
            lines.append("")
            lines.append("\U0001f4ca STOP LEVELS (weekly-weighted 1mo):")
            for sig in open_sigs:
                lvl = get_levels_for_spread(sig['spread_name'])
                daily_stop = -(lvl['avg_favorable_move'] * 0.50)
                two_day_stop = daily_stop * 2
                dl = sig.get("_data_levels", {})
                consec = dl.get("consecutive_losses", 0)
                consec_tag = f" \u26a0\ufe0f {consec} losing day(s)" if consec > 0 else ""
                lines.append(
                    f"  {sig['spread_name']}: "
                    f"daily stop {daily_stop:+.2f}% | "
                    f"2-day stop {two_day_stop:+.2f}%{consec_tag}"
                )

            # ── Entry guidance for new watchers (data-driven) ────
            from spread_statistics import classify_entry_zone
            lines.append("")
            lines.append("\U0001f4a1 NEW SUBSCRIBERS \u2014 CAN I ENTER NOW?")
            for sig in open_sigs:
                pnl = compute_signal_pnl(sig, prices)
                spread_now = pnl["spread_pnl_pct"]
                ez = classify_entry_zone(sig['spread_name'], spread_now)

                if ez["zone"] == "ENTER":
                    lines.append(
                        f"  \u2705 {sig['spread_name']}: {ez['reason']}"
                    )
                    lines.append(
                        f"     Buy {'+'.join(l['ticker'] for l in sig.get('long_legs',[]))} "
                        f"/ Sell {'+'.join(s['ticker'] for s in sig.get('short_legs',[]))}"
                    )
                    lines.append(
                        f"     Daily stop: {ez['stop_level']:+.2f}% | Winners run until stopped"
                    )
                elif ez["zone"] == "PARTIAL":
                    lines.append(
                        f"  \u26a0\ufe0f {sig['spread_name']}: {ez['reason']}"
                    )
                    lines.append(
                        f"     Half position \u2014 add on pullback to {ez['entry_level']:+.2f}%"
                    )
                else:
                    lines.append(
                        f"  \u274c {sig['spread_name']}: {ez['reason']}"
                    )
                    lines.append(
                        f"     Wait for retrace to {ez['entry_level']:+.2f}% (weighted 1mo avg)"
                    )

                # Percentile zone warning for late entrants
                if ez.get("percentile_warning"):
                    lines.append(f"     \u26a0\ufe0f {ez['percentile_warning']}")
                elif ez.get("percentile", 50) >= 60:
                    lines.append(
                        f"     \U0001f4cd Spread at {ez['percentile']:.0f}th percentile of 1mo range"
                    )

            lines.append("")
            lines.append("  \u2022 Enter BOTH legs at the same time (equal \u20b9 each side)")
            lines.append("  \u2022 All levels derived from weekly-weighted 1-month data")
            lines.append("  \u2022 Apply OUR \u00b1% stop thresholds to YOUR entry prices")

            # ── On Our Radar: exploring spreads ──────────────────
            # Show what we're watching but hasn't hit SIGNAL tier yet
            import os as _os
            radar_spreads = {}
            sig_dir = str(Path(__file__).parent / "data" / "signals")
            today_str = now.strftime("%Y-%m-%d")
            for fname in sorted(_os.listdir(sig_dir)):
                if not fname.startswith(f"SIG-{today_str}"):
                    continue
                try:
                    raw = json.loads(
                        (Path(sig_dir) / fname).read_text(encoding="utf-8")
                    )
                    for sp in raw.get("spreads", []):
                        sn = sp.get("spread_name", "")
                        tier = sp.get("tier", "")
                        hr = sp.get("hit_rate", 0)
                        # Only show EXPLORING that aren't already active
                        active_names = {s.get("spread_name") for s in open_sigs}
                        if tier == "EXPLORING" and sn not in active_names:
                            if sn not in radar_spreads or hr > radar_spreads[sn]["hit_rate"]:
                                radar_spreads[sn] = {
                                    "hit_rate": hr,
                                    "need": max(0, 0.65 - hr),
                                    "expected": sp.get("expected_1d_spread", 0),
                                }
                except Exception:
                    pass

            if radar_spreads:
                lines.append("")
                lines.append("\U0001f4e1 ON OUR RADAR:")
                for sn, rd in sorted(radar_spreads.items(), key=lambda x: -x[1]["hit_rate"]):
                    lines.append(
                        f"  \U0001f50d {sn}: {rd['hit_rate']:.0%} hit rate "
                        f"(need {rd['need']:.0%} more for signal)"
                    )
                lines.append("  Will alert when conditions are favorable")

            lines.append("\u2501" * 22)

            snapshot = "\n".join(lines)
            try:
                send_message(snapshot, parse_mode=None)
                print("  Sent P&L snapshot to Telegram")
            except Exception as e:
                print(f"  Failed to send P&L snapshot: {e}")
            try:
                print(snapshot)
            except UnicodeEncodeError:
                print(snapshot.encode("ascii", errors="replace").decode("ascii"))
        except Exception as e:
            print(f"  P&L snapshot error: {e}")

    # 3. Midday leaderboard + position update (if in window)
    if _in_midday_window():
        # Send position update
        try:
            portfolio = get_portfolio_snapshot()
            open_positions = portfolio.get("open_positions", [])
            if open_positions:
                update_msg = format_position_update(
                    regime=regime,
                    positions=open_positions,
                    portfolio_pnl_pct=portfolio.get("portfolio_pnl_pct", 0.0),
                    update_time="MIDDAY",
                )
                print(update_msg)
                if send_telegram:
                    try:
                        send_message(update_msg, parse_mode=None)
                        print("  Sent midday position update to Telegram")
                    except Exception as e:
                        print(f"  Failed to send position update: {e}")
        except Exception as e:
            print(f"  Position update error: {e}")

        # Send spread leaderboard
        try:
            from spread_leaderboard import run_midday_leaderboard
            leaderboard = run_midday_leaderboard(regime=regime)
            print(f"\n{leaderboard}")
            if send_telegram:
                try:
                    send_message(leaderboard, parse_mode=None)
                    print("  Sent midday leaderboard to Telegram")
                except Exception as e:
                    print(f"  Failed to send leaderboard: {e}")
        except ImportError:
            print("  spread_leaderboard module not available")
        except Exception as e:
            print(f"  Leaderboard error: {e}")

    # 4. Dashboard summary
    dashboard = get_signal_dashboard()
    if dashboard["total_signals"] > 0:
        print(f"\n  Dashboard: {dashboard['total_signals']} total, "
              f"{dashboard['wins']}W/{dashboard['losses']}L, "
              f"win rate: {dashboard['win_rate_pct']:.0f}%")

    # 5. Check for tier promotions
    promotions = check_tier_promotions()
    if promotions:
        for promo in promotions:
            msg = (
                f"\U0001f389 PROMOTION: {promo['spread_name']} for {promo['category']} "
                f"upgraded from EXPLORING to SIGNAL "
                f"({promo['win_rate']:.0%} win rate, {promo['n_closed']} trades)"
            )
            print(f"  {msg}")
            if send_telegram:
                try:
                    send_message(msg, parse_mode=None)
                except Exception:
                    pass

    return new_signals


def run_eod(send_telegram=False):
    """End-of-day review with enhanced dashboard."""
    holiday = get_holiday_name()
    if holiday:
        print(f"\n[{_ist_now().strftime('%H:%M IST')}] Market closed — {holiday}. No EOD review.")
        return

    print(f"\n[{_ist_now().strftime('%H:%M IST')}] Running EOD review...")

    # Persist closing-price snapshot for tomorrow's daily-stop / 2-day stop math.
    # Without this, _prev_close_long/short never get written and morning regen
    # falls back to entry prices (#97).
    try:
        run_eod_review()
    except Exception as e:
        print(f"  EOD price snapshot failed: {e}")

    # Per-trade post-mortems for today's closes (#30 / C14). Reads
    # closed_signals.json AFTER run_eod_review() has settled the day's
    # closes. Failure-tolerant: one bad row doesn't sink the EOD path.
    try:
        from trade_postmortem import render_today_closes
        closed_path = Path(__file__).parent / "data" / "signals" / "closed_signals.json"
        if closed_path.exists():
            closed = json.loads(closed_path.read_text(encoding="utf-8"))
            today_iso = _ist_now().strftime("%Y-%m-%d")
            written = render_today_closes(closed, today_iso)
            if written:
                print(f"  Wrote {len(written)} post-mortem(s) for today's closes")
    except Exception as e:
        print(f"  Post-mortem render failed: {e}")

    regime = _load_current_regime()
    portfolio = get_portfolio_snapshot()
    cumulative = get_cumulative_pnl()

    eod_text = format_eod_dashboard(
        regime=regime,
        open_positions=portfolio.get("open_positions", []),
        portfolio_pnl=portfolio.get("portfolio_pnl_pct", 0.0),
        cumulative_pnl=cumulative.get("cumulative_pnl_pct", 0.0),
        days_active=cumulative.get("days_active", 0),
        signal_stats=cumulative.get("signal_stats", {}),
        exploring_stats=cumulative.get("exploring_stats", {}),
    )
    print(eod_text)

    if send_telegram:
        try:
            send_message(eod_text, parse_mode=None)
            print("  Sent EOD dashboard to Telegram")
        except Exception as e:
            print(f"  Failed to send EOD: {e}")

    return eod_text


def run_monitor(send_telegram=False):
    """Continuous monitoring loop during market hours."""
    print(f"Signal monitor started. Polling every {POLL_INTERVAL_MINUTES} minutes.")
    print(f"Market hours: {MARKET_HOURS_IST['open']} - {MARKET_HOURS_IST['close']} IST")

    while True:
        if _in_market_hours():
            run_once(send_telegram)

            # EOD at 15:30+ (after last signal check)
            now = _ist_now()
            if now.time() >= datetime.strptime("15:30", "%H:%M").time():
                run_eod(send_telegram)
        else:
            print(f"[{_ist_now().strftime('%H:%M IST')}] Outside market hours. Waiting...")

        time.sleep(POLL_INTERVAL_MINUTES * 60)


_HARD_TIMEOUT_S = 480  # 8 min — beyond this, the cycle is unhealthy and must be killed
                        # so the next scheduled cycle can proceed without a stale lock.


def _arm_hard_timeout(seconds: int = _HARD_TIMEOUT_S) -> None:
    """Schedule a process-wide os._exit() after `seconds`.

    Last-resort defence so a hung downstream call (slow EODHD, hung
    yfinance, Telegram retry storm, etc.) cannot leave the scheduled
    task running for tens of minutes and block subsequent cycles via
    the stale lockfile. Uses a daemon Timer so it does not delay clean
    exits.
    """
    import threading

    def _kill():
        # Release the lock so the next cycle can run.
        try:
            _release_lock()
        except Exception:
            pass
        print(f"  [HARD TIMEOUT] {_ist_now():%H:%M IST} — killing process after {seconds}s")
        sys.stdout.flush()
        os._exit(2)

    t = threading.Timer(seconds, _kill)
    t.daemon = True
    t.start()


def main():
    parser = argparse.ArgumentParser(description="Anka Signal Monitor V2")
    parser.add_argument("--telegram", action="store_true", help="Send signals to Telegram")
    parser.add_argument("--monitor", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--leaderboard", action="store_true", help="Midday leaderboard only")
    parser.add_argument("--eod", action="store_true", help="End-of-day review only")
    args = parser.parse_args()

    # Continuous --monitor mode is intentionally long-lived; only arm the
    # hard timeout for one-shot scheduled cycles.
    if not args.monitor:
        _arm_hard_timeout()

    if args.leaderboard:
        try:
            from spread_leaderboard import run_midday_leaderboard
            regime = _load_current_regime()
            board = run_midday_leaderboard(regime=regime)
            print(board)
            if args.telegram:
                send_message(board, parse_mode=None)
        except ImportError:
            print("spread_leaderboard module not available")
    elif args.eod:
        run_eod(args.telegram)
    elif args.monitor:
        run_monitor(args.telegram)
    else:
        run_once(args.telegram)


if __name__ == "__main__":
    main()
