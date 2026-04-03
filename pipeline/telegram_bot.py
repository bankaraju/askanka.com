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
    "\u2139\ufe0f Anka Research provides market analysis and historical pattern data. "
    "This is not financial advice. All levels are derived from historical spread behaviour — "
    "past patterns do not guarantee future outcomes. "
    "Consult a registered financial adviser before acting on any market analysis."
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
        f"\U0001f4ca Levels are data-derived from 1-month spread history\n"
        f"\U0001f6d1 Stop threshold posted with each P&L update (varies by spread volatility)\n"
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
# V2 Formatters — Multi-spread cards, Regime, Portfolio
# ---------------------------------------------------------------------------

from config import UNIT_SIZE_INR, SIGNAL_UNITS, EXPLORING_UNITS, NO_DATA_UNITS

TIER_EMOJI = {
    "SIGNAL": "\U0001f7e2",      # 🟢
    "EXPLORING": "\U0001f7e1",   # 🟡
    "NO_DATA": "\u26aa",         # ⚪
}

TIER_UNITS = {
    "SIGNAL": SIGNAL_UNITS,       # 1.0 unit
    "EXPLORING": EXPLORING_UNITS, # 0.5 unit
    "NO_DATA": NO_DATA_UNITS,     # 0 (paper only)
}

REGIME_EMOJI = {
    "RISK_ON": "\U0001f534",    # 🔴
    "RISK_OFF": "\U0001f7e2",   # 🟢
    "MIXED": "\U0001f7e1",      # 🟡
}


def _inr_pnl(pnl_pct: float, tier: str = "SIGNAL") -> str:
    """Convert a % P&L to ₹ amount based on tier unit size.

    1 unit = ₹10,000 per side. SIGNAL = 1 unit, EXPLORING = 0.5 unit.
    P&L applies to both sides, so effective on the per-side amount.
    """
    units = TIER_UNITS.get(tier, SIGNAL_UNITS)
    if units == 0:
        return "paper"
    inr_amount = (pnl_pct / 100.0) * UNIT_SIZE_INR * units
    if abs(inr_amount) >= 1000:
        return f"\u20b9{inr_amount:+,.0f}"
    return f"\u20b9{inr_amount:+.0f}"


def _tier_size_label(tier: str) -> str:
    """Return human-readable size label for a tier."""
    units = TIER_UNITS.get(tier, 0)
    if units == 0:
        return "paper only"
    inr = int(UNIT_SIZE_INR * units)
    return f"\u20b9{inr:,}/side"


def format_multi_spread_card(signal_card: Dict[str, Any], regime: str = "") -> str:
    """Format a V2 multi-spread signal card for Telegram.

    Only shows SIGNAL-tier spreads (65%+ hit rate) to subscribers.
    EXPLORING/NO_DATA spreads are tracked internally but suppressed
    from the Telegram output to keep the signal clean and actionable.

    Returns None-equivalent empty string if no SIGNAL-tier spreads exist.
    """
    event = signal_card.get("event", {})
    spreads = signal_card.get("spreads", [])
    signal_id = signal_card.get("signal_id", "?")

    # Filter to SIGNAL tier only — subscribers see only validated trades
    signal_spreads = [s for s in spreads if s.get("tier") == "SIGNAL"]
    n_exploring = sum(1 for s in spreads if s.get("tier") == "EXPLORING")

    if not signal_spreads:
        # No SIGNAL-tier spreads — don't send to subscribers
        return ""

    category = event.get("category", "UNKNOWN").upper()
    confidence_pct = int(event.get("confidence", 0) * 100)
    headline = event.get("headline", "N/A")

    regime_str = ""
    if regime:
        r_emoji = REGIME_EMOJI.get(regime, "")
        regime_str = f" | {r_emoji} {regime.replace('_', ' ')} day"

    lines = [
        LINE,
        f"\U0001f4e1 ANKA SIGNAL \u2014 {category}",
        LINE,
        f"\U0001f4f0 {headline}",
        f"\U0001f3f7\ufe0f {category} (confidence: {confidence_pct}%){regime_str}",
        "",
    ]

    for spread in signal_spreads:
        name = spread.get("spread_name", "?")
        hit_rate = spread.get("hit_rate", 0)
        n = spread.get("n_precedents", 0)
        expected = spread.get("expected_1d_spread", 0)
        hit_rate_pct = int(hit_rate * 100)
        hit_n = round(hit_rate * n)

        # Build long/short ticker strings with prices
        long_parts = " + ".join(
            f"{lg['ticker']} (\u20b9{lg.get('price', 0):,.0f})"
            if lg.get("price") else lg["ticker"]
            for lg in spread.get("long_leg", [])
        )
        short_parts = " + ".join(
            f"{sg['ticker']} (\u20b9{sg.get('price', 0):,.0f})"
            if sg.get("price") else sg["ticker"]
            for sg in spread.get("short_leg", [])
        )

        exp_inr = _inr_pnl(expected, "SIGNAL")

        lines.append(f"\U0001f4ca SPREAD: {name}")
        lines.append(f"\U0001f7e2 LONG: {long_parts}")
        lines.append(f"\U0001f534 SHORT: {short_parts}")
        lines.append("")
        lines.append(
            f"\U0001f4c8 Historical: {hit_rate_pct}% hit rate "
            f"({hit_n}/{n} events)"
        )
        lines.append(
            f"\U0001f3af Expected 1-day spread: {expected:+.2f}% ({exp_inr})"
        )
        lines.append("")

    lines.append(f"\U0001f4b0 Size: \u20b9{UNIT_SIZE_INR:,} per side (long + short)")
    lines.append(f"\U0001f6d1 Stop loss: {signal_card.get('risk', {}).get('stop_loss_pct', 10)}% on spread differential | 5-day expiry")

    if n_exploring > 0:
        lines.append(f"\U0001f50d Also tracking {n_exploring} exploring spread(s) internally")

    lines.append(f"\nSignal ID: {signal_id}")
    lines.append(DISCLAIMER)
    lines.append(LINE)

    return "\n".join(lines)


