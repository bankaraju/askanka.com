"""Anthropic provider wrapper. Normalises onto ProviderResponse.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 3)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pipeline.llm_providers.base import ProviderResponse


@dataclass
class AnthropicProvider:
    name: str
    model: str
    client: Any = None  # anthropic.Anthropic instance; injected for testability
    max_tokens: int = 4096

    def __post_init__(self):
        if self.client is None:
            import anthropic  # lazy import -- keeps tests dep-free

            self.client = anthropic.Anthropic()

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        system_parts = [
            "You are a domain expert. Be concise and grounded in the provided context."
        ]
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            system_parts.append(f"CONTEXT:\n{ctx_block}")
        system = "\n\n".join(system_parts)

        t0 = time.monotonic()
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", 0.2),
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_s = time.monotonic() - t0

        text = "".join(
            block.text for block in msg.content if hasattr(block, "text")
        )
        return ProviderResponse(
            text=text,
            usage={
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            },
            provider=self.name,
            model=msg.model,
            latency_s=latency_s,
        )
