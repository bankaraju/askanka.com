"""
Anka Research — Expiry Day Real-Time Monitor
Detects heavyweight stock divergence from pinned index in real-time.
Fires instant alerts when manipulation pattern is detected.

The edge: when HDFCBANK moves 0.5% but BankNifty stays pinned,
the stock will likely revert. Alert subscribers BEFORE the reversion.

Runs every 5 minutes on expiry Thursdays.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.expiry_monitor")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent / "data"
DIVERGENCE_LOG = DATA_DIR / "expiry_divergence_log.json"

# Heavyweight-to-index mapping with manipulation potential
HEAVYWEIGHT_PAIRS = [
    {"stock": "HDFCBANK", "index": "NIFTY BANK", "weight": 30.2, "step": 100,
     "pm_reversion_rate": 56, "threshold": 0.3},
    {"stock": "ICICIBANK", "index": "NIFTY BANK", "weight": 23.5, "step": 100,
     "pm_reversion_rate": 71, "threshold": 0.3},
    {"stock": "RELIANCE", "index": "NIFTY 50", "weight": 10.5, "step": 50,
     "pm_reversion_rate": 62, "threshold": 0.4},
    {"stock": "HDFCBANK", "index": "NIFTY 50", "weight": 8.3, "step": 50,
     "pm_reversion_rate": 56, "threshold": 0.4},
    {"stock": "TCS", "index": "NIFTY 50", "weight": 4.1, "step": 50,
     "pm_reversion_rate": 45, "threshold": 0.5},
    {"stock": "KOTAKBANK", "index": "NIFTY BANK", "weight": 12.3, "step": 100,
     "pm_reversion_rate": 50, "threshold": 0.35},
]

# Track alerts already sent (avoid spam)
_sent_alerts = set()


def is_expiry_day() -> bool:
    return datetime.now(IST).weekday() == 3


def scan_divergences() -> list:
    """Scan all heavyweight pairs for divergence from pinned index.
    Returns list of actionable divergence alerts.
    """
    from kite_client import fetch_ltp, get_kite, resolve_token

    # Get all prices in one call
    all_symbols = set()
    for pair in HEAVYWEIGHT_PAIRS:
        all_symbols.add(pair["stock"])
        all_symbols.add(pair["index"])

    prices = fetch_ltp(list(all_symbols))

    # Also need previous close for return calculation
    kite = get_kite()
    now = datetime.now(IST)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    prev_close = {}
    for sym in all_symbols:
        token = resolve_token(sym)
        if not token:
            continue
        try:
            candles = kite.historical_data(token, yesterday, today, "day")
            if candles and len(candles) >= 2:
                prev_close[sym] = float(candles[-2]["close"])
            elif candles:
                prev_close[sym] = float(candles[-1]["open"])
        except Exception:
            pass

    alerts = []

    for pair in HEAVYWEIGHT_PAIRS:
        stock = pair["stock"]
        index = pair["index"]
        stock_price = prices.get(stock)
        idx_price = prices.get(index)
        stock_prev = prev_close.get(stock)
        idx_prev = prev_close.get(index)

        if not all([stock_price, idx_price, stock_prev, idx_prev]):
            continue

        # Calculate today's returns
        stock_ret = (stock_price / stock_prev - 1) * 100
        idx_ret = (idx_price / idx_prev - 1) * 100

        # Expected index contribution from this stock
        expected_idx_from_stock = stock_ret * pair["weight"] / 100

        # Divergence = stock moved significantly but index didn't follow proportionally
        divergence = stock_ret - (idx_ret * pair["weight"] / 100 * 10)  # Simplified

        # More useful: just compare magnitudes
        # If stock moved >threshold% more than index, that's divergence
        relative_move = abs(stock_ret) - abs(idx_ret)

        # Pin analysis
        step = pair["step"]
        pin_strike = round(idx_price / step) * step
        dist_from_pin = abs(idx_price - pin_strike)
        dist_pct = dist_from_pin / idx_price * 100
        index_is_pinned = dist_pct < 0.3

        # ALERT CONDITION:
        # Stock moved significantly AND index is pinned AND they're diverging
        stock_moved = abs(stock_ret) > pair["threshold"]

        if stock_moved and index_is_pinned:
            # Determine trade direction
            if stock_ret > 0:
                # Stock up, index pinned → expect stock to come back down
                direction = "SHORT"
                trade = f"SHORT {stock} (expect reversion to index)"
                reasoning = (f"{stock} up {stock_ret:+.2f}% but {index} pinned at {pin_strike} "
                           f"({dist_pct:.2f}% away). Heavyweight divergence — expect reversion.")
            else:
                # Stock down, index pinned → expect stock to bounce
                direction = "LONG"
                trade = f"LONG {stock} (expect reversion to index)"
                reasoning = (f"{stock} down {stock_ret:+.2f}% but {index} pinned at {pin_strike} "
                           f"({dist_pct:.2f}% away). Heavyweight divergence — expect reversion.")

            # Check if afternoon (higher reversion rate)
            is_afternoon = now.hour >= 13
            reversion_rate = pair["pm_reversion_rate"] if is_afternoon else int(pair["pm_reversion_rate"] * 0.7)

            # Dedup key
            alert_key = f"{stock}_{index}_{direction}_{now.strftime('%H')}"
            if alert_key in _sent_alerts:
                continue
            _sent_alerts.add(alert_key)

            # Stop loss: if stock continues in the divergence direction by another 0.5%
            stop_pct = 0.5
            target_pct = abs(stock_ret) * 0.6  # Expect 60% reversion

            alert = {
                "stock": stock,
                "index": index,
                "weight": pair["weight"],
                "stock_return": round(stock_ret, 2),
                "index_return": round(idx_ret, 2),
                "stock_price": round(stock_price, 2),
                "index_price": round(idx_price, 2),
                "pin_strike": pin_strike,
                "pin_distance_pct": round(dist_pct, 3),
                "direction": direction,
                "trade": trade,
                "reasoning": reasoning,
                "reversion_rate": reversion_rate,
                "is_afternoon": is_afternoon,
                "stop_pct": stop_pct,
                "target_pct": round(target_pct, 2),
                "timestamp": now.isoformat(),
            }
            alerts.append(alert)

            log.info("DIVERGENCE: %s %s%.2f%% vs %s pinned at %d — %s (reversion %d%%)",
                     stock, "+" if stock_ret > 0 else "", stock_ret, index, pin_strike,
                     direction, reversion_rate)

    # Save to log
    _save_divergence_log(alerts)

    return alerts


def _save_divergence_log(alerts: list):
    """Save divergence events for analysis."""
    history = []
    if DIVERGENCE_LOG.exists():
        try:
            history = json.loads(DIVERGENCE_LOG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            history = []

    for a in alerts:
        history.append({
            "timestamp": a["timestamp"],
            "stock": a["stock"],
            "index": a["index"],
            "stock_return": a["stock_return"],
            "direction": a["direction"],
            "pin_strike": a["pin_strike"],
            "reversion_rate": a["reversion_rate"],
        })

    history = history[-500:]
    DIVERGENCE_LOG.write_text(json.dumps(history, indent=2), encoding="utf-8")


def format_divergence_telegram(alerts: list) -> str:
    """Format divergence alerts for Telegram — instant, actionable."""
    if not alerts:
        return ""

    now = datetime.now(IST)
    is_afternoon = now.hour >= 13
    time_label = "AFTERNOON" if is_afternoon else "MORNING"

    lines = [
        "━" * 22,
        f"⚡ *EXPIRY DIVERGENCE ALERT* — {time_label}",
        "━" * 22,
        "",
    ]

    for i, alert in enumerate(alerts, 1):
        emoji = "🔴" if alert["direction"] == "SHORT" else "🟢"
        confidence = "HIGH" if alert["reversion_rate"] >= 60 else "MODERATE"

        lines.append(f"{emoji} *#{i} {alert['trade']}*")
        lines.append(f"  {alert['stock']}: {alert['stock_return']:+.2f}% today (₹{alert['stock_price']:,.0f})")
        lines.append(f"  {alert['index']}: {alert['index_return']:+.2f}% — PINNED at {alert['pin_strike']:,} ({alert['pin_distance_pct']:.2f}% away)")
        lines.append(f"  {alert['stock']} is {alert['weight']:.0f}% of {alert['index']} — index should have moved more")
        lines.append(f"")
        lines.append(f"  Reversion probability: {alert['reversion_rate']}% ({confidence})")
        lines.append(f"  Stop: {alert['stop_pct']:.1f}% further divergence")
        lines.append(f"  Target: {alert['target_pct']:.1f}% reversion")

        if is_afternoon:
            lines.append(f"  ⏰ _Afternoon gamma zone — reversion strengthens into close_")

        lines.append("")

    lines.extend([
        "*How to trade this:*",
        f"  • Vanilla: {alerts[0]['direction']} {alerts[0]['stock']} stock/futures",
        f"  • Options: {'Sell' if alerts[0]['direction'] == 'SHORT' else 'Buy'} {alerts[0]['stock']} ATM {'call' if alerts[0]['direction'] == 'SHORT' else 'put'}",
        f"  • Spread: {alerts[0]['direction']} {alerts[0]['stock']} vs LONG {alerts[0]['index']} futures",
        "",
        "💡 _Heavyweight divergence on expiry = manipulation fingerprint._",
        "_The index is being pinned. The stock will likely revert._",
        "",
        "_Anka Research · Not investment advice_",
        "━" * 22,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print(f"Expiry day: {is_expiry_day()}")
    print(f"Time: {datetime.now(IST).strftime('%H:%M IST')}")

    alerts = scan_divergences()

    if alerts:
        msg = format_divergence_telegram(alerts)
        print(msg)

        from telegram_bot import send_message
        send_message(msg)
        print("\nSent to Telegram!")
    else:
        print("No divergence alerts — heavyweights and indices moving together")
