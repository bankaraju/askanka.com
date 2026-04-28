"""Runner for the Gemma Pilot auto-disable guardrail.

Scheduled hourly during the pilot. Reads:
  - pipeline/data/research/gemma4_pilot/audit/<task>/<date>.jsonl
  - pipeline/data/research/gemma4_pilot/audit/pairwise/<date>.jsonl

Writes (when a floor is breached):
  - pipeline/config/llm_routing.json (24h rubric < 90% → mode=disabled)
  - pipeline/data/research/gemma4_pilot/manual_review/<task>.flag
    (7d pairwise < 40% → human-review flag, no auto-flip)

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md (§4.2)
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 18)
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from pipeline.gemma4_pilot.auto_disable import check_and_apply

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = REPO_ROOT / "pipeline" / "data" / "research" / "gemma4_pilot"
ROUTING_PATH = REPO_ROOT / "pipeline" / "config" / "llm_routing.json"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="[gemma4_auto_disable] %(message)s"
    )
    log = logging.getLogger("gemma4_auto_disable")

    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    today = dt.datetime.now(ist).date().isoformat()

    actions = check_and_apply(AUDIT_ROOT, ROUTING_PATH, today)
    if not actions:
        log.info("no guardrail actions today=%s", today)
    else:
        for a in actions:
            log.warning(
                "guardrail tripped: %s -> %s (%s)",
                a["task"],
                a["action"],
                a["reason"],
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
