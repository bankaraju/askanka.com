"""Tests kill_switch.py — news-driven framework deprecation on V1 verdict pass."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.research.intraday_v1 import kill_switch


def test_kill_switch_inactive_when_no_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "VERDICT_PATH", tmp_path / "verdict.json")
    assert kill_switch.is_news_driven_killed() is False


def test_kill_switch_active_when_verdict_pass(tmp_path, monkeypatch):
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps({"pass": True, "reason": "ALL_GATES_CLEAR"}), encoding="utf-8")
    monkeypatch.setattr(kill_switch, "VERDICT_PATH", verdict_path)
    assert kill_switch.is_news_driven_killed() is True


def test_kill_switch_inactive_when_verdict_fail(tmp_path, monkeypatch):
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps({"pass": False, "reason": "FRAGILITY_2/12"}), encoding="utf-8")
    monkeypatch.setattr(kill_switch, "VERDICT_PATH", verdict_path)
    assert kill_switch.is_news_driven_killed() is False
