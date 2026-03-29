"""
Anka Research Pipeline — Pre-Market Scanner
Runs at 8:30 AM IST to scan Asian markets and generate morning briefing.

Usage:
    python run_premarket.py                    # scan + print briefing
    python run_premarket.py --telegram         # scan + send to Telegram
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from premarket_scanner import fetch_asian_session_data, detect_cascade_signals, generate_premarket_briefing
from telegram_bot import format_premarket_briefing, send_message


def main():
    parser = argparse.ArgumentParser(description="Anka Pre-Market Scanner")
    parser.add_argument("--telegram", action="store_true", help="Send briefing to Telegram")
    args = parser.parse_args()

    print("Scanning Asian markets...")
    data = fetch_asian_session_data()
    signals = detect_cascade_signals(data)
    briefing = generate_premarket_briefing(data, signals)

    # Always print
    print(briefing)

    # Send to Telegram if requested
    if args.telegram:
        formatted = format_premarket_briefing(briefing)
        try:
            send_message(formatted)
            print("\nBriefing sent to Telegram.")
        except Exception as e:
            print(f"\nFailed to send to Telegram: {e}")
            print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in pipeline/.env")


if __name__ == "__main__":
    main()