def format_regime_card(
    regime: str,
    regime_score: float,
    open_positions: list,
    flip_from: str = "",
) -> str:
    """Format the regime classification card for Telegram.

    Used in pre-market briefing and on regime flips.
    """
    r_emoji = REGIME_EMOJI.get(regime, "\U0001f7e1")

    lines = [
        LINE,
        f"{r_emoji} REGIME: {regime.replace('_', ' ')}",
        LINE,
    ]

    if flip_from:
        lines.append(f"\u26a0\ufe0f REGIME FLIP: {flip_from.replace('_', ' ')} \u2192 {regime.replace('_', ' ')}")
        lines.append("")

    lines.append(f"Regime score: {regime_score:+.2f}")
    lines.append("")

    if open_positions:
        lines.append("OPEN POSITIONS:")
        for pos in open_positions:
            tier = pos.get("tier", "SIGNAL")
            tier_icon = TIER_EMOJI.get(tier, "\u26aa")
            pnl = pos.get("spread_pnl_pct", 0)
            pnl_inr = _inr_pnl(pnl, tier)
            days = pos.get("days_open", 0)
            name = pos.get("spread_name", "?")
            lines.append(
                f"  {tier_icon} {name}: {pnl:+.2f}% ({pnl_inr}) day {days}/5"
            )
        lines.append("")

    if flip_from:
        lines.append("ACTION:")
        lines.append("  In-the-money trades: trailing stops manage exit")
        lines.append("  Flat/losing trades: consider exit")
        lines.append("  New regime spreads suggested below")
    else:
        lines.append("Hold current positions. Trailing stops active.")

    lines.append(LINE)
    return "\n".join(lines)


