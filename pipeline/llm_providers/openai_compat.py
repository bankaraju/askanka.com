"""OpenAI-compatible provider -- works against Ollama, vLLM, OpenAI, etc.

Used for Gemma 4 via Ollama. Ollama exposes /v1/chat/completions in
OpenAI's exact request/response shape, including the `usage` block.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 2)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import requests

from pipeline.llm_providers.base import ProviderResponse

_DEFAULT_TIMEOUT_S = 240  # 4 min -- task #4 article draft latency budget per spec §3.1


@dataclass
class OpenAICompatProvider:
    name: str
    base_url: str
    model: str
    api_key: str = "x"  # ollama ignores this but the field exists in OpenAI-compat
    timeout_s: int = _DEFAULT_TIMEOUT_S

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are a domain expert. Use the following retrieved "
                        "context to answer the user. Do not invent facts beyond "
                        f"it.\n\nCONTEXT:\n{ctx_block}"
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        t0 = time.monotonic()
        r = requests.post(url, json=payload, headers=headers, timeout=self.timeout_s)
        latency_s = time.monotonic() - t0

        if r.status_code != 200:
            raise RuntimeError(
                f"{self.name} HTTP {r.status_code}: {r.text[:500]}"
            )

        body = r.json()
        text = body["choices"][0]["message"]["content"]
        usage_raw = body.get("usage", {}) or {}
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
        }
        return ProviderResponse(
            text=text,
            usage=usage,
            provider=self.name,
            model=self.model,
            latency_s=latency_s,
            raw=body,
        )
