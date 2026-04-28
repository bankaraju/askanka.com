"""Auto-disable guardrail per spec §4.2.

Rules (per task; one task tripping does not affect the others):
  - shadow rubric pass rate < 90% over rolling 24h, n>=5
      → flip task mode to 'disabled' in llm_routing.json + Telegram alert
  - pairwise win rate < 40% over rolling 7d, n>=10
      → write manual_review/<task>.flag (no auto-flip; needs human read)

Designed to be idempotent — already-disabled tasks are not re-disabled,
and the manual-review flag is overwritten in place each tick.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md (§4.2)
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 18)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

LOG = logging.getLogger(__name__)

TASKS = [
    "concall_supplement",
    "news_classification",
    "eod_narrative",
    "article_draft",
]
RUBRIC_FLOOR = 0.90
PAIRWISE_FLOOR = 0.40
RUBRIC_MIN_N = 5
PAIRWISE_MIN_N = 10


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rolling_dates(today_iso: str, days: int) -> list[str]:
    today = dt.date.fromisoformat(today_iso)
    return [(today - dt.timedelta(days=i)).isoformat() for i in range(days)]


def _shadow_rubric_pass_rate(
    root: Path, task: str, dates: list[str]
) -> tuple[float | None, int]:
    n = 0
    p = 0
    for d in dates:
        rows = _read_jsonl(root / "audit" / task / f"{d}.jsonl")
        for r in rows:
            sh = r.get("shadow") or {}
            if sh.get("error") or sh.get("provider") is None:
                continue
            n += 1
            if sh.get("rubric_pass"):
                p += 1
    return ((p / n) if n else None), n


def _pairwise_win_rate(
    root: Path, task: str, dates: list[str]
) -> tuple[float | None, int]:
    wins = ties = total = 0
    for d in dates:
        for r in _read_jsonl(root / "audit" / "pairwise" / f"{d}.jsonl"):
            if r.get("task") != task:
                continue
            total += 1
            wp = r.get("winner_provider")
            if wp == "gemma4-local":
                wins += 1
            elif wp == "tie":
                ties += 1
    return (((wins + 0.5 * ties) / total) if total else None), total


def check_and_apply(
    audit_root: Path, routing_path: Path, today_iso: str
) -> list[dict]:
    cfg = json.loads(routing_path.read_text(encoding="utf-8"))
    actions: list[dict] = []

    for task in TASKS:
        # 24h shadow rubric guardrail
        rate, n = _shadow_rubric_pass_rate(
            audit_root, task, _rolling_dates(today_iso, 1)
        )
        if rate is not None and n >= RUBRIC_MIN_N and rate < RUBRIC_FLOOR:
            current_mode = (
                cfg.get("tasks", {}).get(task, {}).get("mode", "shadow")
            )
            if current_mode != "disabled":
                cfg.setdefault("tasks", {}).setdefault(task, {})
                cfg["tasks"][task]["mode"] = "disabled"
                actions.append(
                    {
                        "task": task,
                        "action": "disabled",
                        "reason": (
                            f"rubric_pass_rate {rate:.2%} < "
                            f"{RUBRIC_FLOOR:.0%} over last 24h (n={n})"
                        ),
                    }
                )

        # 7d pairwise guardrail
        wr, np_ = _pairwise_win_rate(
            audit_root, task, _rolling_dates(today_iso, 7)
        )
        if (
            wr is not None
            and np_ >= PAIRWISE_MIN_N
            and wr < PAIRWISE_FLOOR
        ):
            flag_path = audit_root / "manual_review" / f"{task}.flag"
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.write_text(
                f"[{today_iso}] pairwise_win_rate={wr:.2%} (n={np_}) below "
                f"{PAIRWISE_FLOOR:.0%} floor — manual review required\n",
                encoding="utf-8",
            )
            actions.append(
                {
                    "task": task,
                    "action": "manual_review_flagged",
                    "reason": (
                        f"pairwise_win_rate {wr:.2%} < "
                        f"{PAIRWISE_FLOOR:.0%} over last 7d (n={np_})"
                    ),
                }
            )

    if actions:
        routing_path.write_text(
            json.dumps(cfg, indent=2), encoding="utf-8"
        )
        for a in actions:
            LOG.warning(
                "guardrail: %s -- %s -- %s",
                a["task"],
                a["action"],
                a["reason"],
            )
            try:
                from pipeline.telegram_client import send_message  # type: ignore

                send_message(
                    f"⚠️ Gemma Pilot guardrail: {a['task']} {a['action']} — "
                    f"{a['reason']}",
                    channel="ops",
                )
            except Exception as e:  # noqa: BLE001
                LOG.warning("telegram failed: %s", e)
    return actions
