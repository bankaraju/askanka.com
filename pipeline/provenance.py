"""Engine/model output provenance — the running-system source of truth.

Every model output (today_regime.json, correlation_breaks.json,
live_paper_ledger.json, opus scorecards, ...) gets a sibling file
``<output>.provenance.json`` written by the producing scheduled task at
start time. Consumers (terminal pages, exporters, audit) read this to
render the "what is actually producing this value, right now" badge —
because docs lie under cutover, the running system is truth.

Schema (versioned via the ``schema`` field):

    {
        "schema": 1,
        "task_name": "AnkaETFSignal",
        "engine_version": "v3_curated",
        "git_sha": "abc1234",
        "started_at": "2026-04-27T04:45:02+05:30",
        "output_path": "pipeline/data/today_regime.json",
        "expected_cadence_seconds": 86400,
        "extras": {...optional task-specific metadata...}
    }

This module is intentionally tiny and dependency-light so any producer
can ``from pipeline.provenance import write`` without dragging in heavy
imports. Read-side helpers are equally light.

Status: 2026-04-27 — bootstrap. Producers opt-in; consumers degrade
gracefully when ``<output>.provenance.json`` is missing (badge shows
"unknown" amber). No retroactive backfill; we don't know what produced
yesterday's outputs.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROVENANCE_SUFFIX = ".provenance.json"


def _short_git_sha(repo_root: Path | None = None) -> str | None:
    """Best-effort git sha for the current HEAD; None on any failure."""
    try:
        cwd = repo_root or Path(__file__).resolve().parent.parent
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=2.0, check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _ist_now_iso() -> str:
    """Return current time in IST as ISO-8601."""
    # IST is +05:30, no DST. Hardcoding avoids tz-import variance.
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).isoformat(timespec="seconds")


def write(
    output_path: str | Path,
    *,
    task_name: str,
    engine_version: str,
    expected_cadence_seconds: int | None = None,
    extras: dict[str, Any] | None = None,
    git_sha: str | None = None,
    started_at: str | None = None,
) -> Path:
    """Write a provenance sidecar next to ``output_path``.

    Producers call this at task start time, before the output itself is
    written. Idempotent — overwrites prior provenance for this output.
    """
    output_path = Path(output_path)
    record = {
        "schema": SCHEMA_VERSION,
        "task_name": task_name,
        "engine_version": engine_version,
        "git_sha": git_sha if git_sha is not None else _short_git_sha(),
        "started_at": started_at or _ist_now_iso(),
        "output_path": str(output_path),
        "expected_cadence_seconds": expected_cadence_seconds,
        "extras": extras or {},
    }
    sidecar = output_path.with_suffix(output_path.suffix + PROVENANCE_SUFFIX)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return sidecar


def read(output_path: str | Path) -> dict[str, Any] | None:
    """Return provenance for ``output_path`` or ``None`` if absent/corrupt.

    Consumers degrade gracefully: badge renders "unknown" (amber) when
    this returns None.
    """
    output_path = Path(output_path)
    sidecar = output_path.with_suffix(output_path.suffix + PROVENANCE_SUFFIX)
    if not sidecar.is_file():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def staleness_seconds(output_path: str | Path) -> float | None:
    """Seconds since the output file was last modified, or None if missing."""
    output_path = Path(output_path)
    if not output_path.is_file():
        return None
    return max(0.0, datetime.now().timestamp() - output_path.stat().st_mtime)


def assess(
    output_path: str | Path,
    expected_engine_version: str | None = None,
) -> dict[str, Any]:
    """Compose a UI-ready badge state for ``output_path``.

    Returns a dict the badge can consume directly:
        {
            "engine_version": str | None,
            "expected_engine_version": str | None,
            "task_name": str | None,
            "started_at": str | None,
            "output_age_seconds": float | None,
            "expected_cadence_seconds": int | None,
            "color": "green" | "amber" | "red" | "unknown",
            "reason": str,         # one-line human explanation
        }
    """
    p = read(output_path)
    age = staleness_seconds(output_path)
    if p is None:
        return {
            "engine_version": None,
            "expected_engine_version": expected_engine_version,
            "task_name": None,
            "started_at": None,
            "output_age_seconds": age,
            "expected_cadence_seconds": None,
            "color": "amber",
            "reason": "provenance sidecar not found — producer has not opted in yet",
        }

    cadence = p.get("expected_cadence_seconds")
    actual_version = p.get("engine_version")

    color = "green"
    reason = "ok"

    # Version mismatch trumps everything else: red
    if expected_engine_version and actual_version and actual_version != expected_engine_version:
        return {
            "engine_version": actual_version,
            "expected_engine_version": expected_engine_version,
            "task_name": p.get("task_name"),
            "started_at": p.get("started_at"),
            "output_age_seconds": age,
            "expected_cadence_seconds": cadence,
            "color": "red",
            "reason": f"engine_version mismatch: running {actual_version}, config expects {expected_engine_version}",
        }

    # Age vs cadence
    if cadence is not None and age is not None:
        if age > 2.0 * cadence:
            color = "red"
            reason = f"output age {int(age)}s > 2x cadence ({cadence}s)"
        elif age > 1.5 * cadence:
            color = "amber"
            reason = f"output age {int(age)}s > 1.5x cadence ({cadence}s)"

    return {
        "engine_version": actual_version,
        "expected_engine_version": expected_engine_version,
        "task_name": p.get("task_name"),
        "started_at": p.get("started_at"),
        "output_age_seconds": age,
        "expected_cadence_seconds": cadence,
        "color": color,
        "reason": reason,
    }
