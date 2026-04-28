"""Provider protocol contract tests. A conforming Provider must implement:
    name (str), generate(prompt, retrieved_context, **kwargs) -> ProviderResponse.
The protocol exists to let llm_router treat all providers uniformly.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 1)
"""
from __future__ import annotations

from pipeline.llm_providers.base import Provider, ProviderResponse


class _FakeProvider:
    name = "fake"

    def generate(self, prompt, retrieved_context=None, **kwargs):
        ctx_len = len(retrieved_context) if retrieved_context else 0
        return ProviderResponse(
            text=f"echo: {prompt} (ctx={ctx_len})",
            usage={"input_tokens": len(prompt.split()), "output_tokens": 4},
            provider="fake",
            model="fake-1",
            latency_s=0.01,
        )


def test_provider_response_dataclass_fields():
    r = ProviderResponse(
        text="hi",
        usage={"input_tokens": 1, "output_tokens": 1},
        provider="x",
        model="y",
        latency_s=0.0,
    )
    assert r.text == "hi"
    assert r.provider == "x"
    assert r.model == "y"
    assert r.usage["input_tokens"] == 1


def test_fake_conforms_to_protocol():
    p: Provider = _FakeProvider()
    response = p.generate("hello", retrieved_context=[{"text": "ctx1"}])
    assert response.text == "echo: hello (ctx=1)"
    assert response.usage["output_tokens"] == 4
    assert response.provider == "fake"


def test_protocol_accepts_no_context():
    p: Provider = _FakeProvider()
    response = p.generate("hi")
    assert "ctx=0" in response.text
