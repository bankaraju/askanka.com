"""Anthropic provider wrapper contract test. Uses an injected MagicMock
client so no real API call is made.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 3)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_normalizes_response():
    fake_client = MagicMock()
    fake_msg = SimpleNamespace(
        content=[SimpleNamespace(text="hello")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        model="claude-haiku-4-5-20251001",
    )
    fake_client.messages.create.return_value = fake_msg

    p = AnthropicProvider(
        name="claude-haiku",
        model="claude-haiku-4-5-20251001",
        client=fake_client,
    )
    r = p.generate("ping", retrieved_context=[{"text": "facts"}])

    assert r.text == "hello"
    assert r.provider == "claude-haiku"
    assert r.model == "claude-haiku-4-5-20251001"
    assert r.usage == {"input_tokens": 10, "output_tokens": 2}

    # Verify retrieved_context flowed into the system prompt
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert "facts" in call_kwargs["system"]
