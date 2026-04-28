"""Watchdog CLI entry point — orchestrates inventory → scheduler → freshness → drift → alerts.

Usage:
    python pipeline/watchdog.py --all                  # gate-run: every task + drift
    python pipeline/watchdog.py --tier critical        # intraday: critical tier only
    python pipeline/watchdog.py --all --dry-run        # shadow-mode: digest to stdout instead of Telegram
"""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

# Windows console defaults to cp1252 which can't encode the digest emojis.
# Reconfigure stdout/stderr to UTF-8 so --dry-run print() and log handlers work.
# (Telegram path is already UTF-8; this only matters for local stdout.)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

from pipeline.watchdog_alerts import (
    Issue,
    IssueKind,
    build_digest,
    load_state,
    save_state,
    send_or_log_digest,
    update_state,
)
from pipeline.watchdog_freshness import (
    IST,
    FreshnessResult,
    check_file_freshness,
    expand_output_template,
)
from pipeline.watchdog_inventory import (
    InventoryError,
    load_inventory,
)
from pipeline.watchdog_scheduler import (
    SchedulerQueryError,
    TaskLivenessResult,
    check_drift,
    check_task_liveness,
    query_anka_tasks,
)

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_PATH = REPO_ROOT / "pipeline" / "config" / "anka_inventory.json"
STATE_PATH = REPO_ROOT / "pipeline" / "data" / "watchdog_state.json"
LOG_PATH = REPO_ROOT / "pipeline" / "logs" / "watchdog.log"
ALERT_FALLBACK_PATH = REPO_ROOT / "pipeline" / "logs" / "watchdog_alerts.log"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[
        RotatingFileHandler(LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("anka.watchdog")


def _fail_inventory(reason: str, now_iso: str, dry_run: bool) -> None:
    """Inventory missing/malformed → emergency alert + exit 1."""
    emergency = f"🚨 Anka Watchdog EMERGENCY {now_iso[:16]}\ninventory problem: {reason}\nskipping this run"
    log.error("INVENTORY FAIL: %s", reason)
    send_or_log_digest(emergency, ALERT_FALLBACK_PATH, dry_run=dry_run)
    sys.exit(1)


def _filter_tasks_by_tier(inventory: dict, tier_filter):
    if tier_filter is None:
        return inventory["tasks"]
    return [t for t in inventory["tasks"] if t["tier"] == tier_filter]


def _eval_task(task: dict, live_by_name: dict, now: datetime) -> list:
    """Evaluate one inventory task — return a list of issues (may be empty)."""
    issues = []
    task_name = task["task_name"]
    tier = task["tier"]
    cadence = task["cadence_class"]
    grace = task["grace_multiplier"]

    # File checks — `outputs` entries may contain {today} / {last_biz_day}
    # templates which are resolved against `now` before checking the file.
    # The displayed `output_path` in any alert is the EXPANDED path so an
    # operator can copy-paste it, rather than the raw template.
    for output_path_str in task["outputs"]:
        expanded = expand_output_template(output_path_str, now)
        path = REPO_ROOT / expanded
        result = check_file_freshness(path, cadence, grace, now)
        if result == FreshnessResult.OUTPUT_MISSING:
            issues.append(Issue(
                kind=IssueKind.OUTPUT_MISSING, task_name=task_name,
                output_path=expanded, detail="file does not exist",
                tier=tier,
            ))
        elif result == FreshnessResult.OUTPUT_STALE:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
                age_hours = (now - mtime).total_seconds() / 3600
                detail = f"mtime {mtime:%Y-%m-%d %H:%M} ({age_hours:.1f}h old)"
            except OSError:
                detail = "stale (mtime unavailable)"
            issues.append(Issue(
                kind=IssueKind.OUTPUT_STALE, task_name=task_name,
                output_path=expanded,
                detail=detail,
                tier=tier,
            ))

    # Task liveness (only if task is in live scheduler).
    # VPS-hosted tasks live as systemd timers on Contabo, not in Windows Task
    # Scheduler. Their disabled Windows entries (kept around so PowerShell
    # enumeration doesn't ghost-flag them) freeze LastRunTime at the last run
    # before disablement, so the Windows liveness check is misleading. Skip it
    # — file-freshness on the synced artifact is the real signal.
    if task.get("host") == "vps":
        return issues
    if task_name in live_by_name:
        result = check_task_liveness(
            live_by_name[task_name], cadence, grace,
            now.isoformat(),
        )
        kind_map = {
            TaskLivenessResult.TASK_NEVER_RAN: IssueKind.TASK_NEVER_RAN,
            TaskLivenessResult.TASK_STALE_RESULT: IssueKind.TASK_STALE_RESULT,
            TaskLivenessResult.TASK_STALE_RUN: IssueKind.TASK_STALE_RUN,
        }
        if result in kind_map:
            last = live_by_name[task_name]
            issues.append(Issue(
                kind=kind_map[result], task_name=task_name,
                output_path=None,
                detail=f"LastTaskResult=0x{last.get('LastTaskResult', 0):x} LastRunTime={last.get('LastRunTime', '?')}",
                tier=tier,
            ))
    return issues


def run(args: argparse.Namespace, inventory_path: Path = INVENTORY_PATH) -> int:
    now = datetime.now(IST)
    now_iso = now.isoformat()
    run_label = "Intraday check" if args.tier else "Gate run"

    # 1. Load inventory (fatal on failure)
    try:
        inventory = load_inventory(inventory_path)
    except InventoryError as e:
        _fail_inventory(str(e), now_iso, args.dry_run)
        return 1  # unreachable

    # 2. Query live scheduler (warn + skip drift on failure, continue file checks)
    drift_skipped = False
    live_tasks = []
    try:
        live_tasks = query_anka_tasks()
    except SchedulerQueryError as e:
        log.warning("scheduler query failed: %s (drift check will be skipped)", e)
        drift_skipped = True

    live_by_name = {t["TaskName"]: t for t in live_tasks}

    # 3. Evaluate each inventory task (filtered by tier if requested)
    selected = _filter_tasks_by_tier(inventory, args.tier)
    current_issues = []
    for task in selected:
        current_issues.extend(_eval_task(task, live_by_name, now))

    # 4. Drift checks — only on --all (gate) runs, and only if scheduler query worked
    if not args.tier and not drift_skipped:
        orphans, ghosts = check_drift(inventory, live_tasks)
        for name in orphans:
            current_issues.append(Issue(
                kind=IssueKind.ORPHAN_TASK, task_name=name,
                detail="registered in scheduler but not in inventory", tier="warn",
            ))
        for name in ghosts:
            current_issues.append(Issue(
                kind=IssueKind.INVENTORY_GHOST, task_name=name,
                detail="in inventory but missing from scheduler", tier="warn",
            ))

    # 5. Dedup + digest
    prior_state = load_state(STATE_PATH)
    new_state, is_new, resolved_keys = update_state(prior_state, current_issues, now_iso)

    # 6. Emit or log
    if not current_issues and not resolved_keys:
        log.info("OK %d tasks, 0 issues", len(selected))
        save_state(new_state, STATE_PATH)
        return 0

    digest = build_digest(
        run_label=run_label + (" (DRIFT skipped)" if drift_skipped else ""),
        now_iso=now_iso,
        current_issues=current_issues,
        resolved_keys=resolved_keys,
        state=new_state,
        is_new=is_new,
    )

    if args.dry_run:
        print(digest)
        log.info("[DRY-RUN] digest written to stdout (%d issues, %d resolved)",
                 len(current_issues), len(resolved_keys))
    else:
        ok = send_or_log_digest(digest, ALERT_FALLBACK_PATH, dry_run=False)
        log.info("digest sent: telegram_ok=%s (%d issues, %d resolved)",
                 ok, len(current_issues), len(resolved_keys))

    save_state(new_state, STATE_PATH)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Anka data-freshness watchdog")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="check every task + drift (gate run)")
    group.add_argument("--tier", choices=["critical", "warn", "info"], help="check only this tier")
    parser.add_argument("--dry-run", action="store_true", help="print digest to stdout instead of Telegram")
    parser.add_argument("--inventory", type=Path, help="override inventory path (for tests)")
    args = parser.parse_args()

    inventory_path = args.inventory if args.inventory else INVENTORY_PATH
    return run(args, inventory_path=inventory_path)


if __name__ == "__main__":
    sys.exit(main())
