"""Tests for the daily Gemma 4 health check.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 19)
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.scripts.gemma4_health_check import run_check


def test_health_pass_when_ping_succeeds(tmp_path: Path, monkeypatch):
    def fake_ping(*_args, **_kwargs):
        return {"ok": True, "latency_s": 12.3, "text": "PONG"}

    monkeypatch.setattr(
        "pipeline.scripts.gemma4_health_check._ping_ollama", fake_ping
    )
    rc = run_check(out_dir=tmp_path)
    assert rc == 0
    out = json.loads((tmp_path / "gemma4_health.json").read_text(encoding="utf-8"))
    assert out["status"] == "OK"
    assert out["latency_s"] == 12.3


def test_health_fail_when_ping_errors(tmp_path: Path, monkeypatch):
    def fake_ping(*_args, **_kwargs):
        return {"ok": False, "error": "connection refused"}

    monkeypatch.setattr(
        "pipeline.scripts.gemma4_health_check._ping_ollama", fake_ping
    )
    monkeypatch.setattr(
        "pipeline.scripts.gemma4_health_check._send_alert",
        lambda *_a, **_k: None,
    )
    rc = run_check(out_dir=tmp_path)
    assert rc == 1
    out = json.loads((tmp_path / "gemma4_health.json").read_text(encoding="utf-8"))
    assert out["status"] == "FAIL"
    assert "connection refused" in out["error"]


def test_health_degraded_when_latency_over_budget(tmp_path: Path, monkeypatch):
    def fake_ping(*_args, **_kwargs):
        return {"ok": True, "latency_s": 95.0, "text": "PONG"}

    monkeypatch.setattr(
        "pipeline.scripts.gemma4_health_check._ping_ollama", fake_ping
    )
    monkeypatch.setattr(
        "pipeline.scripts.gemma4_health_check._send_alert",
        lambda *_a, **_k: None,
    )
    rc = run_check(out_dir=tmp_path)
    assert rc == 0  # degraded != fail; cron should not crash
    out = json.loads((tmp_path / "gemma4_health.json").read_text(encoding="utf-8"))
    assert out["status"] == "DEGRADED"
