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
VALID_CADENCES = {"intraday", "daily", "weekly"}
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
        with path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise InventoryError(f"malformed JSON in {path}: {e}") from e

    if not isinstance(data, dict):
        raise InventoryError(f"inventory root must be an object, got {type(data).__name__}")
    if "version" not in data:
        raise InventoryError("inventory missing required top-level field: version")
    if data.get("version") != 1:
        raise InventoryError(f"unsupported inventory version: {data.get('version')}")
    if "tasks" not in data or not isinstance(data["tasks"], list):
        raise InventoryError("inventory missing or non-list 'tasks' field")

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
        if not isinstance(task["grace_multiplier"], (int, float)) or task["grace_multiplier"] < 0:
            raise InventoryError(f"tasks[{i}] ({task['task_name']}) grace_multiplier must be non-negative number")

    return data
