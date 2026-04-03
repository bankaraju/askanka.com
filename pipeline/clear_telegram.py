"""
Clear all logged Anka bot messages from Telegram channel + chat.
Run once before subscriber launch for a clean start.

For messages sent BEFORE this script was first run (no log file):
  - Open Telegram, go to the channel, long-press any message
  - Tap "Select All" then delete — or ask @BotFather admins to clear

For messages sent AFTER message logging was added (has log file):
  - This script handles deletion automatically.

Usage:
  python clear_telegram.py           # actually deletes
  python clear_telegram.py --dry-run # preview only
"""

import sys
from pathlib import Path

_lib = str(Path(__file__).parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from telegram_bot import clear_channel_messages

log_file = Path(__file__).parent / "data" / "sent_messages.jsonl"

if not log_file.exists() or log_file.stat().st_size == 0:
    print("No message log found (or empty).")
    print("")
    print("The message logger was just added — it will track all future sends.")
    print("To clear OLD test messages from Telegram:")
    print("  1. Open Telegram desktop / mobile")
    print("  2. Go to your channel")
    print("  3. Select messages > Delete (or use 'Delete all messages' if you own the channel)")
    print("")
    print("Going forward, run this script anytime to wipe the bot's messages cleanly.")
    sys.exit(0)

dry_run = "--dry-run" in sys.argv
n = clear_channel_messages(dry_run=dry_run)

if dry_run:
    print(f"[DRY RUN] Would delete {n} messages")
else:
    print(f"Deleted {n} messages from Telegram channel/chat")
    print("Channel is clean. Ready for subscriber launch.")
