"""EOD runner -- writes today's pilot report card to JSON+MD and posts a
one-line summary to Telegram. Scheduled at 22:00 IST, after all four task
ledgers have accumulated for the day.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 17)
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from pipeline.gemma4_pilot.daily_report import build_report

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="[gemma4_daily_report] %(message)s"
    )
    log = logging.getLogger("gemma4_daily_report")

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    today = dt.datetime.now(ist).date().isoformat()

    report = build_report(AUDIT_ROOT, today, write_files=True)
    log.info("Wrote report card for %s", today)

    # One-line Telegram summary -- best-effort, never block on Telegram down.
    try:
        from pipeline.telegram_client import send_message  # type: ignore
        line = f"Gemma Pilot {today}: "
        for task, m in report["tasks"].items():
            wr = m.get("pairwise_win_rate")
            line += (
                f"{task}={'%.0f%%' % (wr * 100) if wr is not None else '—'}  "
            )
        send_message(line.strip(), channel="ops")
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram post failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
