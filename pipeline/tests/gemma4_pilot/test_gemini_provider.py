"""Gemini provider wrapper contract test. Uses an injected MagicMock
client so no real API call is made.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 3)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_normalizes_response():
    fake_client = MagicMock()
    fake_resp = SimpleNamespace(
        text="hello",
        usage_metadata=SimpleNamespace(
            prompt_token_count=10, candidates_token_count=2
        ),
    )
    fake_client.models.generate_content.return_value = fake_resp

    p = GeminiProvider(
        name="gemini-flash", model="gemini-2.5-flash", client=fake_client
    )
    r = p.generate("ping", retrieved_context=[{"text": "facts"}])

    assert r.text == "hello"
    assert r.provider == "gemini-flash"
    assert r.model == "gemini-2.5-flash"
    assert r.usage == {"input_tokens": 10, "output_tokens": 2}

    sent_kwargs = fake_client.models.generate_content.call_args.kwargs
    contents = sent_kwargs["contents"]
    assert "facts" in contents
    assert "ping" in contents
