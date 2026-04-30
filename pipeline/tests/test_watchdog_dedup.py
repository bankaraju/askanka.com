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

    def test_save_is_atomic_no_tmp_left_behind(self, tmp_path):
        state = State(last_run="", active_issues={})
        f = tmp_path / "state.json"
        save_state(state, f)
        assert f.exists()
        # Temp file must not survive a successful write
        assert not (tmp_path / "state.json.tmp").exists()


class TestUpdateState:
    def _now(self):
        return datetime(2026, 4, 16, 9, 20, tzinfo=IST).isoformat()

    def test_new_issue_gets_alert_count_1(self):
        state = State(last_run="", active_issues={})
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new, resolved = update_state(state, [issue], self._now())
        key = stable_key(issue)
        assert is_new[key] is True
        assert new_state.active_issues[key]["alert_count"] == 1
        assert resolved == []

    def test_persistent_issue_increments_count(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        issue = Issue(IssueKind.OUTPUT_STALE, "A", "p.json", "")
        new_state, is_new, resolved = update_state(state, [issue], self._now())
        assert is_new[key] is False
        assert new_state.active_issues[key]["alert_count"] == 3
        assert resolved == []

    def test_resolved_issue_returns_resolved_list(self):
        key = "A|p.json|OUTPUT_STALE"
        state = State(last_run="", active_issues={
            key: {"first_seen": "x", "last_seen": "x", "alert_count": 2}
        })
        # No current issues
        new_state, is_new, resolved = update_state(state, [], self._now())
        assert key not in new_state.active_issues
        assert resolved == ["A|p.json|OUTPUT_STALE"]


class TestBuildDigest:
    def test_clean_digest_has_status_header_and_no_buckets(self):
        # Quiet cycle: no NEW, no ESCALATED, no RESOLVED, no ONGOING.
        # Header shows the four counts; no bucket sections render when empty.
        state = State(last_run="", active_issues={})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-16T09:20:00+05:30",
            current_issues=[], resolved_keys=[], state=state, is_new={},
        )
        assert "NEW: 0" in digest
        assert "ESCALATED: 0" in digest
        assert "RESOLVED: 0" in digest
        assert "ONGOING: 0" in digest
        # No bucket subsections when empty (silence is the default)
        assert "CRITICAL (" not in digest
        assert "WARN (" not in digest

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
        assert "NEW: 1" in digest

    def test_persistent_issue_suppressed_unless_escalated(self):
        # Steady-state issue (alert_count=3, not at escalation threshold) MUST NOT
        # appear by name in the digest. It is counted in the ONGOING header only.
        # This is the core anti-spam reform — see feedback_watchdog_must_be_actionable.
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
        # Suppressed: name does not appear, count is rolled into ONGOING
        assert "AnkaMorningScan" not in digest
        assert "ONGOING: 1" in digest
        assert "NEW: 0" in digest
        assert "ESCALATED: 0" in digest

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

    def test_escalation_refires_at_count_12(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaWeeklyStats",
            output_path="data/spread_stats.json", detail="",
            tier="warn",
        )
        key = stable_key(i)
        state = State(last_run="", active_issues={key: {
            "first_seen": "", "last_seen": "", "alert_count": 12,
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

    def test_info_tier_not_rendered(self):
        i = Issue(
            kind=IssueKind.OUTPUT_STALE, task_name="AnkaBackfill",
            output_path="data/whatever.json", detail="",
            tier="info",
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
        # Info-tier issues must not appear in any section
        assert "AnkaBackfill" not in digest
        # And must not be counted in any header bucket
        assert "NEW: 0" in digest
        assert "ONGOING: 0" in digest

    def test_fanout_collapse_by_output_path(self):
        # When N tasks all flag the same stale output_path, collapse to a single
        # source-of-truth line "(affects N tasks: A, B, +M more)" rather than
        # rendering N separate alerts. Root cause once, not fan-out 25 times.
        common_path = "pipeline/data/technicals.json"
        consumers = [
            "AnkaIntraday0930", "AnkaIntraday0945", "AnkaIntraday1000",
            "AnkaIntraday1015", "AnkaSignal0945",
        ]
        issues = [
            Issue(
                kind=IssueKind.OUTPUT_STALE, task_name=t,
                output_path=common_path, detail="mtime 2026-04-29 12:00 (23h old)",
                tier="critical",
            )
            for t in consumers
        ]
        # All NEW this cycle
        is_new = {stable_key(i): True for i in issues}
        state = State(last_run="", active_issues={stable_key(i): {
            "first_seen": "", "last_seen": "", "alert_count": 1,
        } for i in issues})
        digest = build_digest(
            run_label="Gate run", now_iso="2026-04-30T11:00:00+05:30",
            current_issues=issues, resolved_keys=[], state=state, is_new=is_new,
        )
        # The path appears exactly once in the body (header + footer mentions allowed)
        body = digest.split("CRITICAL")[1].split("RESOLVED")[0] if "CRITICAL" in digest else digest
        assert body.count(common_path) == 1, f"path should appear once in CRITICAL body, got {body.count(common_path)}\n{digest}"
        # The N-affected line names enough consumers to be useful
        assert "affects 5 tasks" in digest
        assert "AnkaIntraday0930" in digest

    def test_status_header_lists_run_label_and_counts(self):
        # Header line on every digest carries the four-tuple of counts so the
        # user can scan one line and know if they need to dig in.
        i_new = Issue(IssueKind.OUTPUT_STALE, "TaskNew", "p1.json", "", "critical")
        i_ongoing = Issue(IssueKind.OUTPUT_STALE, "TaskOngoing", "p2.json", "", "critical")
        state = State(last_run="", active_issues={
            stable_key(i_new): {"first_seen": "", "last_seen": "", "alert_count": 1},
            stable_key(i_ongoing): {"first_seen": "", "last_seen": "", "alert_count": 4},
        })
        digest = build_digest(
            run_label="Intraday check", now_iso="2026-04-30T11:00:00+05:30",
            current_issues=[i_new, i_ongoing],
            resolved_keys=["TaskGone||OUTPUT_STALE"],
            state=state,
            is_new={stable_key(i_new): True, stable_key(i_ongoing): False},
        )
        assert "Intraday check" in digest
        assert "NEW: 1" in digest
        assert "ESCALATED: 0" in digest
        assert "RESOLVED: 1" in digest
        assert "ONGOING: 1" in digest
        # New is loud
        assert "TaskNew" in digest
        # Ongoing is suppressed
        assert "TaskOngoing" not in digest
