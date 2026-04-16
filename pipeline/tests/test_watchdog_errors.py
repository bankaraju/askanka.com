"""Tests for inventory loading and error-handling invariants."""

import json
from pathlib import Path

import pytest

from pipeline.watchdog_inventory import (
    InventoryError,
    load_inventory,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadInventory:
    def test_valid_minimal(self):
        inv = load_inventory(FIXTURES / "inventory_valid_minimal.json")
        assert inv["version"] == 1
        assert len(inv["tasks"]) == 1
        assert inv["tasks"][0]["task_name"] == "AnkaMorningScan"

    def test_missing_file_raises_InventoryError(self, tmp_path):
        with pytest.raises(InventoryError, match="not found"):
            load_inventory(tmp_path / "does_not_exist.json")

    def test_malformed_json_raises_InventoryError(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{this is: not valid json")
        with pytest.raises(InventoryError, match="malformed JSON"):
            load_inventory(f)

    def test_missing_version_raises(self, tmp_path):
        f = tmp_path / "no_version.json"
        f.write_text(json.dumps({"tasks": []}))
        with pytest.raises(InventoryError, match="version"):
            load_inventory(f)

    def test_invalid_tier_raises(self, tmp_path):
        f = tmp_path / "bad_tier.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "X", "tier": "bogus", "cadence_class": "daily",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        with pytest.raises(InventoryError, match="tier"):
            load_inventory(f)

    def test_invalid_cadence_raises(self, tmp_path):
        f = tmp_path / "bad_cadence.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "X", "tier": "info", "cadence_class": "hourly",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        with pytest.raises(InventoryError, match="cadence_class"):
            load_inventory(f)

    def test_missing_task_field_raises(self, tmp_path):
        f = tmp_path / "missing_field.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{"task_name": "X"}],  # missing everything else
        }))
        with pytest.raises(InventoryError, match="missing"):
            load_inventory(f)
