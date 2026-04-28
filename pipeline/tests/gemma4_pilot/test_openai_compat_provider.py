"""Contract tests for the OpenAI-compatible provider (Ollama / Gemma 4
+ any OpenAI-shaped /v1/chat/completions endpoint).

Network calls are mocked via requests-mock — no real ollama needed.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 2)
"""
from __future__ import annotations

import pytest
import requests_mock as _rm

from pipeline.llm_providers.openai_compat import OpenAICompatProvider


@pytest.fixture
def mock_ollama():
    with _rm.Mocker() as m:
        m.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "id": "x",
                "choices": [
                    {
                        "message": {"content": "hello world"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                },
                "model": "gemma4:26b",
            },
            status_code=200,
        )
        yield m


def test_generate_no_context(mock_ollama):
    p = OpenAICompatProvider(
        name="gemma4-local",
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b",
        api_key="ollama",
    )
    r = p.generate("say hello", retrieved_context=None)
    assert r.text == "hello world"
    assert r.provider == "gemma4-local"
    assert r.model == "gemma4:26b"
    assert r.usage["input_tokens"] == 5
    assert r.usage["output_tokens"] == 2
    assert r.latency_s >= 0


def test_generate_includes_retrieved_context_in_system(mock_ollama):
    p = OpenAICompatProvider(
        name="gemma4-local",
        base_url="http://127.0.0.1:11434/v1",
        model="gemma4:26b",
        api_key="ollama",
    )
    p.generate(
        "question?",
        retrieved_context=[{"text": "fact A"}, {"text": "fact B"}],
    )
    sent = mock_ollama.request_history[-1].json()
    msgs = sent["messages"]
    # System message must precede user message and include both context docs
    assert msgs[0]["role"] == "system"
    assert "fact A" in msgs[0]["content"]
    assert "fact B" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "question?"


def test_http_error_raises():
    with _rm.Mocker() as m:
        m.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            status_code=503,
            text="model loading",
        )
        p = OpenAICompatProvider(
            name="gemma4-local",
            base_url="http://127.0.0.1:11434/v1",
            model="gemma4:26b",
            api_key="ollama",
        )
        with pytest.raises(RuntimeError, match="503"):
            p.generate("hi")
