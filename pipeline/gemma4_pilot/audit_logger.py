"""Append-only JSONL audit logger for per-call records.

Layout: <root>/audit/<task>/<YYYY-MM-DD>.jsonl
One row per primary+shadow call pair (or single call if no shadow).

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 6)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class AuditLogger:
    root: Path

    def log(
        self, *, task: str, date_iso: str, record: Mapping[str, Any]
    ) -> None:
        out = self.root / "audit" / task / f"{date_iso}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