def format_eod_dashboard(
    regime: str,
    open_positions: list,
    portfolio_pnl: float,
    cumulative_pnl: float,
    days_active: int,
    signal_stats: Dict[str, Any],
    exploring_stats: Dict[str, Any],
) -> str:
    """Format the enhanced EOD dashboard with regime + portfolio P&L.

    All P&L shown in both % and ₹ terms using consistent unit sizing.
    """
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    r_emoji = REGIME_EMOJI.get(regime, "\U0001f7e1")

    lines = [
        LINE,
        f"\U0001f4ca ANKA EOD \u2014 {now.strftime('%d %b %Y')}",
        LINE,
        f"{r_emoji} REGIME: {regime.replace('_', ' ')}",
        f"\U0001f4b0 Unit: \u20b9{UNIT_SIZE_INR:,}/side | SIGNAL=1x | EXPLORING=0.5x",
        "",
    ]

    if open_positions:
        lines.append("OPEN POSITIONS:")
        for pos in open_positions:
            tier = pos.get("tier", "SIGNAL")
            tier_icon = TIER_EMOJI.get(tier, "\u26aa")
            pnl = pos.get("spread_pnl_pct", 0)
            pnl_inr = _inr_pnl(pnl, tier)
            days = pos.get("days_open", 0)
            name = pos.get("spread_name", "?")
            lines.append(f"  {tier_icon} {name}: {pnl:+.2f}% ({pnl_inr}) day {days}/5")
        lines.append("")

    # Portfolio P&L in ₹ (weighted across all positions)
    # Use SIGNAL units for portfolio-level since it's a blend
    portfolio_inr = _inr_pnl(portfolio_pnl, "SIGNAL")
    cumulative_inr = _inr_pnl(cumulative_pnl, "SIGNAL")
    lines.append(f"TODAY'S P&L: {portfolio_pnl:+.2f}% ({portfolio_inr})")
    lines.append(f"CUMULATIVE: {cumulative_pnl:+.2f}% ({cumulative_inr}) over {days_active} days")
    lines.append("")

    # Signal vs Exploring breakdown
    sig_w = signal_stats.get("wins", 0)
    sig_l = signal_stats.get("losses", 0)
    sig_avg = signal_stats.get("avg_pnl", 0)
    sig_avg_inr = _inr_pnl(sig_avg, "SIGNAL")
    exp_w = exploring_stats.get("wins", 0)
    exp_l = exploring_stats.get("losses", 0)
    exp_avg = exploring_stats.get("avg_pnl", 0)
    exp_avg_inr = _inr_pnl(exp_avg, "EXPLORING")

    lines.append("SIGNAL vs EXPLORING:")
    lines.append(f"  \U0001f7e2 SIGNAL trades: {sig_w}W / {sig_l}L | avg {sig_avg:+.2f}% ({sig_avg_inr})")
    lines.append(f"  \U0001f7e1 EXPLORING trades: {exp_w}W / {exp_l}L | avg {exp_avg:+.2f}% ({exp_avg_inr})")
    lines.append("")

    # Anka success rate
    total_closed = sig_w + sig_l + exp_w + exp_l
    total_wins = sig_w + exp_w
    if total_closed > 0:
        success_rate = (total_wins / total_closed) * 100
        lines.append(f"\U0001f3af ANKA SUCCESS RATE: {success_rate:.0f}% ({total_wins}/{total_closed} trades)")
    else:
        lines.append(f"\U0001f3af ANKA SUCCESS RATE: Tracking started")
    lines.append("")

    lines.append("REGIME OUTLOOK:")
    lines.append("  Hold current positions. Trailing stops active.")
    lines.append("  Watch for: ceasefire/diplomacy headlines \u2192 regime flip risk.")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append(LINE)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service Call Formatters — ENTRY, STOP LOSS, EXIT, ALERT, UPDATE
# ---------------------------------------------------------------------------

