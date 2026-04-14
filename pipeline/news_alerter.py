"""
Anka Research — News Alert Formatter + Telegram Sender
Formats classified news events into readable Telegram messages.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

from telegram_bot import send_message

log = logging.getLogger("anka.news_alerter")
IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = _HERE / "data"


def _load_positions() -> list[dict]:
    signals_dir = DATA_DIR / "signals"
    open_file = signals_dir / "open_signals.json"
    if not open_file.exists():
        return []
    try:
        return json.loads(open_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


def _check_position_impact(stocks: list[str], positions: list[dict]) -> str | None:
    for pos in positions:
        pos_stocks = set()
        for leg in pos.get("long_legs", []):
            pos_stocks.add(leg.get("ticker", ""))
        for leg in pos.get("short_legs", []):
            pos_stocks.add(leg.get("ticker", ""))
        overlap = set(stocks) & pos_stocks
        if overlap:
            return f"Your position: {pos.get('spread_name', 'Unknown')} -- {', '.join(overlap)} affected"
    return None


def format_news_alert(event: dict, positions: list[dict] = None) -> str:
    confidence = event.get("confidence", "MEDIUM")
    impact = event.get("impact", "MEDIUM")
    title = event["title"]
    source = event.get("source", "Unknown")
    stocks = event.get("matched_stocks", [])
    categories = event.get("categories", [])

    if impact == "HIGH":
        header = f"NEWS ALERT: [{confidence}] -- {impact} IMPACT"
    else:
        header = f"NEWS: [{confidence}]"

    stocks_str = ", ".join(stocks) if stocks else "Sector-wide"
    cat_str = ", ".join(c.upper().replace("_", " ") for c in categories) if categories else "GENERAL"

    pos_impact = ""
    if positions:
        impact_msg = _check_position_impact(stocks, positions)
        if impact_msg:
            pos_impact = f"\n{impact_msg}"

    msg = (
        f"{header}\n\n"
        f"{title}\n"
        f"Source: {source}\n\n"
        f"Affected: {stocks_str}\n"
        f"Category: {cat_str}"
        f"{pos_impact}\n\n"
        f"Overnight backtest will assess impact by 04:45 AM."
    )
    return msg


def send_news_alerts(events: list[dict]):
    positions = _load_positions()
    for event in events[:5]:
        msg = format_news_alert(event, positions)
        try:
            send_message(msg)
            log.info(f"Alert sent: {event['title'][:60]}")
        except Exception as exc:
            log.warning(f"Telegram failed: {exc}")


if __name__ == "__main__":
    today_file = DATA_DIR / "news_events_today.json"
    if today_file.exists():
        data = json.loads(today_file.read_text(encoding="utf-8"))
        high = [e for e in data.get("events", []) if e["impact"] == "HIGH"]
        print(f"HIGH impact events: {len(high)}")
        for e in high[:3]:
            print(format_news_alert(e))
            print("---")
    else:
        print("No events today. Run news_intelligence.py first.")
