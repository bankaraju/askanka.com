"""Tests for dedup state, stable keys, and digest formatting."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from pipeline.watchdog_alerts import (
    Issue,
    IssueKind,
    State,
    build_digest,
    load_state,
    save_state,
    stable_key,
    update_state,
)

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class TestStableKey:
    def test_key_joins_three_parts_with_pipe(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaMorningScan",
            output_path="data/global_regime.json", detail="",
        )
        assert stable_key(i) == "AnkaMorningScan|data/global_regime.json|OUTPUT_STALE"

    def test_key_with_no_output_path(self):
        i = Issue(
            kind=IssueKind.TASK_NEVER_RAN, task_name="AnkaGapPredictor",
            output_path=None, detail="",
        )
        assert stable_key(i) == "AnkaGapPredictor||TASK_NEVER_RAN"


class TestStateIO:
    def test_load_missing_state_returns_empty(self, tmp_path):
        state = load_state(tmp_path / "nope.json")
        assert state.active_issues == {}

    def test_load_malformed_state_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        state = load_state(f)
        assert state.active_issues == {}

    def test_save_and_reload_roundtrip(self, tmp_path):
        state = State(
            last_run="2026-04-16T09:20:00+05:30",
            active_issues={
                "A|path|OUTPUT_STALE": {
                    "first_seen": "2026-04-16T09:20:00+05:30",
                    "last_seen": "2026-04-16T09:20:00+05:30",
                    "alert_count": 1,
                }
            },
        )
        f = tmp_path / "state.json"
        save_state(state, f)
        loaded = load_state(f)
        assert loaded.active_issues == state.active_issues


class TestUpdateState:
    def _now(self):
        return datetime(2026, 4, 16, 9, 20, tzinfo=IST).isoformat()

    def test_new_issue_gets_alert_count_1(self):
        state = State(last_run="", active_issues={})
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new = update_state(state, [issue], self._now())
        key = stable_key(issue)
        assert is_new[key] is True
        assert new_state.active_issues[key]["alert_count"] == 1

    def test_persistent_issue_increments_count(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new = update_state(state, [issue], self._now())
        assert is_new[key] is False
        assert new_state.active_issues[key]["alert_count"] == 3

    def test_resolved_issue_returns_resolved_list(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        # No current issues
        new_state, is_new = update_state(state, [], self._now())
        assert key not in new_state.active_issues


class TestBuildDigest:
    def test_clean_digest_has_all_section_headers(self):
        state = State(last_run="", active_issues={})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[], resolved_keys=[], state=state, is_new={},
        )
        assert "CRITICAL (0)" in digest
        assert "WARN (0)" in digest
        assert "DRIFT (0)" in digest

    def test_new_critical_renders_loud_block(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaReverseRegimeProfile",
            output_path="pipeline/autoresearch/reverse_regime_profile.json",
            detail="mtime 2026-04-14 15:38 (42h old, max 30h)",
            tier="critical",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 1,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: True},
        )
        assert "AnkaReverseRegimeProfile" in digest
        assert "42h old" in digest

    def test_persistent_issue_renders_compact_reminder(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaMorningScan",
            output_path="data/global_regime.json", detail="",
            tier="critical",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 3,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: False},
        )
        assert "still stale" in digest.lower() or "3rd run" in digest or "run 3" in digest.lower()

    def test_escalation_at_count_6(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaWeeklyStats",
            output_path="data/spread_stats.json", detail="",
            tier="warn",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 6,
        }})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[i], resolved_keys=[], state=state,
            is_new={key: False},
        )
        assert "STILL BROKEN" in digest

    def test_resolved_tail_shows_recovered_keys(self):
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[], resolved_keys=["AnkaEODReview|data/track_record.json|OUTPUT_STALE"],
            state=State(last_run="", active_issues={}), is_new={},
        )
        assert "RESOLVED" in digest
        assert "AnkaEODReview" in digest
