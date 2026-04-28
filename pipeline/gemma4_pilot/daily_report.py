"""Daily report card aggregator.

Reads:
   - audit/<task>/<date>.jsonl    (per-call records from ShadowDispatcher)
   - audit/pairwise/<date>.jsonl  (human pairwise ratings)

Produces:
   - report_cards/<date>.json
   - report_cards/<date>.md

Locked metrics (spec §4.1):
  - rubric pass rate = pass / total (per provider, per task)
  - pairwise win rate = (gemma_wins + 0.5 * ties) / total_ratings (per task)

Errors are excluded from the shadow_rubric_pass_rate denominator so a
flapping local Ollama instance doesn't drag the rate to zero.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 17)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASKS = [
    "concall_supplement",
    "news_classification",
    "eod_narrative",
    "article_draft",
]


def build_report(root: Path, date_iso: str, write_files: bool = False) -> dict:
    report: dict[str, Any] = {"date": date_iso, "tasks": {}}

    pairwise_path = root / "audit" / "pairwise" / f"{date_iso}.jsonl"
    pairwise_rows: list[dict] = []
    if pairwise_path.exists():
        for line in pairwise_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pairwise_rows.append(json.loads(line))

    for task in TASKS:
        audit_path = root / "audit" / task / f"{date_iso}.jsonl"
        rows: list[dict] = []
        if audit_path.exists():
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))

        prim_pass = sum(
            1 for r in rows if r.get("primary", {}).get("rubric_pass")
        )
        shadow_attempts = [
            r for r in rows if r.get("shadow", {}).get("provider")
        ]
        shadow_errors = sum(
            1 for r in shadow_attempts if r["shadow"].get("error")
        )
        shadow_success = [
            r for r in shadow_attempts if not r["shadow"].get("error")
        ]
        shadow_pass = sum(
            1 for r in shadow_success if r["shadow"].get("rubric_pass")
        )

        prim_lat = [
            r["primary"]["latency_s"]
            for r in rows
            if "primary" in r and "latency_s" in r["primary"]
        ]
        shadow_lat = [
            r["shadow"]["latency_s"]
            for r in shadow_success
            if "latency_s" in r["shadow"]
        ]

        task_pairs = [r for r in pairwise_rows if r.get("task") == task]
        gemma_wins = sum(
            1 for r in task_pairs if r.get("winner_provider") == "gemma4-local"
        )
        ties = sum(1 for r in task_pairs if r.get("winner_provider") == "tie")
        n_pairs = len(task_pairs)
        win_rate = (
            ((gemma_wins + 0.5 * ties) / n_pairs) if n_pairs else None
        )

        report["tasks"][task] = {
            "calls": len(rows),
            "primary_rubric_pass_rate": (
                prim_pass / len(rows) if rows else None
            ),
            "shadow_rubric_pass_rate": (
                shadow_pass / len(shadow_success) if shadow_success else None
            ),
            "shadow_errors": shadow_errors,
            "primary_latency_p50_s": _p50(prim_lat),
            "shadow_latency_p50_s": _p50(shadow_lat),
            "pairwise_total": n_pairs,
            "pairwise_gemma_wins": gemma_wins,
            "pairwise_ties": ties,
            "pairwise_win_rate": win_rate,
        }

    if write_files:
        out_json = root / "report_cards" / f"{date_iso}.json"
        out_md = root / "report_cards" / f"{date_iso}.md"
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        out_md.write_text(_render_markdown(report), encoding="utf-8")

    return report


def _p50(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[len(s) // 2]


def _fmt_pct(x: float | None) -> str:
    return f"{x*100:.1f}%" if x is not None else "—"


def _fmt_s(x: float | None) -> str:
    return f"{x:.1f}s" if x is not None else "—"


def _render_markdown(report: dict) -> str:
    lines = [f"# Gemma Pilot Report Card — {report['date']}", ""]
    lines.append(
        "| Task | Calls | Primary Rubric | Shadow Rubric | Shadow Errors | "
        "P50 Lat (P/S) | Pairs | Pairwise Win |"
    )
    lines.append("|---|---:|---:|---:|---:|---|---:|---:|")
    for task, m in report["tasks"].items():
        lines.append(
            f"| {task} | {m['calls']} | "
            f"{_fmt_pct(m['primary_rubric_pass_rate'])} | "
            f"{_fmt_pct(m['shadow_rubric_pass_rate'])} | "
            f"{m['shadow_errors']} | "
            f"{_fmt_s(m['primary_latency_p50_s'])} / "
            f"{_fmt_s(m['shadow_latency_p50_s'])} | "
            f"{m['pairwise_total']} | {_fmt_pct(m['pairwise_win_rate'])} |"
        )
    return "\n".join(lines) + "\n"