def format_entry_call(
    signal_id: str,
    category: str,
    spread_name: str,
    long_tickers: list,
    short_tickers: list,
    hit_rate_pct: float,
    expected_spread_pct: float,
    stock_probs: list = None,
    regime: str = "",
    data_levels: dict = None,
) -> str:
    """Format an ENTRY service call with data-driven levels.

    *data_levels*: {entry_level, stop_level, daily_std, avg_favorable_move, cum_percentile}
    from spread_statistics. If None, levels are fetched automatically.
    """
    # Fetch data-driven levels if not provided
    if data_levels is None:
        try:
            from spread_statistics import get_levels_for_spread
            data_levels = get_levels_for_spread(spread_name)
        except Exception:
            data_levels = {"entry_level": 0, "stop_level": -1.5,
                           "daily_std": 2.0, "avg_favorable_move": 2.0,
                           "cum_percentile": 50.0}

    stop = data_levels.get("stop_level", -1.5)
    entry = data_levels.get("entry_level", 0)
    daily_std = data_levels.get("daily_std", 2.0)

    r_emoji = REGIME_EMOJI.get(regime, "")
    regime_tag = f" | {r_emoji} {regime.replace('_', ' ')}" if regime else ""

    long_str = " + ".join(long_tickers)
    short_str = " + ".join(short_tickers)

    lines = [
        LINE,
        f"\U0001f4e2 ANKA ENTRY CALL",
        LINE,
        f"\U0001f3f7\ufe0f {category.upper()}{regime_tag}",
        "",
        f"\U0001f4ca SPREAD: {spread_name}",
        f"\U0001f7e2 LONG: {long_str}",
        f"\U0001f534 SHORT: {short_str}",
        "",
        f"\U0001f4c8 Hit rate: {hit_rate_pct:.0f}% | Expected: {expected_spread_pct:+.2f}%",
        f"\U0001f4b0 Size: \u20b9{UNIT_SIZE_INR:,}/side",
    ]

    # ── DATA-DRIVEN LEVELS section ──────────────────────
    avg_favorable = data_levels.get("avg_favorable_move", 2.0)
    daily_stop_level = -(avg_favorable * 0.50)
    two_day_stop_level = daily_stop_level * 2
    lines.append("")
    lines.append("\U0001f4ca DATA-DRIVEN LEVELS (weekly-weighted 1mo):")
    lines.append(f"  \U0001f3e0 Entry fair value:     {entry:+.2f}% (weighted 1mo avg)")
    lines.append(f"  \U0001f6d1 Daily stop:           {stop:+.2f}% (50% of avg daily move)")
    lines.append(f"  \U0001f6d1 2-day stop:           {two_day_stop_level:+.2f}% (2 \u00d7 daily stop)")
    lines.append(f"  \U0001f4cf Daily volatility:     \u00b1{daily_std:.2f}%")
    lines.append(f"  \u267b\ufe0f No target exit \u2014 winners run until stopped out")
    lines.append(f"  \U0001f4c5 Last week data weighted 4x vs first week")

    if stock_probs:
        lines.append("")
        lines.append("\U0001f52c STOCK PROBABILITY RANKING:")
        for sp in stock_probs:
            arrow = "\u2191" if sp.get("median_move_pct", 0) >= 0 else "\u2193"
            lines.append(
                f"  {sp['ticker']}: {sp.get('prob_up_pct', 0):.0f}% prob {arrow} "
                f"(median {sp.get('median_move_pct', 0):+.1f}%) \u2014 {sp.get('driver', '')}"
            )

    # ── HOW TO TRADE section ──────────────────────────
    daily_stop = -(data_levels.get("avg_favorable_move", 2.0) * 0.50)
    two_day_stop = daily_stop * 2
    lines.append("")
    lines.append("\u2699\ufe0f HOW TO TRADE:")
    lines.append("  1\ufe0f\u20e3 Enter BOTH legs simultaneously at market")
    lines.append("  2\ufe0f\u20e3 Equal \u20b9 on each side | Do NOT stop individual legs")
    lines.append(f"  3\ufe0f\u20e3 Daily stop: {stop:+.2f}% | 2-day stop: {two_day_stop:+.2f}%")
    lines.append("  4\ufe0f\u20e3 No target exit \u2014 winners run until stopped")
    lines.append("  5\ufe0f\u20e3 We send exit alerts when stop thresholds are breached")
    lines.append("")
    lines.append("\u26a0\ufe0f YOUR ENTRY PRICE WILL DIFFER FROM OURS")
    lines.append("  Our P&L is from signal-time open prices.")
    lines.append("  Use OUR stop levels (\u00b1% thresholds) but apply")
    lines.append("  them to YOUR entry prices. The % move thresholds")
    lines.append("  are the same \u2014 your base price is different.")

    lines.append("")
    lines.append(f"Signal ID: {signal_id}")
    lines.append(DISCLAIMER)
    lines.append(LINE)
    return "\n".join(lines)


def format_stop_loss_call(
    signal_id: str,
    spread_name: str,
    reason: str,
    current_pnl_pct: float,
    tier: str = "SIGNAL",
    stop_level: float = None,
) -> str:
    """Format a STOP LOSS / EXIT NOW call — data-driven stop hit."""
    pnl_inr = _inr_pnl(current_pnl_pct, tier)

    stop_str = f" (data-driven stop: {stop_level:+.2f}%)" if stop_level is not None else ""

    lines = [
        LINE,
        f"\U0001f6a8 ANKA STOP LOSS \u2014 EXIT NOW",
        LINE,
        "",
        f"\U0001f4ca {spread_name}",
        f"\u274c Reason: {reason}{stop_str}",
        f"\U0001f4c9 Current P&L: {current_pnl_pct:+.2f}% ({pnl_inr})",
        "",
        f"\u26a1 ACTION: Close both legs immediately",
        "",
        f"Signal ID: {signal_id}",
        DISCLAIMER,
        LINE,
    ]
    return "\n".join(lines)


def format_exit_call(
    signal_id: str,
    spread_name: str,
    exit_type: str,
    final_pnl_pct: float,
    tier: str = "SIGNAL",
    days_held: int = 0,
) -> str:
    """Format an EXIT call — target hit, trailing stop, or expiry.

    *exit_type*: TARGET_HIT, TRAILING_STOP, EXPIRED
    """
    pnl_inr = _inr_pnl(final_pnl_pct, tier)

    if exit_type == "TARGET_HIT":
        header = "\u2705 ANKA EXIT \u2014 TARGET HIT"
    elif exit_type == "TRAILING_STOP":
        header = "\U0001f3c1 ANKA EXIT \u2014 TRAILING STOP"
    else:
        header = "\u23f0 ANKA EXIT \u2014 EXPIRED"

    lines = [
        LINE,
        header,
        LINE,
        "",
        f"\U0001f4ca {spread_name}",
        f"\U0001f4b0 Final P&L: {final_pnl_pct:+.2f}% ({pnl_inr})",
        f"\U0001f4c5 Held: {days_held} day(s)",
        "",
        f"Signal ID: {signal_id}",
        DISCLAIMER,
        LINE,
    ]
    return "\n".join(lines)


