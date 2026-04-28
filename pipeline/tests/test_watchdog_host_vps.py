"""Watchdog skips Windows scheduler liveness for tasks marked `host: vps`.

Cohort A migrated to VPS systemd timers on 2026-04-25; Cohort B on 2026-04-28.
Their disabled Windows entries return stale LastRunTime forever, so the
scheduler-side checks (TASK_STALE_RUN, TASK_STALE_RESULT, TASK_NEVER_RAN, and
INVENTORY_GHOST) all false-alarm on these tasks. File-freshness on the
synced artifact is the only meaningful signal.
"""
from datetime import datetime, timezone, timedelta

from pipeline.watchdog import _eval_task


IST = timezone(timedelta(hours=5, minutes=30))


def test_host_vps_skips_task_liveness_check():
    # A weekly VPS-hosted task whose Windows entry is stale by 14 days.
    # If the watchdog still queried the Windows scheduler we'd get
    # TASK_STALE_RUN. With host=vps it must return zero issues
    # (file-freshness on outputs[] still runs, but outputs are empty here).
    task = {
        "task_name": "AnkaUnifiedBacktest",
        "tier": "critical",
        "cadence_class": "weekly",
        "host": "vps",
        "outputs": [],
        "grace_multiplier": 1.5,
        "notes": "",
    }
    live_by_name = {
        "AnkaUnifiedBacktest": {
            "TaskName": "AnkaUnifiedBacktest",
            "LastTaskResult": 0,
            "LastRunTime": "2026-04-14T00:00:00+05:30",
        }
    }
    now = datetime(2026, 4, 28, 10, 0, tzinfo=IST)
    issues = _eval_task(task, live_by_name, now)
    assert issues == []


def test_laptop_hosted_task_still_flags_stale_run():
    # Same shape, but no host=vps → Windows liveness check should fire.
    task = {
        "task_name": "AnkaSomeLaptopTask",
        "tier": "warn",
        "cadence_class": "weekly",
        "outputs": [],
        "grace_multiplier": 1.5,
        "notes": "",
    }
    live_by_name = {
        "AnkaSomeLaptopTask": {
            "TaskName": "AnkaSomeLaptopTask",
            "LastTaskResult": 0,
            "LastRunTime": "2026-04-14T00:00:00+05:30",
        }
    }
    now = datetime(2026, 4, 28, 10, 0, tzinfo=IST)
    issues = _eval_task(task, live_by_name, now)
    assert len(issues) == 1
    assert issues[0].kind.name == "TASK_STALE_RUN"
