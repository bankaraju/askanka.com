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
    # mtime is fresh but content diverges from a source-of-truth: e.g.,
    # data/track_record.json reports total_closed=58 but closed_signals.json
    # already has 60 closed rows. Caught by content audits, not by mtime.
    CONTENT_DRIFT = "CONTENT_DRIFT"


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

    Reform 2026-04-30: digest is NEW + ESCALATED + RESOLVED only. Steady-state
    "ongoing" issues are tracked in pipeline/data/watchdog_state.json but NOT
    re-printed every cycle — that produced 32 alerts/hour the user ignored, and
    real fires (silent CRITICAL OUTPUT_MISSING) drowned in the noise.

    Header line carries NEW/ESCALATED/RESOLVED/ONGOING counts so the user can
    confirm the watchdog is alive every cycle without scrolling.

    Fan-out collapse: when N tasks share a stale output_path (one source-of-truth
    feeding many consumers), render the path once with "(affects N tasks: ...)"
    rather than N separate alerts.

    now_iso must be an ISO-8601 timestamp starting "YYYY-MM-DDTHH:MM:..." —
    only the first 16 characters render in the header.
    """
    # ----- Filter to renderable issues (drop info-tier; ORPHAN/GHOST -> DRIFT bucket)
    renderable: list[Issue] = []
    for issue in current_issues:
        if issue.kind in (IssueKind.ORPHAN_TASK, IssueKind.INVENTORY_GHOST):
            renderable.append(issue)
            continue
        tier = (issue.tier or "info").upper()
        if tier in ("CRITICAL", "WARN"):
            renderable.append(issue)

    # ----- Partition into to-show (NEW or ESCALATED-this-cycle) vs ongoing (suppressed)
    to_show: list[tuple[Issue, int, bool]] = []  # (issue, alert_count, is_new_flag)
    ongoing_count = 0
    new_n = 0
    esc_n = 0
    for issue in renderable:
        key = stable_key(issue)
        count = state.active_issues.get(key, {}).get("alert_count", 1)
        is_new_flag = is_new.get(key, True)
        is_escalated = (
            (not is_new_flag)
            and count >= ESCALATION_COUNT
            and count % ESCALATION_COUNT == 0
        )
        if is_new_flag:
            to_show.append((issue, count, True))
            new_n += 1
        elif is_escalated:
            to_show.append((issue, count, False))
            esc_n += 1
        else:
            ongoing_count += 1

    # ----- Bucket the to-show issues
    def _bucket_for(issue: Issue) -> str:
        if issue.kind in (IssueKind.ORPHAN_TASK, IssueKind.INVENTORY_GHOST):
            return "DRIFT"
        return (issue.tier or "info").upper()

    by_bucket: dict[str, list[tuple[Issue, int, bool]]] = {
        "CRITICAL": [], "WARN": [], "DRIFT": [],
    }
    for issue, count, is_new_flag in to_show:
        by_bucket[_bucket_for(issue)].append((issue, count, is_new_flag))

    # ----- Header: status line scannable in one glance
    header = (
        f"🚨 Anka Watchdog — {now_iso[:16].replace('T', ' ')} IST\n"
        f"{run_label} • NEW: {new_n} • ESCALATED: {esc_n} "
        f"• RESOLVED: {len(resolved_keys)} • ONGOING: {ongoing_count}"
    )

    sections = [header]

    # ----- Bucket bodies (only emit non-empty buckets)
    for bucket in ("CRITICAL", "WARN", "DRIFT"):
        items = by_bucket[bucket]
        if not items:
            continue
        sections.append("")
        sections.append(f"{bucket} ({len(items)}):")

        # Fan-out collapse: group OUTPUT_STALE/OUTPUT_MISSING by output_path
        # so a single stale source-of-truth doesn't print N consumer alerts.
        path_groups: dict[str, list[tuple[Issue, int, bool]]] = {}
        per_task: list[tuple[Issue, int, bool]] = []
        for issue, count, is_new_flag in items:
            if (
                issue.kind in (IssueKind.OUTPUT_STALE, IssueKind.OUTPUT_MISSING)
                and issue.output_path
            ):
                path_groups.setdefault(issue.output_path, []).append(
                    (issue, count, is_new_flag)
                )
            else:
                per_task.append((issue, count, is_new_flag))

        for path, group in path_groups.items():
            if len(group) == 1:
                issue, count, is_new_flag = group[0]
                if not is_new_flag:
                    sections.append(f"  ⚠️ STILL BROKEN — run {count}")
                sections.append(_format_issue_loud(issue))
            else:
                # Many consumers, one root cause — render the path once.
                sample = group[0][0]
                kind_str = sample.kind.value.lower().replace("_", " ")
                task_names = sorted({i.task_name for i, _, _ in group})
                shown = task_names[:3]
                more = len(task_names) - len(shown)
                tail = f", +{more} more" if more > 0 else ""
                # If any in the group is escalated, surface that
                any_esc = any(
                    (not new_flag) and count >= ESCALATION_COUNT
                    and count % ESCALATION_COUNT == 0
                    for _, count, new_flag in group
                )
                if any_esc:
                    sections.append("  ⚠️ STILL BROKEN")
                sections.append(
                    f"  • {kind_str}: {sample.output_path}  {sample.detail}".rstrip()
                )
                sections.append(
                    f"    affects {len(group)} tasks: {', '.join(shown)}{tail}"
                )

        for issue, count, is_new_flag in per_task:
            if not is_new_flag:
                sections.append(f"  ⚠️ STILL BROKEN — run {count}")
            sections.append(_format_issue_loud(issue))

    # ----- Resolved tail
    if resolved_keys:
        sections.append("")
        sections.append(f"RESOLVED ({len(resolved_keys)}):")
        for key in resolved_keys:
            task_name = key.split("|")[0]
            sections.append(f"  ✅ {task_name} — fresh again")

    # ----- Suppressed-ongoing footer (for trust: prove the watchdog still tracks)
    if ongoing_count > 0:
        sections.append("")
        sections.append(
            f"({ongoing_count} ongoing issue{'s' if ongoing_count != 1 else ''} "
            f"suppressed — see pipeline/data/watchdog_state.json)"
        )

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