def format_alert(
    alert_type: str,
    headline: str,
    details: str = "",
    action: str = "",
) -> str:
    """Format a mid-day ALERT — regime flip, correlation break, breaking news.

    *alert_type*: REGIME_FLIP, CORRELATION_BREAK, BREAKING_NEWS
    """
    if alert_type == "REGIME_FLIP":
        icon = "\u26a0\ufe0f"
        title = "REGIME FLIP ALERT"
    elif alert_type == "CORRELATION_BREAK":
        icon = "\U0001f4a5"
        title = "CORRELATION BREAK"
    else:
        icon = "\U0001f4e3"
        title = "BREAKING ALERT"

    lines = [
        LINE,
        f"{icon} ANKA {title}",
        LINE,
        "",
        f"\U0001f4f0 {headline}",
    ]

    if details:
        lines.append(f"\U0001f4cb {details}")

    if action:
        lines.append("")
        lines.append(f"\u26a1 ACTION: {action}")

    lines.append("")
    lines.append(DISCLAIMER)
    lines.append(LINE)
    return "\n".join(lines)


def format_position_update(
    regime: str,
    positions: list,
    portfolio_pnl_pct: float,
    update_time: str = "MIDDAY",
) -> str:
    """Format a midday UPDATE with all open positions and P&L.

    *positions*: list of dicts with keys: spread_name, tier, pnl_pct, days_open, long_move, short_move
    """
    r_emoji = REGIME_EMOJI.get(regime, "\U0001f7e1")
    portfolio_inr = _inr_pnl(portfolio_pnl_pct, "SIGNAL")

    lines = [
        LINE,
        f"\U0001f4cb ANKA {update_time} UPDATE",
        LINE,
        f"{r_emoji} REGIME: {regime.replace('_', ' ')}",
        "",
        "OPEN POSITIONS:",
    ]

    for i, pos in enumerate(positions, 1):
        tier = pos.get("tier", "SIGNAL")
        tier_icon = TIER_EMOJI.get(tier, "\u26aa")
        pnl = pos.get("spread_pnl_pct", pos.get("pnl_pct", 0))
        pnl_inr = _inr_pnl(pnl, tier)
        days = pos.get("days_open", 0)
        name = pos.get("spread_name", "?")
        long_move = pos.get("long_move", "")
        short_move = pos.get("short_move", "")

        lines.append(f"  #{i} {tier_icon} {name}: {pnl:+.2f}% ({pnl_inr}) day {days}/5")
        if long_move or short_move:
            lines.append(f"     Long {long_move} | Short {short_move}")

    lines.append("")
    lines.append(f"\U0001f4b0 PORTFOLIO: {portfolio_pnl_pct:+.2f}% ({portfolio_inr})")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append(LINE)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sender helpers (using direct HTTP API for reliability)
# ---------------------------------------------------------------------------

import requests as _requests

_TELEGRAM_API = "https://api.telegram.org"
_SEND_TIMEOUT = 15  # seconds


