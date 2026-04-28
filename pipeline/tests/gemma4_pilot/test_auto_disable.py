"""Tests for the auto-disable guardrail.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md (§4.2)
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 18)
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.gemma4_pilot.auto_disable import check_and_apply


def _audit(root: Path, task: str, date_iso: str, n_pass: int, n_fail: int) -> None:
    p = root / "audit" / task / f"{date_iso}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for _ in range(n_pass):
        rows.append({"shadow": {"provider": "gemma4-local", "rubric_pass": True}})
    for _ in range(n_fail):
        rows.append({"shadow": {"provider": "gemma4-local", "rubric_pass": False}})
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _routing(path: Path, mode_for_task: dict[str, str]) -> None:
    cfg = {
        "default_primary": "gemini-flash",
        "default_fallback": "claude-haiku",
        "tasks": {
            t: {"mode": m, "primary": "gemini-flash", "shadow": "gemma4-local"}
            for t, m in mode_for_task.items()
        },
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")


def test_disables_when_below_90_pct(tmp_path: Path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"news_classification": "live"})
    _audit(tmp_path, "news_classification", "2026-04-29", n_pass=8, n_fail=2)
    # 80% pass — should disable

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert any(
        a["action"] == "disabled" and a["task"] == "news_classification"
        for a in actions
    )

    cfg = json.loads(routing_path.read_text(encoding="utf-8"))
    assert cfg["tasks"]["news_classification"]["mode"] == "disabled"


def test_no_disable_when_above_threshold(tmp_path: Path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"news_classification": "live"})
    _audit(tmp_path, "news_classification", "2026-04-29", n_pass=95, n_fail=5)

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert not any(a["action"] == "disabled" for a in actions)


def test_pairwise_below_40_pct_writes_manual_flag(tmp_path: Path):
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"article_draft": "live"})
    _audit(tmp_path, "article_draft", "2026-04-29", n_pass=10, n_fail=0)

    pw = tmp_path / "audit" / "pairwise" / "2026-04-29.jsonl"
    pw.parent.mkdir(parents=True, exist_ok=True)
    rows = (
        [{"task": "article_draft", "winner_provider": "gemini-flash"}] * 8
        + [{"task": "article_draft", "winner_provider": "gemma4-local"}] * 2
    )
    pw.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert any(
        a["action"] == "manual_review_flagged" and a["task"] == "article_draft"
        for a in actions
    )
    flag = tmp_path / "manual_review" / "article_draft.flag"
    assert flag.exists()


def test_low_n_does_not_trip_either_floor(tmp_path: Path):
    """Below the n>=5 / n>=10 minima, do not trip the guardrails."""
    routing_path = tmp_path / "llm_routing.json"
    _routing(routing_path, {"eod_narrative": "live"})
    # 3 fails, 0 passes — would be 0% but n=3 < 5
    _audit(tmp_path, "eod_narrative", "2026-04-29", n_pass=0, n_fail=3)

    actions = check_and_apply(tmp_path, routing_path, today_iso="2026-04-29")
    assert not actions
    cfg = json.loads(routing_path.read_text(encoding="utf-8"))
    assert cfg["tasks"]["eod_narrative"]["mode"] == "live"
