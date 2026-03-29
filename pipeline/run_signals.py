"""
Anka Research Pipeline — Signal Monitor
Runs every 30 minutes during IST market hours to detect events and generate signals.

Usage:
    python run_signals.py                      # one-shot: detect + signal + print
    python run_signals.py --telegram           # one-shot + send to Telegram
    python run_signals.py --monitor            # continuous 30-min loop (market hours only)
    python run_signals.py --monitor --telegram # continuous + Telegram delivery
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from political_signals import run_signal_check
from signal_tracker import (
    load_open_signals, check_signal_status, close_signal,
    fetch_current_prices, get_signal_dashboard, run_signal_monitor,
)
from telegram_bot import format_signal_card, format_followup_message, send_message
from config import MARKET_HOURS_IST, POLL_INTERVAL_MINUTES, INDIA_SIGNAL_STOCKS


IST = timezone(timedelta(hours=5, minutes=30))


def _ist_now():
    return datetime.now(IST)


def _in_market_hours():
    now = _ist_now()
    market_open = datetime.strptime(MARKET_HOURS_IST["open"], "%H:%M").time()
    market_close = datetime.strptime(MARKET_HOURS_IST["close"], "%H:%M").time()
    return market_open <= now.time() <= market_close and now.weekday() < 5


def _format_for_telegram(signal):
    """Convert internal signal dict to Telegram card format."""
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


def run_once(send_telegram=False):
    """Single detection + signal generation cycle."""
    print(f"\n[{_ist_now().strftime('%H:%M IST')}] Running signal check...")

    # 1. Detect events and generate new signals
    new_signals = run_signal_check()

    if new_signals:
        print(f"  New signals: {len(new_signals)}")
        for sig in new_signals:
            card_data = _format_for_telegram(sig)
            card = format_signal_card(card_data)
            print(card)

            if send_telegram:
                try:
                    send_message(card)
                    print(f"  Sent {sig['signal_id']} to Telegram")
                except Exception as e:
                    print(f"  Failed to send {sig['signal_id']}: {e}")
    else:
        print("  No new signals")

    # 2. Check existing open signals for stop-outs / expiry
    closed_results = run_signal_monitor()
    if closed_results:
        for closed_sig, reason, pnl in closed_results:
            followup = format_followup_message(
                closed_sig.get("signal_id", "?"),
                reason,
                pnl.get("spread_pnl_pct", 0.0),
            )
            print(followup)
            if send_telegram:
                try:
                    send_message(followup)
                except Exception as e:
                    print(f"  Failed to send followup: {e}")

    # 3. Dashboard summary
    dashboard = get_signal_dashboard()
    if dashboard["total_signals"] > 0:
        print(f"\n  Dashboard: {dashboard['total_signals']} total, "
              f"{dashboard['wins']}W/{dashboard['losses']}L, "
              f"win rate: {dashboard['win_rate_pct']:.0f}%")

    return new_signals


def run_monitor(send_telegram=False):
    """Continuous monitoring loop during market hours."""
    print(f"Signal monitor started. Polling every {POLL_INTERVAL_MINUTES} minutes.")
    print(f"Market hours: {MARKET_HOURS_IST['open']} - {MARKET_HOURS_IST['close']} IST")

    while True:
        if _in_market_hours():
            run_once(send_telegram)
        else:
            print(f"[{_ist_now().strftime('%H:%M IST')}] Outside market hours. Waiting...")

        time.sleep(POLL_INTERVAL_MINUTES * 60)


def main():
    parser = argparse.ArgumentParser(description="Anka Signal Monitor")
    parser.add_argument("--telegram", action="store_true", help="Send signals to Telegram")
    parser.add_argument("--monitor", action="store_true", help="Continuous monitoring mode")
    args = parser.parse_args()

    if args.monitor:
        run_monitor(args.telegram)
    else:
        run_once(args.telegram)


if __name__ == "__main__":
    main()