def _send_to_chat_http(chat_id: str, text: str, parse_mode: Optional[str] = None) -> bool:
    """Send a message to a single chat/channel via Telegram HTTP API."""
    if not BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set")
        return False

    url = f"{_TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = _requests.post(url, json=payload, timeout=_SEND_TIMEOUT)
        if resp.ok:
            log.info(f"Sent to {chat_id} ({len(text)} chars)")
            try:
                msg_id = resp.json().get("result", {}).get("message_id")
                if msg_id:
                    _log_sent_message(chat_id, msg_id)
            except Exception:
                pass
            return True
        else:
            # If parse_mode failed, retry without it
            if parse_mode:
                log.warning(f"Send to {chat_id} failed ({resp.status_code}), retrying without parse_mode")
                payload.pop("parse_mode", None)
                resp2 = _requests.post(url, json=payload, timeout=_SEND_TIMEOUT)
                if resp2.ok:
                    log.info(f"Sent to {chat_id} (no parse_mode, {len(text)} chars)")
                    try:
                        msg_id = resp2.json().get("result", {}).get("message_id")
                        if msg_id:
                            _log_sent_message(chat_id, msg_id)
                    except Exception:
                        pass
                    return True
            log.error(f"Send to {chat_id} failed: {resp.status_code} {resp.text[:200]}")
            return False
    except _requests.Timeout:
        log.error(f"Send to {chat_id} timed out after {_SEND_TIMEOUT}s")
        return False
    except Exception as e:
        log.error(f"Send to {chat_id} error: {e}")
        return False


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message to private chat AND public channel.

    Uses direct HTTP API calls instead of python-telegram-bot library
    for reliability (the library has timeout issues in some environments).
    """
    if not BOT_TOKEN:
        log.warning("Telegram not configured. Set TELEGRAM_BOT_TOKEN in .env")
        log.info(f"Would send:\n{text}")
        return False

    success = False

    # Send to private chat
    if CHAT_ID:
        result = _send_to_chat_http(CHAT_ID, text, parse_mode)
        success = success or result

    # Also send to public channel
    if CHANNEL_ID:
        result = _send_to_chat_http(CHANNEL_ID, text, parse_mode)
        success = success or result

    return success


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


def send_entry_call(**kwargs) -> bool:
    """Format and send an ENTRY service call."""
    text = format_entry_call(**kwargs)
    return send_message(text)


def send_stop_loss_call(**kwargs) -> bool:
    """Format and send a STOP LOSS service call."""
    text = format_stop_loss_call(**kwargs)
    return send_message(text)


def send_exit_call(**kwargs) -> bool:
    """Format and send an EXIT service call."""
    text = format_exit_call(**kwargs)
    return send_message(text)


def send_alert(**kwargs) -> bool:
    """Format and send a mid-day ALERT."""
    text = format_alert(**kwargs)
    return send_message(text)


def send_position_update(**kwargs) -> bool:
    """Format and send a position UPDATE."""
    text = format_position_update(**kwargs)
    return send_message(text)


# ---------------------------------------------------------------------------
# Component A — Daily EOD Track Record (Signal Universe v2)
# ---------------------------------------------------------------------------

def format_eod_track_record(
    date_str: str,
    open_positions: list,
    closed_this_week: list,
    scorecard: dict,
    macro_line: str = "",
    fii_line: str = "",
    institutional_data: dict = None,
) -> str:
    """Format the daily client track record.

    Section 1 — Open Positions
    Section 2 — Closed This Week
    Section 3 — Running Scorecard
    Section 4 — Macro Context
    """
    from datetime import datetime
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%d %b %Y")
    except Exception:
        date_display = date_str

    lines = [f"📋 *ANKA DAILY RECORD — {date_display}*", ""]

    # ── Section 1: Open Positions ──────────────────────────────────────
    if open_positions:
        lines.append("*OPEN POSITIONS*")
        for pos in open_positions:
            badge = pos.get("tier_badge", "🔵")
            name = pos.get("spread_name", "?")
            days = pos.get("days_held", 1)
            sp = pos.get("spread_pnl_pct", 0.0)
            em = pos.get("pnl_emoji", "⚪")
            stop = pos.get("daily_stop")
            entry = pos.get("entry_date", "?")

            lines.append(f"{badge} *{name}*  (Day {days}, entry {entry})")
            lines.append(f"  Spread P&L: {em} {sp:+.2f}%")
            if stop:
                lines.append(f"  Daily stop: {stop:+.2f}%")
            if pos.get("corr_break"):
                lines.append("  ⚠️ CORR BREAK: both baskets falling — market selloff, not spread")

            # Leg detail
            longs = pos.get("long_legs", [])
            shorts = pos.get("short_legs", [])
            if longs:
                long_str = "  📈 Long: " + " | ".join(
                    f"{l['ticker']} Rs{l['current']:,.0f}" for l in longs
                )
                lines.append(long_str)
            if shorts:
                short_str = "  📉 Short: " + " | ".join(
                    f"{s['ticker']} Rs{s['current']:,.0f}" for s in shorts
                )
                lines.append(short_str)
            lines.append("")
    else:
        lines.append("*OPEN POSITIONS*")
        lines.append("  No open positions today")
        lines.append("")

    # ── Section 2: Closed This Week ───────────────────────────────────
    if closed_this_week:
        lines.append("*CLOSED THIS WEEK*")
        for c in closed_this_week:
            sp = c.get("spread_pnl_pct", 0.0)
            lines.append(
                f"{c['result_badge']}  {c['spread_name']}  {sp:+.2f}%  "
                f"({c['days_held']}d, {c['exit_label']})"
            )
        lines.append("")

    # ── Section 3: Running Scorecard ──────────────────────────────────
    lines.append("*RUNNING SCORECARD*")
    strip = scorecard.get("strip", "")
    if strip:
        lines.append(f"  {strip}  (🔷 open  🟩 win  🟥 loss)")
    else:
        lines.append("  No completed signals yet")

    sig_s = scorecard.get("signal_stats", {})
    exp_s = scorecard.get("exploring_stats", {})
    total_open   = scorecard.get("total_open", 0)
    total_closed = scorecard.get("total_closed", 0)
    wr = scorecard.get("win_rate_pct", 0.0)

    # Open position P&L by tier (passed in via scorecard)
    open_signal_pnls    = scorecard.get("open_signal_pnls", [])
    open_exploring_pnls = scorecard.get("open_exploring_pnls", [])

    sig_open_n   = len(open_signal_pnls)
    exp_open_n   = len(open_exploring_pnls)
    sig_closed_n = sig_s.get("wins", 0) + sig_s.get("losses", 0)
    exp_closed_n = exp_s.get("wins", 0) + exp_s.get("losses", 0)

    # SIGNAL row
    sig_open_str = ""
    if sig_open_n > 0:
        avg_open = sum(open_signal_pnls) / sig_open_n
        sig_open_str = f"  {sig_open_n} open (avg {avg_open:+.1f}%)"
    if sig_closed_n > 0:
        lines.append(
            f"  🔵 SIGNAL:{sig_open_str}  |  "
            f"{sig_s.get('wins', 0)}W / {sig_s.get('losses', 0)}L closed  "
            f"avg {sig_s.get('avg_pnl', 0):+.1f}%"
        )
    else:
        lines.append(f"  🔵 SIGNAL:{sig_open_str if sig_open_str else '  none yet'}")

    # EXPLORING row
    exp_open_str = ""
    if exp_open_n > 0:
        avg_open = sum(open_exploring_pnls) / exp_open_n
        exp_open_str = f"  {exp_open_n} open (avg {avg_open:+.1f}%)"
    if exp_closed_n > 0:
        lines.append(
            f"  🟡 EXPLORING:{exp_open_str}  |  "
            f"{exp_s.get('wins', 0)}W / {exp_s.get('losses', 0)}L closed  "
            f"avg {exp_s.get('avg_pnl', 0):+.1f}%"
        )
    else:
        lines.append(f"  🟡 EXPLORING:{exp_open_str if exp_open_str else '  none yet'}")

    if total_closed > 0:
        lines.append(f"  Overall: {wr:.0f}% win rate | {total_closed} closed | {total_open} open")
    else:
        lines.append(f"  Win rate tracked once positions close")
    lines.append("")

    # ── Section 4: Macro Context ──────────────────────────────────────
    if macro_line or fii_line or institutional_data:
        lines.append("*MACRO CONTEXT*")
        if macro_line:
            lines.append(f"  {macro_line}")
        if institutional_data:
            fii = institutional_data.get("fii_net", 0)
            dii = institutional_data.get("dii_net", 0)
            lines.append(f"  📊 Inst. Flow: FII ₹{fii:+,.0f} cr | DII ₹{dii:+,.0f} cr")
            if fii < 0 and abs(fii) > 0:
                ratio = abs(dii) / abs(fii)
                if ratio > 1.0:
                    ratio_emoji = "🟢"
                    ratio_label = "DII offsetting"
                elif ratio >= 0.5:
                    ratio_emoji = "🟡"
                    ratio_label = "partial support"
                else:
                    ratio_emoji = "🔴"
                    ratio_label = "no domestic support"
                lines.append(f"  Ratio: {ratio:.2f}x {ratio_emoji} ({ratio_label})")
        elif fii_line:
            lines.append(f"  {fii_line}")
        lines.append("")

    lines.append(
        "_Anka Research · Spread signals for Indian equities_\n"
        "_Not investment advice. For information only._"
    )
    return "\n".join(lines)


def send_eod_track_record(**kwargs) -> bool:
    """Format and send the daily EOD track record."""
    text = format_eod_track_record(**kwargs)
    return send_message(text)


# ---------------------------------------------------------------------------
# Channel management
# ---------------------------------------------------------------------------

def _log_sent_message(chat_id: str, message_id: int) -> None:
    """Persist a sent message ID to data/sent_messages.jsonl for later deletion."""
    from pathlib import Path as _Path
    log_file = _Path(__file__).parent / "data" / "sent_messages.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with log_file.open("a", encoding="utf-8") as f:
        f.write(_json.dumps({"chat_id": chat_id, "message_id": message_id}) + "\n")


def clear_channel_messages(dry_run: bool = False) -> int:
    """Delete all bot messages logged in data/sent_messages.jsonl.

    Telegram bots can only delete their own messages. This function replays
    the log of message IDs we recorded at send time and deletes each one.

    Args:
        dry_run: If True, print what would be deleted without actually deleting.

    Returns:
        Number of messages successfully deleted (or would-delete in dry_run).
    """
    import json as _json
    from pathlib import Path as _Path

    if not BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — cannot clear messages")
        return 0

    log_file = _Path(__file__).parent / "data" / "sent_messages.jsonl"
    if not log_file.exists():
        log.info("No sent_messages.jsonl found — nothing to clear")
        return 0

    records = []
    with log_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(_json.loads(line))
                except Exception:
                    pass

    if not records:
        log.info("sent_messages.jsonl is empty — nothing to clear")
        return 0

    deleted = 0
    failed = []
    for rec in records:
        chat_id = rec.get("chat_id")
        msg_id = rec.get("message_id")
        if not chat_id or not msg_id:
            continue
        if dry_run:
            log.info("[DRY RUN] Would delete message %d from %s", msg_id, chat_id)
            deleted += 1
            continue
        try:
            url = f"{_TELEGRAM_API}/bot{BOT_TOKEN}/deleteMessage"
            resp = _requests.post(
                url, json={"chat_id": chat_id, "message_id": msg_id}, timeout=10
            )
            if resp.ok:
                deleted += 1
            else:
                # Message may already be deleted or too old — not critical
                log.debug("Could not delete message %d from %s: %s", msg_id, chat_id, resp.text[:100])
                failed.append(msg_id)
        except Exception as exc:
            log.warning("Error deleting message %d: %s", msg_id, exc)
            failed.append(msg_id)

    if not dry_run:
        # Clear the log file — successfully deleted + silently failed (already gone)
        log_file.write_text("", encoding="utf-8")
        log.info("Cleared channel: %d deleted, %d already gone/failed", deleted, len(failed))

    return deleted


# ---------------------------------------------------------------------------
# Component B — Macro Signal Card (Signal Universe v2)
# ---------------------------------------------------------------------------

def format_macro_signal_card(
    msi: dict,
    regime: str,
    top_spreads: list,
    crossing: str = "NEUTRAL_TO_STRESS",
    institutional_data: dict = None,
) -> str:
    """Format a macro regime crossing signal card.

    Fires once when MSI crosses from NEUTRAL → STRESS.
    """
    from macro_stress import msi_bar, regime_emoji
    score = msi.get("msi_score", 0)
    timestamp = msi.get("timestamp", "")[:16].replace("T", " ")

    lines = [
        f"📊 *MACRO SIGNAL — STRESS REGIME*",
        f"_{timestamp} IST_",
        "",
        msi_bar(score, regime),
    ]

    if institutional_data:
        fii = institutional_data.get("fii_net", 0)
        dii = institutional_data.get("dii_net", 0)
        ratio_str = ""
        if fii < 0 and abs(fii) > 0:
            ratio = abs(dii) / abs(fii)
            ratio_emoji = "🟢" if ratio > 1.0 else ("🟡" if ratio >= 0.5 else "🔴")
            ratio_str = f" | Ratio: {ratio:.2f}x {ratio_emoji}"
        lines.append(f"    📊 Inst. Flow: FII ₹{fii:+,.0f} cr | DII ₹{dii:+,.0f} cr{ratio_str}")

    lines.extend(["", "*Why stress is elevated:*"])

    comps = msi.get("components", {})
    comp_labels = {
        "inst_flow":  "Institutional flows",
        "india_vix":  "India VIX",
        "usdinr":     "USD/INR",
        "nifty_30d":  "Nifty 30d",
        "crude_5d":   "Crude 5d",
    }
    for key, label in comp_labels.items():
        c = comps.get(key, {})
        norm = c.get("norm", 0)
        contrib = c.get("contribution", 0)
        raw = c.get("raw")
        if norm >= 0.6:  # only highlight elevated components
            raw_str = f" ({raw})" if raw is not None else ""
            lines.append(f"  🔺 {label}{raw_str} → stress contribution {contrib:.0f}/100")

    if top_spreads:
        lines.append("")
        lines.append("*Spreads with best STRESS-regime track record:*")
        for sp in top_spreads:
            wr = sp.get("win_rate", 0)
            n = sp.get("n", 0)
            avg = sp.get("avg_return", 0)
            lines.append(
                f"  📌 *{sp['spread_name']}*  "
                f"{wr:.0%} win rate | avg {avg:+.1f}% | {n} data pts"
            )

    lines.extend([
        "",
        "⚠️ _Macro stress signals are EXPLORING tier — half-unit position sizing_",
        "_We send exit alerts when stop thresholds are breached_",
        "",
        "_Anka Research · Not investment advice_",
    ])
    return "\n".join(lines)


def send_macro_signal_card(**kwargs) -> bool:
    """Format and send a macro signal card."""
    text = format_macro_signal_card(**kwargs)
    return send_message(text)
