"""Tests for v2 scheduled-task wiring (Task 7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


INVENTORY_PATH = Path("pipeline/config/anka_inventory.json")
REQUIRED_TASKS = (
    "AnkaAutoresearchMode2",
    "AnkaAutoresearchBHFDR",
    "AnkaAutoresearchHoldout",
)


def test_three_v2_tasks_present_in_inventory():
    inv = json.loads(INVENTORY_PATH.read_text())
    # Real schema: {"version": ..., "tasks": [...]} where each entry has "task_name"
    tasks_list = inv.get("tasks", inv) if isinstance(inv, dict) else inv
    if isinstance(tasks_list, list):
        task_names = {t["task_name"] for t in tasks_list if isinstance(t, dict) and "task_name" in t}
    elif isinstance(tasks_list, dict):
        task_names = set(tasks_list.keys())
    else:
        task_names = set()
    missing = [n for n in REQUIRED_TASKS if n not in task_names]
    assert not missing, f"inventory missing v2 tasks: {missing}"


def test_three_v2_bat_wrappers_present():
    for bat in REQUIRED_TASKS:
        path = Path("pipeline/scripts") / f"{bat}.bat"
        assert path.exists(), f"missing .bat wrapper: {path}"
