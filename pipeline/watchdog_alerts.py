"""Dedup state, issue keys, digest formatting. Telegram send is in Task 8."""

import enum
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


class IssueKind(enum.Enum):
    OUTPUT_STALE = "OUTPUT_STALE"
    OUTPUT_MISSING = "OUTPUT_MISSING"
    TASK_NEVER_RAN = "TASK_NEVER_RAN"
    TASK_STALE_RESULT = "TASK_STALE_RESULT"
    TASK_STALE_RUN = "TASK_STALE_RUN"
    ORPHAN_TASK = "ORPHAN_TASK"
    INVENTORY_GHOST = "INVENTORY_GHOST"


@dataclass
class Issue:
    kind: IssueKind
    task_name: str
    output_path: Optional[str] = None
    detail: str = ""
    tier: str = "info"


@dataclass
class State:
    last_run: str
    active_issues: dict = field(default_factory=dict)


ESCALATION_COUNT = 6


def stable_key(issue: Issue) -> str:
    return f"{issue.task_name}|{issue.output_path or ''}|{issue.kind.value}"


def load_state(path: Path) -> State:
    path = Path(path)
    if not path.exists():
        return State(last_run="", active_issues={})
    try:
        with path.open() as f:
            data = json.load(f)
        return State(
            last_run=data.get("last_run", ""),
            active_issues=data.get("active_issues", {}),
        )
    except (json.JSONDecodeError, OSError):
        return State(last_run="", active_issues={})


def save_state(state: State, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump({"last_run": state.last_run, "active_issues": state.active_issues},
                  f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def update_state(
    prior: State,
    current_issues: list[Issue],
    now_iso: str,
) -> tuple[State, dict[str, bool], list[str]]:
    """Return (new_state, is_new_map, resolved_keys).

    - is_new_map[key] = True if first time seen in this run
    - resolved_keys = keys present in prior but absent in current_issues
    """
    is_new: dict[str, bool] = {}
    new_active: dict[str, dict] = {}
    for issue in current_issues:
        key = stable_key(issue)
        if key in prior.active_issues:
            prev = prior.active_issues[key]
            new_active[key] = {
                "first_seen": prev["first_seen"],
                "last_seen": now_iso,
                "alert_count": prev["alert_count"] + 1,
            }
            is_new[key] = False
        else:
            new_active[key] = {
                "first_seen": now_iso,
                "last_seen": now_iso,
                "alert_count": 1,
            }
            is_new[key] = True
    resolved_keys = sorted(set(prior.active_issues.keys()) - set(new_active.keys()))
    return State(last_run=now_iso, active_issues=new_active), is_new, resolved_keys


def _format_issue_loud(issue: Issue) -> str:
    lines = [f"  • {issue.task_name} — {issue.kind.value.lower().replace('_', ' ')}"]
    if issue.output_path:
        lines.append(f"    {issue.output_path}  {issue.detail}")
    elif issue.detail:
        lines.append(f"    {issue.detail}")
    return "\n".join(lines)


def _format_issue_compact(issue: Issue, alert_count: int) -> str:
    return f"  • {issue.task_name} still {issue.kind.value.lower().replace('_', ' ')} (run {alert_count})"


def build_digest(
    run_label: str,
    now_iso: str,
    current_issues: list[Issue],
    resolved_keys: list[str],
    state: State,
    is_new: dict[str, bool],
) -> str:
    """Assemble the Telegram-ready digest message.

    now_iso must be an ISO-8601 timestamp starting "YYYY-MM-DDTHH:MM:..."
    (e.g. datetime.isoformat() on an aware datetime). Only the first 16
    characters are rendered in the header.
    """
    by_bucket: dict[str, list[Issue]] = {"CRITICAL": [], "WARN": [], "DRIFT": []}
    for issue in current_issues:
        if issue.kind in (IssueKind.ORPHAN_TASK, IssueKind.INVENTORY_GHOST):
            by_bucket["DRIFT"].append(issue)
            continue
        tier = (issue.tier or "info").upper()
        if tier in ("CRITICAL", "WARN"):
            by_bucket[tier].append(issue)
        # info-tier issues are logged but not surfaced in the Telegram digest

    total = sum(len(v) for v in by_bucket.values())
    header = f"🚨 Anka Watchdog — {now_iso[:16].replace('T', ' ')} IST\n{run_label} • {total} issue{'s' if total != 1 else ''}"

    sections = [header, ""]
    for bucket in ("CRITICAL", "WARN", "DRIFT"):
        items = by_bucket[bucket]
        sections.append(f"{bucket} ({len(items)}):")
        for issue in items:
            key = stable_key(issue)
            count = state.active_issues.get(key, {}).get("alert_count", 1)
            if is_new.get(key, True):
                sections.append(_format_issue_loud(issue))
            elif count >= ESCALATION_COUNT and count % ESCALATION_COUNT == 0:
                sections.append(f"  ⚠️ STILL BROKEN AFTER {count // 2} DAYS")
                sections.append(_format_issue_loud(issue))
            else:
                sections.append(_format_issue_compact(issue, count))
        sections.append("")

    if resolved_keys:
        sections.append(f"RESOLVED ({len(resolved_keys)}):")
        for key in resolved_keys:
            task_name = key.split("|")[0]
            sections.append(f"  ✅ {task_name} — fresh again")

    return "\n".join(sections).rstrip() + "\n"


def _send_alert(digest: str) -> bool:
    """Thin shim around pipeline.telegram_bot.send_message. Isolated for mocking.

    The digest is already fully formatted — bypass telegram_bot's format_alert
    and send the plain text directly. parse_mode=None avoids Markdown surprises
    from emoji/dashes/parens in task names and headers.
    """
    from pipeline.telegram_bot import send_message
    return send_message(digest, parse_mode=None)


def send_or_log_digest(digest: str, fallback_log: Path, dry_run: bool = False) -> bool:
    """Send digest to Telegram, fall back to log on failure.

    Returns True iff Telegram delivery succeeded (or dry_run). Log-fallback
    returns False but does not raise.
    """
    if dry_run:
        return True
    try:
        return bool(_send_alert(digest))
    except Exception as e:
        fallback_log.parent.mkdir(parents=True, exist_ok=True)
        with Path(fallback_log).open("a", encoding="utf-8") as f:
            f.write(f"\n---\nTELEGRAM_FAILED {datetime.now().isoformat()}\nerror: {type(e).__name__}: {e}\n{digest}\n")
        return False
