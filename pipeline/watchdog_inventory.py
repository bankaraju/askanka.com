"""Inventory file loader and schema validator.

The inventory is the canonical source-of-truth for what tasks should exist
and what their output-file contracts are. A missing or malformed inventory
is a FATAL condition — the watchdog must never silently fall back to
enumerating the live scheduler, because silent drift is the bug we're fixing.
"""

import json
from pathlib import Path
from typing import Any

VALID_TIERS = {"critical", "warn", "info"}
VALID_CADENCES = {"intraday", "daily", "weekly", "monthly"}
REQUIRED_TASK_FIELDS = {
    "task_name", "tier", "cadence_class", "outputs", "grace_multiplier", "notes",
}


class InventoryError(Exception):
    """Raised on any inventory load/validate failure. Always fatal."""


def load_inventory(path: Path) -> dict[str, Any]:
    """Load and validate the inventory JSON. Raise InventoryError on any issue."""
    path = Path(path)
    if not path.exists():
        raise InventoryError(f"inventory file not found: {path}")
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise InventoryError(f"malformed JSON in {path}: {e}") from e

    if not isinstance(data, dict):
        raise InventoryError(f"inventory root must be an object, got {type(data).__name__}")
    if "version" not in data:
        raise InventoryError("inventory missing required top-level field: version")
    if data.get("version") != 1:
        raise InventoryError(f"unsupported inventory version: {data.get('version')!r}")
    if "tasks" not in data or not isinstance(data["tasks"], list):
        raise InventoryError("inventory missing or non-list 'tasks' field")

    # Optional: paths whose freshness is event-driven (only update when an
    # event happens, e.g. closed_signals.json on signal close). The watchdog
    # SKIPS the cyclical OUTPUT_STALE check on these paths but still flags
    # OUTPUT_MISSING. Without this, a quiet day produces N false-positive
    # OUTPUT_STALE alerts (one per task that lists the file in `outputs`).
    edp = data.get("event_driven_paths", [])
    if not isinstance(edp, list):
        raise InventoryError(
            f"event_driven_paths must be a list, got {type(edp).__name__}")
    if not all(isinstance(p, str) for p in edp):
        raise InventoryError("event_driven_paths must be a list of strings")

    for i, task in enumerate(data["tasks"]):
        if not isinstance(task, dict):
            raise InventoryError(f"tasks[{i}] is not an object")
        missing = REQUIRED_TASK_FIELDS - set(task.keys())
        if missing:
            raise InventoryError(f"tasks[{i}] ({task.get('task_name', '?')}) missing fields: {sorted(missing)}")
        if task["tier"] not in VALID_TIERS:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) invalid tier: {task['tier']!r}")
        if task["cadence_class"] not in VALID_CADENCES:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) invalid cadence_class: {task['cadence_class']!r}")
        if not isinstance(task["outputs"], list):
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) outputs must be a list")
        if not all(isinstance(o, str) for o in task["outputs"]):
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) outputs must be a list of strings")
        if not isinstance(task["grace_multiplier"], (int, float)) or task["grace_multiplier"] < 0:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) grace_multiplier must be non-negative number")

    names = [t["task_name"] for t in data["tasks"]]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise InventoryError(f"duplicate task_name(s): {sorted(dupes)}")

    return data
