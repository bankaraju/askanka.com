"""Tests for scheduler query bridge and drift detection."""

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
