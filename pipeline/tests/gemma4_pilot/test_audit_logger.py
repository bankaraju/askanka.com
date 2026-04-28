"""AuditLogger contract tests.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 6)
"""
from __future__ import annotations

import json

from pipeline.gemma4_pilot.audit_logger import AuditLogger


def test_logger_writes_jsonl_row(tmp_path):
    logger = AuditLogger(root=tmp_path)
    logger.log(
        task="concall_supplement",
        date_iso="2026-04-29",
        record={
            "ts": "2026-04-29T14:30:00+05:30",
            "ticker": "RELIANCE",
            "primary": {
                "provider": "gemini-flash",
                "text": "...",
                "latency_s": 4.2,
                "rubric_score": 1.0,
                "rubric_pass": True,
            },
            "shadow": {
                "provider": "gemma4-local",
                "text": "...",
                "latency_s": 71.3,
                "rubric_score": 0.8,
                "rubric_pass": True,
            },
        },
    )
    out = tmp_path / "audit" / "concall_supplement" / "2026-04-29.jsonl"
    assert out.exists()
    line = json.loads(out.read_text().strip())
    assert line["ticker"] == "RELIANCE"
    assert line["shadow"]["provider"] == "gemma4-local"


def test_logger_appends(tmp_path):
    logger = AuditLogger(root=tmp_path)
    for i in range(3):
        logger.log(
            task="news_classification",
            date_iso="2026-04-29",
            record={"i": i},
        )
    out = tmp_path / "audit" / "news_classification" / "2026-04-29.jsonl"
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[2])["i"] == 2
