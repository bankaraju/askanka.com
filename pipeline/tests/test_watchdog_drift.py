"""Tests for scheduler query bridge and drift detection."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from pipeline.watchdog_scheduler import (
    SchedulerQueryError,
    TaskLivenessResult,
    query_anka_tasks,
    check_task_liveness,
    check_drift,
)


class TestQueryAnkaTasks:
    def test_parses_powershell_json_output(self):
        fake_stdout = """[
            {"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"},
            {"TaskName": "AnkaEODReview", "LastTaskResult": 0, "LastRunTime": "2026-04-15T16:00:00"}
        ]"""
        mock_result = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert len(tasks) == 2
        assert tasks[0]["TaskName"] == "AnkaMorningScan"
        assert tasks[0]["LastTaskResult"] == 0

    def test_single_task_object_wrapped_to_list(self):
        # PowerShell returns a single object (not array) for one-task result
        fake_stdout = """{"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"}"""
        mock_result = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert len(tasks) == 1

    def test_empty_output_returns_empty_list(self):
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            tasks = query_anka_tasks()
        assert tasks == []

    def test_powershell_nonzero_raises_SchedulerQueryError(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="Access denied")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            with pytest.raises(SchedulerQueryError, match="Access denied"):
                query_anka_tasks()

    def test_timeout_raises_SchedulerQueryError(self):
        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=30)
        with patch("pipeline.watchdog_scheduler.subprocess.run", side_effect=raise_timeout):
            with pytest.raises(SchedulerQueryError, match="timed out"):
                query_anka_tasks()

    def test_malformed_json_raises_SchedulerQueryError(self):
        mock_result = MagicMock(returncode=0, stdout="not valid json", stderr="")
        with patch("pipeline.watchdog_scheduler.subprocess.run", return_value=mock_result):
            with pytest.raises(SchedulerQueryError, match="non-JSON"):
                query_anka_tasks()


class TestDriftDetection:
    def _inventory(self, task_names):
        return {"version": 1, "updated": "2026-04-16", "tasks": [
            {"task_name": n, "tier": "info", "cadence_class": "daily",
             "outputs": [], "grace_multiplier": 1.5, "notes": ""}
            for n in task_names
        ]}

    def _live(self, task_names):
        return [{"TaskName": n, "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:00:00"} for n in task_names]

    def test_exact_agreement_zero_drift(self):
        inv = self._inventory(["A", "B", "C"])
        live = self._live(["A", "B", "C"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == []
        assert ghosts == []

    def test_scheduler_has_extra_tasks_yields_orphans(self):
        inv = self._inventory(["A", "B"])
        live = self._live(["A", "B", "C", "D"])
        orphans, ghosts = check_drift(inv, live)
        assert sorted(orphans) == ["C", "D"]
        assert ghosts == []

    def test_inventory_has_extra_tasks_yields_ghosts(self):
        inv = self._inventory(["A", "B", "C", "D"])
        live = self._live(["A", "B"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == []
        assert sorted(ghosts) == ["C", "D"]

    def test_both_drifts_simultaneously(self):
        inv = self._inventory(["A", "B", "X"])
        live = self._live(["A", "B", "Y"])
        orphans, ghosts = check_drift(inv, live)
        assert orphans == ["Y"]
        assert ghosts == ["X"]

    def test_vps_hosted_task_not_flagged_as_ghost(self):
        # VPS-hosted tasks live as systemd timers on Contabo; they're absent
        # from Windows Task Scheduler by design. They must not show up as
        # inventory ghosts.
        inv = {"version": 1, "updated": "2026-04-28", "tasks": [
            {"task_name": "A", "tier": "info", "cadence_class": "daily",
             "outputs": [], "grace_multiplier": 1.5, "notes": ""},
            {"task_name": "VPSTask", "tier": "info", "cadence_class": "weekly",
             "host": "vps", "outputs": [], "grace_multiplier": 1.5, "notes": ""},
        ]}
        live = self._live(["A"])  # VPSTask deliberately absent from Windows
        orphans, ghosts = check_drift(inv, live)
        assert orphans == []
        assert ghosts == []  # VPSTask excluded from ghost set


class TestCheckTaskLiveness:
    def test_result_0_recent_run_is_alive(self):
        task = {"TaskName": "AnkaMorningScan", "LastTaskResult": 0, "LastRunTime": "2026-04-16T09:25:00"}
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.ALIVE

    def test_never_ran_sentinel(self):
        task = {"TaskName": "AnkaGapPredictor", "LastTaskResult": 267011,
                "LastRunTime": "1999-12-30T00:00:00"}
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_NEVER_RAN

    def test_nonzero_result(self):
        task = {"TaskName": "AnkaWeeklyReport", "LastTaskResult": 1,
                "LastRunTime": "2026-04-11T10:00:00"}
        result = check_task_liveness(task, cadence_class="weekly", grace_multiplier=1.25,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_STALE_RESULT

    def test_stale_run_time(self):
        task = {"TaskName": "AnkaMorningScan", "LastTaskResult": 0,
                "LastRunTime": "2026-04-14T09:25:00"}
        # 48h later, daily cadence + 1.5 multiplier = 30h window → stale run
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T10:00:00")
        assert result == TaskLivenessResult.TASK_STALE_RUN

    def test_missing_last_run_time_is_never_ran(self):
        # PowerShell can omit the field entirely, or return None
        task1 = {"TaskName": "AnkaFoo", "LastTaskResult": 0}  # no LastRunTime
        task2 = {"TaskName": "AnkaBar", "LastTaskResult": 0, "LastRunTime": None}
        for t in (task1, task2):
            result = check_task_liveness(t, cadence_class="daily", grace_multiplier=1.5,
                                         now_iso="2026-04-16T10:00:00")
            assert result == TaskLivenessResult.TASK_NEVER_RAN

    def test_intraday_outside_market_hours_is_alive_even_if_old(self):
        # Intraday task last ran at 09:30 IST; now is 20:00 IST (post-market).
        # Age = 10h 30m = 37800s > 4500s intraday window → would be stale.
        # But post-market: no new runs expected until tomorrow → ALIVE.
        task = {"TaskName": "AnkaIntraday0930", "LastTaskResult": 0,
                "LastRunTime": "2026-04-16T09:30:00+05:30"}
        result = check_task_liveness(task, cadence_class="intraday", grace_multiplier=2.0,
                                     now_iso="2026-04-16T20:00:00+05:30")
        assert result == TaskLivenessResult.ALIVE

    def test_intraday_during_market_hours_still_flags_stale_run(self):
        # Intraday task last ran at 10:00; now is 12:00 IST (market hours).
        # Age = 2h = 7200s > 4500s (75 min) intraday window → stale run should still fire.
        task = {"TaskName": "AnkaIntraday1000", "LastTaskResult": 0,
                "LastRunTime": "2026-04-16T10:00:00+05:30"}
        result = check_task_liveness(task, cadence_class="intraday", grace_multiplier=2.0,
                                     now_iso="2026-04-16T12:00:00+05:30")
        assert result == TaskLivenessResult.TASK_STALE_RUN

    def test_intraday_weekend_is_alive_even_if_very_old(self):
        # Intraday task last ran Friday 15:30 IST; now is Monday 09:00 IST (pre-market).
        # Age = 65.5 hours, but weekend + pre-market → ALIVE.
        task = {"TaskName": "AnkaIntraday1530", "LastTaskResult": 0,
                "LastRunTime": "2026-04-10T15:30:00+05:30"}  # Friday
        result = check_task_liveness(task, cadence_class="intraday", grace_multiplier=2.0,
                                     now_iso="2026-04-13T09:00:00+05:30")  # Monday 09:00
        assert result == TaskLivenessResult.ALIVE

    def test_sched_s_task_running_treated_as_alive(self):
        # 0x00041301 (267009) = SCHED_S_TASK_RUNNING — task is in-flight when queried.
        # This is informational, not a failure.
        task = {"TaskName": "AnkaEODTrackRecord", "LastTaskResult": 0x41301,
                "LastRunTime": "2026-04-16T16:15:45+05:30"}
        result = check_task_liveness(task, cadence_class="daily", grace_multiplier=1.5,
                                     now_iso="2026-04-16T16:15:47+05:30")
        assert result == TaskLivenessResult.ALIVE
