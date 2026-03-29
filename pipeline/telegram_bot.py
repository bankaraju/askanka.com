"""
Anka Research Pipeline -- Telegram Delivery Module
Sends trading signals, briefings, follow-ups, and dashboards to Telegram.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

log = logging.getLogger("anka.telegram")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)

BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
CHANNEL_ID: Optional[str] = os.getenv("TELEGRAM_CHANNEL_ID")

DISCLAIMER = (
    "\u26a0\ufe0f Not investment advice. Educational/exploratory only. "
    "Past performance \u2260 future results."
)

LINE = "\u2501" * 22  # ━━━━━━━━━━━━━━━━━━━━━━


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_signal_card(signal: Dict[str, Any]) -> str:
    """Format a trading signal dict as a Telegram-friendly message.

    Expected *signal* keys (from political_signals.generate_signal()):
        headline, category, confidence_pct, spread_name,
        long_legs  [{ticker, price}], short_legs [{ticker, price}],
        hit_rate_pct, hit_n, hit_total, expected_1d_spread_pct,
        signal_id
    """
    long_parts = "  +  ".join(
        f"{lg['ticker']} (\u20b9{lg['price']})" for lg in signal.get("long_legs", [])
    )
    short_parts = "  +  ".join(
        f"{sg['ticker']} (\u20b9{sg['price']})" for sg in signal.get("short_legs", [])
    )

    text = (
        f"{LINE}\n"
        f"\U0001f4e1 ANKA SIGNAL \u2014 Exploring an idea...\n"
        f"{LINE}\n"
        f"\n"
        f"\U0001f4f0 Event: {signal.get('headline', 'N/A')}\n"
        f"\U0001f3f7\ufe0f Category: {signal.get('category', 'N/A').upper()} "
        f"(confidence: {signal.get('confidence_pct', 0)}%)\n"
        f"\n"
        f"\U0001f4ca SPREAD: {signal.get('spread_name', 'N/A')}\n"
        f"\U0001f7e2 LONG: {long_parts}\n"
        f"\U0001f534 SHORT: {short_parts}\n"
        f"\n"
        f"\U0001f4c8 Historical: {signal.get('hit_rate_pct', 0)}% hit rate "
        f"({signal.get('hit_n', 0)}/{signal.get('hit_total', 0)} events)\n"
        f"\U0001f3af Expected 1-day spread: +{signal.get('expected_1d_spread_pct', 0)}%\n"
        f"\U0001f6d1 Stop loss: 10% on each leg\n"
        f"\n"
        f"Signal ID: {signal.get('signal_id', 'N/A')}\n"
        f"{DISCLAIMER}\n"
        f"{LINE}"
    )
    return text


def format_premarket_briefing(briefing_text: str) -> str:
    """Wrap a premarket briefing for Telegram.

    The *premarket_scanner* module already formats the text, so we return
    it unchanged (with the disclaimer appended if not already present).
    """
    if DISCLAIMER not in briefing_text:
        return f"{briefing_text}\n\n{DISCLAIMER}"
    return briefing_text


def format_followup_message(
    signal_id: str,
    result: str,
    pnl_pct: float,
    details: str = "",
) -> str:
    """Format a follow-up message for a closed signal.

    *result* must be one of TARGET_HIT, STOPPED_OUT, or EXPIRED.
    """
    detail_line = f"\n{details}" if details else ""

    if result == "TARGET_HIT":
        header = f"\u2705 SIGNAL {signal_id} \u2014 WORKED!"
        pnl_line = f"Spread P&L: +{pnl_pct:.1f}%"
    elif result == "STOPPED_OUT":
        header = f"\U0001f6d1 SIGNAL {signal_id} \u2014 Stopped Out"
        pnl_line = f"Spread P&L: {pnl_pct:+.1f}%"
    elif result == "EXPIRED":
        header = f"\u23f0 SIGNAL {signal_id} \u2014 Expired (5-day window)"
        pnl_line = f"Final P&L: {pnl_pct:+.1f}%"
    else:
        header = f"\u2753 SIGNAL {signal_id} \u2014 {result}"
        pnl_line = f"P&L: {pnl_pct:+.1f}%"

    text = f"{header}\n{pnl_line}{detail_line}\n\n{DISCLAIMER}"
    return text


def format_daily_dashboard(dashboard: Dict[str, Any]) -> str:
    """Format the signal-tracker dashboard for Telegram."""
    best = dashboard.get("best_signal", {})
    worst = dashboard.get("worst_signal", {})

    best_str = (
        f"{best.get('id', 'N/A')} (+{best.get('pnl', 0):.1f}%)" if best else "N/A"
    )
    worst_str = (
        f"{worst.get('id', 'N/A')} ({worst.get('pnl', 0):+.1f}%)" if worst else "N/A"
    )

    text = (
        f"\U0001f4ca ANKA SIGNAL DASHBOARD\n"
        f"{LINE}\n"
        f"Total Signals: {dashboard.get('total_signals', 0)}\n"
        f"Win Rate: {dashboard.get('win_rate_pct', 0):.0f}% "
        f"({dashboard.get('wins', 0)}W / {dashboard.get('losses', 0)}L)\n"
        f"Avg Spread P&L: {dashboard.get('avg_spread_pnl_pct', 0):.1f}%\n"
        f"Best Signal: {best_str}\n"
        f"Worst Signal: {worst_str}\n"
        f"Open Signals: {dashboard.get('open_signals', 0)}\n"
        f"{LINE}\n"
        f"\n{DISCLAIMER}"
    )
    return text


# ---------------------------------------------------------------------------
# Sender helpers
# ---------------------------------------------------------------------------

async def _send_to_chat(bot, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to a single chat/channel, with fallback on parse errors."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        log.info(f"Sent to {chat_id} ({len(text)} chars)")
        return True
    except Exception as e:
        log.warning(f"Send to {chat_id} failed ({e}), retrying without parse_mode")
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as e2:
            log.error(f"Send to {chat_id} retry failed: {e2}")
            return False


async def _send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to private chat AND public channel (async)."""
    from telegram import Bot

    if not BOT_TOKEN or not CHAT_ID:
        log.warning(
            "Telegram not configured. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )
        log.info(f"Would send:\n{text}")
        return False

    bot = Bot(token=BOT_TOKEN)
    success = False

    # Send to private chat
    if CHAT_ID:
        result = await _send_to_chat(bot, CHAT_ID, text, parse_mode)
        success = success or result

    # Also send to public channel
    if CHANNEL_ID:
        result = await _send_to_chat(bot, CHANNEL_ID, text, parse_mode)
        success = success or result

    return success


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Synchronous wrapper around :func:`_send_message`."""
    try:
        return asyncio.run(_send_message(text, parse_mode))
    except Exception as e:
        log.error(f"send_message error: {e}")
        return False


# ---------------------------------------------------------------------------
# Public convenience senders
# ---------------------------------------------------------------------------

def send_signal(signal: Dict[str, Any]) -> bool:
    """Format and send a trading signal."""
    text = format_signal_card(signal)
    return send_message(text)


def send_premarket_briefing(briefing_text: str) -> bool:
    """Send the pre-market morning briefing."""
    text = format_premarket_briefing(briefing_text)
    return send_message(text)


def send_followup(
    signal_id: str, result: str, pnl_pct: float, details: str = ""
) -> bool:
    """Send a follow-up for a closed signal."""
    text = format_followup_message(signal_id, result, pnl_pct, details)
    return send_message(text)


def send_dashboard(dashboard: Dict[str, Any]) -> bool:
    """Send the daily dashboard summary."""
    text = format_daily_dashboard(dashboard)
    return send_message(text)
