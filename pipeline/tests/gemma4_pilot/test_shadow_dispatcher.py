"""ShadowDispatcher contract tests. Mocks Provider via MagicMock so no
network calls happen.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 6)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from pipeline.gemma4_pilot.shadow_dispatcher import ShadowDispatcher
from pipeline.llm_providers.base import ProviderResponse


def _resp(provider, text, latency=1.0):
    return ProviderResponse(
        text=text,
        usage={"input_tokens": 1, "output_tokens": 1},
        provider=provider,
        model="m",
        latency_s=latency,
    )


def test_dispatcher_returns_primary_when_no_shadow(tmp_path):
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK")
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="news_classification",
        date_iso="2026-04-29",
        primary=primary,
        shadow=None,
        prompt="classify this",
        retrieved_context=None,
        meta={"item_id": "x"},
    )
    assert text == "PRIMARY OK"
    primary.generate.assert_called_once()
    rubric.assert_called_once()


def test_dispatcher_runs_both_in_shadow_mode(tmp_path):
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK", latency=2.0)
    shadow = MagicMock()
    shadow.generate.return_value = _resp("gemma4-local", "SHADOW OK", latency=70.0)
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="article_draft",
        date_iso="2026-04-29",
        primary=primary,
        shadow=shadow,
        prompt="write the article",
        retrieved_context=[{"text": "ctx"}],
        meta={"topic": "markets"},
    )
    assert text == "PRIMARY OK"  # production still consumes primary
    primary.generate.assert_called_once()
    shadow.generate.assert_called_once()
    assert rubric.call_count == 2

    # Check JSONL written
    audit_files = list((tmp_path / "audit" / "article_draft").glob("*.jsonl"))
    assert len(audit_files) == 1
    rec = json.loads(audit_files[0].read_text().strip())
    assert rec["primary"]["text"] == "PRIMARY OK"
    assert rec["shadow"]["text"] == "SHADOW OK"


def test_dispatcher_swallows_shadow_failures(tmp_path):
    """Shadow MUST NOT break production. If gemma errors, prod still
    returns primary."""
    primary = MagicMock()
    primary.generate.return_value = _resp("gemini-flash", "PRIMARY OK")
    shadow = MagicMock()
    shadow.name = "gemma4-local"
    shadow.generate.side_effect = RuntimeError("ollama down")
    rubric = MagicMock(return_value={"score": 1.0, "pass": True, "notes": ""})

    d = ShadowDispatcher(audit_root=tmp_path, rubric_fn=rubric)
    text = d.dispatch(
        task="eod_narrative",
        date_iso="2026-04-29",
        primary=primary,
        shadow=shadow,
        prompt="hi",
        retrieved_context=None,
        meta={},
    )
    assert text == "PRIMARY OK"

    audit_files = list((tmp_path / "audit" / "eod_narrative").glob("*.jsonl"))
    rec = json.loads(audit_files[0].read_text().strip())
    assert rec["shadow"]["error"] == "ollama down"
    assert rec["primary"]["text"] == "PRIMARY OK"
