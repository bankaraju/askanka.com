"""PowerShell bridge to Windows Task Scheduler + drift + task-liveness checks.

Query format: one `Get-ScheduledTask -TaskName Anka* | Get-ScheduledTaskInfo`
invocation piped to ConvertTo-Json. Single call; watchdog does NOT iterate per
task (that would multiply latency by ~70x on a slow laptop).
"""

import enum
import json
import subprocess
from datetime import datetime

from pipeline.watchdog_freshness import IST, compute_window_seconds, is_market_hours

# Windows Task Scheduler informational (non-failure) codes.
# 0x00041301 = SCHED_S_TASK_RUNNING — task is currently running when queried.
_SCHED_INFO_CODES = frozenset({0x41301})

# PowerShell one-liner: enumerate Anka*, join with TaskInfo, emit JSON array.
_PS_QUERY = (
    "Get-ScheduledTask -TaskName 'Anka*' | "
    "ForEach-Object { "
    "  $i = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath; "
    "  [PSCustomObject]@{ "
    "    TaskName = $_.TaskName; "
    "    LastTaskResult = $i.LastTaskResult; "
    "    LastRunTime = $i.LastRunTime.ToString('o'); "
    "    NextRunTime = $i.NextRunTime.ToString('o') "
    "  } "
    "} | ConvertTo-Json -Compress"
)


class SchedulerQueryError(Exception):
    """Raised when the PowerShell Get-ScheduledTask call fails."""


class TaskLivenessResult(enum.Enum):
    ALIVE = "ALIVE"
    TASK_NEVER_RAN = "TASK_NEVER_RAN"
    TASK_STALE_RESULT = "TASK_STALE_RESULT"
    TASK_STALE_RUN = "TASK_STALE_RUN"


def query_anka_tasks() -> list[dict]:
    """Invoke PowerShell, return list of {TaskName, LastTaskResult, LastRunTime, NextRunTime}."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", _PS_QUERY],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        raise SchedulerQueryError(f"PowerShell query timed out after {e.timeout}s") from e
    if result.returncode != 0:
        raise SchedulerQueryError(f"Get-ScheduledTask failed: {result.stderr.strip()}")
    out = result.stdout.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise SchedulerQueryError(f"PowerShell returned non-JSON output: {e}") from e
    # PowerShell returns a single object (not array) when only one result
    if isinstance(data, dict):
        return [data]
    return data


def check_drift(inventory: dict, live_tasks: list[dict]) -> tuple[list[str], list[str]]:
    """Return (orphans, ghosts).

    orphans = Anka* tasks in scheduler but not in inventory.
    ghosts  = inventory entries whose task_name is not in scheduler.

    Tasks marked ``host: vps`` are excluded from the ghost set: they run as
    systemd timers on Contabo and are deliberately absent from Windows Task
    Scheduler. They still count as "known" inventory entries, so a Windows
    Anka* task with the same name would still register as orphan / not flagged.
    """
    vps_hosted = {
        t["task_name"] for t in inventory["tasks"] if t.get("host") == "vps"
    }
    inv_names = {t["task_name"] for t in inventory["tasks"]}
    live_names = {t["TaskName"] for t in live_tasks}
    orphans = sorted(live_names - inv_names)
    ghosts = sorted((inv_names - live_names) - vps_hosted)
    return orphans, ghosts


def check_task_liveness(
    task: dict,
    cadence_class: str,
    grace_multiplier: float,
    now_iso: str,
) -> TaskLivenessResult:
    """Classify one live-scheduler task entry against its expected cadence."""
    last_run_raw = task.get("LastRunTime") or ""
    next_run_raw = task.get("NextRunTime") or ""
    last_run_is_sentinel = (
        not last_run_raw
        or last_run_raw.startswith("1999-")
        or last_run_raw.startswith("0001-")
    )

    # Newly-registered task: LastRunTime is the 1999 sentinel but the trigger
    # has a future NextRunTime — the first fire just hasn't happened yet. This
    # is the V1 Shadow_HHMM cohort registered mid-day after their HHMM had
    # passed; their next fire is tomorrow at HHMM. Without this branch the
    # watchdog flagged 12 healthy tasks as NEVER_RAN every cycle.
    if last_run_is_sentinel and next_run_raw and not (
        next_run_raw.startswith("1999-") or next_run_raw.startswith("0001-")
    ):
        try:
            now_dt = datetime.fromisoformat(now_iso)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=IST)
            next_run_dt = datetime.fromisoformat(next_run_raw.replace("Z", "+00:00"))
            if next_run_dt.tzinfo is None:
                next_run_dt = next_run_dt.replace(tzinfo=IST)
            if next_run_dt > now_dt:
                return TaskLivenessResult.ALIVE
        except (ValueError, AttributeError):
            pass  # malformed → fall through to NEVER_RAN

    if last_run_is_sentinel:
        return TaskLivenessResult.TASK_NEVER_RAN

    # Non-zero result = crashed or failed (but exclude informational codes like SCHED_S_TASK_RUNNING).
    result_code = task.get("LastTaskResult", 0)
    if result_code != 0 and result_code not in _SCHED_INFO_CODES:
        return TaskLivenessResult.TASK_STALE_RESULT

    # Parse last-run timestamp and compute age
    try:
        last_run = datetime.fromisoformat(last_run_raw.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
    except (ValueError, AttributeError):
        return TaskLivenessResult.TASK_STALE_RUN

    # NextRunTime > now means the task is on schedule — Windows Task Scheduler
    # advances NextRunTime forward only when the previous fire window closed
    # successfully (or was missed and consumed). For per-time-slot tasks like
    # AnkaIntraday0930 (fires once daily at HH:MM), age may be ~24h between
    # fires while the task is perfectly healthy; the only valid liveness signal
    # is whether the NEXT scheduled run is still in the future. Older Windows
    # builds may not surface NextRunTime; when absent we fall back to the
    # cadence-window age check below.
    next_run_raw = task.get("NextRunTime") or ""
    if next_run_raw and not (
        next_run_raw.startswith("1999-") or next_run_raw.startswith("0001-")
    ):
        try:
            next_run = datetime.fromisoformat(next_run_raw.replace("Z", "+00:00"))
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=IST)
            if next_run > now:
                return TaskLivenessResult.ALIVE
        except (ValueError, AttributeError):
            pass  # malformed NextRunTime → fall through to age check

    # Intraday tasks don't run outside market hours — skip age check if we're
    # currently in a no-run window (post-market, pre-market, or weekend).
    if cadence_class == "intraday" and not is_market_hours(now):
        return TaskLivenessResult.ALIVE

    age = (now - last_run).total_seconds()
    window = compute_window_seconds(cadence_class, grace_multiplier)
    if age > window:
        return TaskLivenessResult.TASK_STALE_RUN
    return TaskLivenessResult.ALIVE
