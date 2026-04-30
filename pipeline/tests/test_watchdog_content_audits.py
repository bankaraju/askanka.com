"""Tests for pipeline.watchdog_content_audits.

Each audit gets a deterministic happy path + one failure case. The
mtime-driven test for stale-OPEN rows uses a fixed today_iso so it
doesn't drift with the system clock.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import watchdog_content_audits as audits


# ---------------------------------------------------------------------------
# audit_stale_open_rows
# ---------------------------------------------------------------------------

class TestStaleOpenRows:
    def test_no_issue_when_no_open_rows(self, tmp_path, monkeypatch):
        ledger = tmp_path / "live_paper_options_ledger.json"
        ledger.write_text(json.dumps([
            {"signal_id": "x", "status": "CLOSED", "open_date": "2026-04-28"},
        ]))
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        assert audits.audit_stale_open_rows(today_iso="2026-04-30") == []

    def test_open_row_today_is_not_stale(self, tmp_path, monkeypatch):
        ledger = tmp_path / "live_paper_options_ledger.json"
        ledger.write_text(json.dumps([
            {"signal_id": "x", "status": "OPEN", "open_date": "2026-04-30"},
        ]))
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        assert audits.audit_stale_open_rows(today_iso="2026-04-30") == []

    def test_open_row_from_yesterday_fires_with_self_heal(self, tmp_path, monkeypatch):
        ledger = tmp_path / "live_paper_options_ledger.json"
        ledger.write_text(json.dumps([
            {"signal_id": "2026-04-28_IEX_1533", "status": "OPEN",
             "entry_time": "2026-04-29T09:25:11+05:30"},
        ]))
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        issues = audits.audit_stale_open_rows(today_iso="2026-04-30")
        assert len(issues) == 1
        assert issues[0]["kind"] == "STALE_OPEN_ROWS"
        assert "2026-04-28_IEX_1533" in issues[0]["detail"]
        assert issues[0]["self_heal"] == "phase_c_options_sidecar_close"

    def test_unreadable_ledger_fires_distinct_kind(self, tmp_path, monkeypatch):
        ledger = tmp_path / "live_paper_options_ledger.json"
        ledger.write_text("not json {")
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        issues = audits.audit_stale_open_rows(today_iso="2026-04-30")
        assert len(issues) == 1
        assert issues[0]["kind"] == "LEDGER_UNREADABLE"

    def test_missing_ledger_is_skipped_silently(self, tmp_path, monkeypatch):
        # New paired surface that hasn't shipped yet — don't false-alarm.
        ledger = tmp_path / "does_not_exist.json"
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        assert audits.audit_stale_open_rows(today_iso="2026-04-30") == []

    def test_futures_ledger_fires_without_self_heal(self, tmp_path, monkeypatch):
        # Phase C futures has its own close path (cmd_close); only options
        # auto-self-heals via the sidecar. Futures stale should still alert.
        ledger = tmp_path / "live_paper_ledger.json"
        ledger.write_text(json.dumps([
            {"signal_id": "y", "status": "OPEN", "open_date": "2026-04-28"},
        ]))
        monkeypatch.setattr(audits, "STALE_OPEN_LEDGERS", (ledger,))
        issues = audits.audit_stale_open_rows(today_iso="2026-04-30")
        assert len(issues) == 1
        assert issues[0]["self_heal"] is None


# ---------------------------------------------------------------------------
# audit_provenance_drift
# ---------------------------------------------------------------------------

class TestProvenanceDrift:
    def test_in_tolerance_no_issue(self, tmp_path, monkeypatch):
        data = tmp_path / "today.json"
        prov = tmp_path / "today.json.provenance.json"
        data.write_text("{}")
        prov.write_text("{}")
        # Both written ~now → lag is 0
        monkeypatch.setattr(audits, "PROVENANCE_PAIRS",
                            ((data, prov, 6 * 3600),))
        assert audits.audit_provenance_drift() == []

    def test_data_newer_than_prov_beyond_tolerance_fires(self, tmp_path, monkeypatch):
        data = tmp_path / "today.json"
        prov = tmp_path / "today.json.provenance.json"
        data.write_text("{}")
        prov.write_text("{}")
        # Backdate prov by 10 hours; tolerance is 6h
        old = time.time() - 10 * 3600
        os.utime(prov, (old, old))
        monkeypatch.setattr(audits, "PROVENANCE_PAIRS",
                            ((data, prov, 6 * 3600),))
        issues = audits.audit_provenance_drift()
        assert len(issues) == 1
        assert issues[0]["kind"] == "PROVENANCE_DRIFT"
        assert "lag" in issues[0]["detail"]

    def test_missing_prov_sidecar_fires_distinct_kind(self, tmp_path, monkeypatch):
        data = tmp_path / "today.json"
        prov = tmp_path / "today.json.provenance.json"
        data.write_text("{}")
        # prov absent
        monkeypatch.setattr(audits, "PROVENANCE_PAIRS",
                            ((data, prov, 6 * 3600),))
        issues = audits.audit_provenance_drift()
        assert len(issues) == 1
        assert issues[0]["kind"] == "PROVENANCE_MISSING"

    def test_missing_data_file_skipped(self, tmp_path, monkeypatch):
        data = tmp_path / "today.json"
        prov = tmp_path / "today.json.provenance.json"
        # both absent — OUTPUT_MISSING handles the data-file case
        monkeypatch.setattr(audits, "PROVENANCE_PAIRS",
                            ((data, prov, 6 * 3600),))
        assert audits.audit_provenance_drift() == []


# ---------------------------------------------------------------------------
# audit_cross_host_regime
# ---------------------------------------------------------------------------

class TestCrossHostRegime:
    def _setup_laptop(self, tmp_path, regime, ts="2026-04-30T09:25:12+05:30"):
        laptop_root = tmp_path
        laptop_data = laptop_root / "pipeline/data/today_regime.json"
        laptop_data.parent.mkdir(parents=True, exist_ok=True)
        laptop_data.write_text(json.dumps({"regime": regime, "timestamp": ts}))
        return laptop_root

    def test_match_no_issue(self, tmp_path, monkeypatch):
        root = self._setup_laptop(tmp_path, "NEUTRAL")
        monkeypatch.setattr(audits, "REPO_ROOT", root)
        monkeypatch.setattr(audits, "_ssh_read",
                            lambda p, timeout=10: json.dumps({"regime": "NEUTRAL",
                                                              "timestamp": "2026-04-30T09:25:12+05:30"}))
        assert audits.audit_cross_host_regime() == []

    def test_drift_fires_with_self_heal(self, tmp_path, monkeypatch):
        root = self._setup_laptop(tmp_path, "NEUTRAL")
        monkeypatch.setattr(audits, "REPO_ROOT", root)
        monkeypatch.setattr(audits, "_ssh_read",
                            lambda p, timeout=10: json.dumps({"regime": "RISK-ON",
                                                              "timestamp": "2026-04-25T04:45:20+05:30"}))
        issues = audits.audit_cross_host_regime()
        assert len(issues) == 1
        assert issues[0]["kind"] == "HOST_DRIFT"
        assert issues[0]["self_heal"] == "push_to_vps"
        assert "NEUTRAL" in issues[0]["detail"] and "RISK-ON" in issues[0]["detail"]

    def test_timestamp_lag_fires_even_if_value_matches(self, tmp_path, monkeypatch):
        # Same regime label, but VPS file is 24h stale — lag check catches it
        root = self._setup_laptop(tmp_path, "NEUTRAL", ts="2026-04-30T09:25:00+05:30")
        monkeypatch.setattr(audits, "REPO_ROOT", root)
        monkeypatch.setattr(audits, "_ssh_read",
                            lambda p, timeout=10: json.dumps({"regime": "NEUTRAL",
                                                              "timestamp": "2026-04-29T03:00:00+05:30"}))
        issues = audits.audit_cross_host_regime()
        assert len(issues) == 1
        assert issues[0]["kind"] == "HOST_TIMESTAMP_LAG"
        assert issues[0]["self_heal"] == "push_to_vps"

    def test_vps_unreachable_fires_no_false_drift(self, tmp_path, monkeypatch):
        # Network/SSH failure must NOT be reported as drift — that would
        # falsely accuse VPS of having wrong content when we just couldn't read.
        root = self._setup_laptop(tmp_path, "NEUTRAL")
        monkeypatch.setattr(audits, "REPO_ROOT", root)
        monkeypatch.setattr(audits, "_ssh_read", lambda p, timeout=10: None)
        issues = audits.audit_cross_host_regime()
        assert len(issues) == 1
        assert issues[0]["kind"] == "VPS_UNREACHABLE"
        assert issues[0]["self_heal"] is None  # nothing safe to do

    def test_vps_corrupt_json_fires_with_self_heal(self, tmp_path, monkeypatch):
        root = self._setup_laptop(tmp_path, "NEUTRAL")
        monkeypatch.setattr(audits, "REPO_ROOT", root)
        monkeypatch.setattr(audits, "_ssh_read", lambda p, timeout=10: "not json {")
        issues = audits.audit_cross_host_regime()
        assert len(issues) == 1
        assert issues[0]["kind"] == "VPS_FILE_CORRUPT"
        assert issues[0]["self_heal"] == "push_to_vps"
