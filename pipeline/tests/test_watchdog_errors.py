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

    def test_version_as_string_raises(self, tmp_path):
        f = tmp_path / "string_version.json"
        f.write_text(json.dumps({"version": "1", "updated": "2026-04-16", "tasks": []}))
        with pytest.raises(InventoryError, match="'1'"):
            load_inventory(f)

    def test_duplicate_task_name_raises(self, tmp_path):
        f = tmp_path / "dupes.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [
                {"task_name": "AnkaMorningScan", "tier": "critical", "cadence_class": "daily",
                 "outputs": [], "grace_multiplier": 1.5, "notes": ""},
                {"task_name": "AnkaMorningScan", "tier": "warn", "cadence_class": "daily",
                 "outputs": [], "grace_multiplier": 1.0, "notes": ""},
            ],
        }))
        with pytest.raises(InventoryError, match="duplicate task_name"):
            load_inventory(f)

    def test_non_string_output_entry_raises(self, tmp_path):
        f = tmp_path / "bad_outputs.json"
        f.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "X", "tier": "info", "cadence_class": "daily",
                "outputs": ["data/ok.json", None, 42],
                "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        with pytest.raises(InventoryError, match="list of strings"):
            load_inventory(f)

    def test_production_inventory_loads(self):
        # Smoke test: the real bootstrap output must validate at all times.
        repo_root = Path(__file__).resolve().parents[2]
        prod_path = repo_root / "pipeline" / "config" / "anka_inventory.json"
        inv = load_inventory(prod_path)
        assert inv["version"] == 1
        assert len(inv["tasks"]) > 0

    def test_empty_tasks_list_is_valid(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"version": 1, "updated": "2026-04-16", "tasks": []}))
        inv = load_inventory(f)
        assert inv["tasks"] == []


from unittest.mock import patch, MagicMock


class TestEndToEndErrorPaths:
    def test_missing_inventory_exits_1_with_emergency_alert(self, tmp_path):
        """Calling watchdog with missing inventory path → exit 1, emergency alert."""
        import pipeline.watchdog as wd

        args = MagicMock(all=True, tier=None, dry_run=True, inventory=tmp_path / "absent.json")

        with patch("pipeline.watchdog.send_or_log_digest") as mock_send:
            with pytest.raises(SystemExit) as exc:
                wd.run(args, inventory_path=args.inventory)
            assert exc.value.code == 1
            mock_send.assert_called_once()
            # First positional arg is the emergency digest string
            emergency_msg = mock_send.call_args[0][0]
            assert "EMERGENCY" in emergency_msg
            assert "inventory" in emergency_msg.lower()

    def test_scheduler_query_failure_skips_drift_continues_file_checks(self, tmp_path, monkeypatch):
        """If PowerShell fails, drift is skipped but file checks still run, exit 0."""
        import pipeline.watchdog as wd

        # Minimal valid inventory
        inv = tmp_path / "inv.json"
        inv.write_text(json.dumps({
            "version": 1, "updated": "2026-04-16",
            "tasks": [{
                "task_name": "AnkaTest", "tier": "info", "cadence_class": "daily",
                "outputs": [], "grace_multiplier": 1.5, "notes": "",
            }],
        }))
        # Redirect side-effect paths to tmp so no real state/log file is touched
        state = tmp_path / "state.json"
        monkeypatch.setattr(wd, "STATE_PATH", state)
        monkeypatch.setattr(wd, "ALERT_FALLBACK_PATH", tmp_path / "alerts.log")

        from pipeline.watchdog_scheduler import SchedulerQueryError
        with patch("pipeline.watchdog.query_anka_tasks", side_effect=SchedulerQueryError("ps fail")):
            with patch("pipeline.watchdog.send_or_log_digest") as mock_send:
                args = MagicMock(all=True, tier=None, dry_run=True, inventory=inv)
                exit_code = wd.run(args, inventory_path=inv)
        assert exit_code == 0  # ran cleanly despite drift-skip
