"""LLMRouter contract tests. Routing config is a flat JSON file so we
can flip a task between LIVE / SHADOW / DISABLED without code changes.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 4)
"""
from __future__ import annotations

import json

import pytest

from pipeline.llm_router import LLMRouter, RoutingConfig


@pytest.fixture
def cfg_path(tmp_path):
    cfg = {
        "default_primary": "gemini-flash",
        "default_fallback": "claude-haiku",
        "tasks": {
            "concall_supplement": {
                "mode": "shadow",
                "primary": "gemini-flash",
                "shadow": "gemma4-local",
            },
            "news_classification": {
                "mode": "live",
                "primary": "gemma4-local",
                "shadow": "gemini-flash",
            },
            "eod_narrative": {
                "mode": "disabled",
                "primary": "gemini-flash",
                "shadow": "gemma4-local",
            },
            "article_draft": {
                "mode": "shadow",
                "primary": "gemini-flash",
                "shadow": "gemma4-local",
            },
        },
    }
    p = tmp_path / "routing.json"
    p.write_text(json.dumps(cfg))
    return p


def test_load_config(cfg_path):
    cfg = RoutingConfig.load(cfg_path)
    assert cfg.tasks["news_classification"]["mode"] == "live"


def test_router_returns_primary_for_live(cfg_path):
    router = LLMRouter(
        RoutingConfig.load(cfg_path),
        providers={
            "gemma4-local": "G",
            "gemini-flash": "F",
            "claude-haiku": "C",
        },
    )
    primary, shadow = router.providers_for("news_classification")
    assert primary == "G"
    assert shadow == "F"


def test_router_returns_primary_for_shadow(cfg_path):
    router = LLMRouter(
        RoutingConfig.load(cfg_path),
        providers={
            "gemma4-local": "G",
            "gemini-flash": "F",
            "claude-haiku": "C",
        },
    )
    primary, shadow = router.providers_for("article_draft")
    assert primary == "F"  # current stack is primary in shadow mode
    assert shadow == "G"  # gemma is shadow


def test_router_disabled_returns_primary_only(cfg_path):
    router = LLMRouter(
        RoutingConfig.load(cfg_path),
        providers={
            "gemma4-local": "G",
            "gemini-flash": "F",
            "claude-haiku": "C",
        },
    )
    primary, shadow = router.providers_for("eod_narrative")
    assert primary == "F"
    assert shadow is None


def test_unknown_task_falls_back_to_default(cfg_path):
    router = LLMRouter(
        RoutingConfig.load(cfg_path),
        providers={
            "gemma4-local": "G",
            "gemini-flash": "F",
            "claude-haiku": "C",
        },
    )
    primary, shadow = router.providers_for("some_other_task")
    assert primary == "F"  # default_primary
    assert shadow is None
