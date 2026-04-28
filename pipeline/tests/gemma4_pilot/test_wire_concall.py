"""Smoke test for the wiring helper -- concall supplement path.

Confirms dispatch_for_task threads through the dispatcher cleanly when
both primary and shadow providers are mocked, and that the audit row
gets written.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 11)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from pipeline.gemma4_pilot.wiring import dispatch_for_task
from pipeline.llm_providers.base import ProviderResponse


def _resp(provider: str, text: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        usage={"input_tokens": 1, "output_tokens": 1},
        provider=provider,
        model="m",
        latency_s=1.0,
    )


_VALID_OUTPUT = json.dumps(
    {
        "ticker": "RELIANCE",
        "signal_points": [
            {"point": "a", "stance": "BULLISH"},
            {"point": "b", "stance": "BULLISH"},
            {"point": "c", "stance": "BEARISH"},
        ],
    }
)


def test_dispatch_concall_returns_primary_text(tmp_path: Path, monkeypatch):
    fake_primary = MagicMock()
    fake_primary.generate.return_value = _resp("gemini-flash", _VALID_OUTPUT)
    fake_shadow = MagicMock()
    fake_shadow.generate.return_value = _resp("gemma4-local", _VALID_OUTPUT)

    fake_router = MagicMock()
    fake_router.providers_for.return_value = (fake_primary, fake_shadow)

    monkeypatch.setattr(
        "pipeline.gemma4_pilot.wiring._build_router",
        lambda: fake_router,
    )
    monkeypatch.setattr(
        "pipeline.gemma4_pilot.wiring._AUDIT_ROOT",
        tmp_path,
    )

    out = dispatch_for_task(
        task="concall_supplement",
        prompt="Summarize RELIANCE Q4 concall.",
        retrieved_context=None,
        meta={"ticker": "RELIANCE", "universe": {"RELIANCE", "TCS"}},
    )
    assert "signal_points" in out
    fake_primary.generate.assert_called_once()
    fake_shadow.generate.assert_called_once()

    # Confirm an audit row was written
    audit_files = list((tmp_path / "audit" / "concall_supplement").glob("*.jsonl"))
    assert len(audit_files) == 1
    rows = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])
    assert record["task"] == "concall_supplement"
    assert record["primary"]["provider"] == "gemini-flash"
    assert record["shadow"]["provider"] == "gemma4-local"


def test_dispatch_unknown_task_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown pilot task"):
        dispatch_for_task(task="not_a_task", prompt="x")
