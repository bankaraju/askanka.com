"""Tests for the daily report card aggregator.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 17)
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.gemma4_pilot.daily_report import build_report


def _write_audit(root: Path, task: str, date: str, rows: list[dict]) -> None:
    p = root / "audit" / task / f"{date}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _row(
    prim_pass: bool,
    shadow_pass: bool | None,
    primary_text: str = "P",
    shadow_text: str = "S",
    shadow_provider: str = "gemma4-local",
    shadow_error: str | None = None,
) -> dict:
    rec = {
        "ts": "2026-04-29T10:00:00+05:30",
        "primary": {
            "provider": "gemini-flash",
            "model": "gemini-2.5-flash",
            "text": primary_text,
            "rubric_score": 1.0 if prim_pass else 0.0,
            "rubric_pass": prim_pass,
            "latency_s": 2.0,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }
    if shadow_error:
        rec["shadow"] = {"provider": shadow_provider, "error": shadow_error}
    else:
        rec["shadow"] = {
            "provider": shadow_provider,
            "model": "gemma4:26b",
            "text": shadow_text,
            "rubric_score": 1.0 if shadow_pass else 0.0,
            "rubric_pass": shadow_pass,
            "latency_s": 70.0,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    return rec


def test_report_aggregates_rubric_pass_rates(tmp_path: Path):
    rows = [_row(True, True), _row(True, False), _row(True, True), _row(True, True)]
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)

    pairwise_path = tmp_path / "audit" / "pairwise" / "2026-04-29.jsonl"
    pairwise_path.parent.mkdir(parents=True, exist_ok=True)
    pairwise_path.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"task": "news_classification", "winner_provider": "gemma4-local", "winner": "A"},
                {"task": "news_classification", "winner_provider": "gemma4-local", "winner": "B"},
                {"task": "news_classification", "winner_provider": "gemini-flash", "winner": "A"},
                {"task": "news_classification", "winner_provider": "tie", "winner": "tie"},
            ]
        ),
        encoding="utf-8",
    )

    report = build_report(tmp_path, "2026-04-29")

    nc = report["tasks"]["news_classification"]
    assert nc["calls"] == 4
    assert nc["primary_rubric_pass_rate"] == 1.0
    assert nc["shadow_rubric_pass_rate"] == 0.75  # 3/4
    assert nc["pairwise_total"] == 4
    # Win rate: gemma_wins=2, ties=1 → (2 + 0.5*1) / 4 = 0.625
    assert abs(nc["pairwise_win_rate"] - 0.625) < 1e-9


def test_report_handles_shadow_errors(tmp_path: Path):
    rows = [_row(True, True), _row(True, None, shadow_error="ollama_down")]
    _write_audit(tmp_path, "concall_supplement", "2026-04-29", rows)

    report = build_report(tmp_path, "2026-04-29")
    cs = report["tasks"]["concall_supplement"]
    assert cs["calls"] == 2
    assert cs["shadow_errors"] == 1
    # 1 pass / 1 successful_call = 1.0 (errors not counted in denominator)
    assert cs["shadow_rubric_pass_rate"] == 1.0


def test_report_writes_both_json_and_md(tmp_path: Path):
    rows = [_row(True, True)]
    _write_audit(tmp_path, "news_classification", "2026-04-29", rows)
    build_report(tmp_path, "2026-04-29", write_files=True)
    assert (tmp_path / "report_cards" / "2026-04-29.json").exists()
    assert (tmp_path / "report_cards" / "2026-04-29.md").exists()


def test_report_handles_empty_day(tmp_path: Path):
    """No audit rows at all -> tasks dict still has keys, calls=0, rates None."""
    report = build_report(tmp_path, "2026-04-29")
    assert set(report["tasks"].keys()) == {
        "concall_supplement",
        "news_classification",
        "eod_narrative",
        "article_draft",
    }
    for task_metrics in report["tasks"].values():
        assert task_metrics["calls"] == 0
        assert task_metrics["primary_rubric_pass_rate"] is None
        assert task_metrics["pairwise_win_rate"] is None
