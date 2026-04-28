"""Gemini provider wrapper using google-genai SDK.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 3)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pipeline.llm_providers.base import ProviderResponse


@dataclass
class GeminiProvider:
    name: str
    model: str
    client: Any = None

    def __post_init__(self):
        if self.client is None:
            from google import genai  # lazy import -- keeps tests dep-free

            self.client = genai.Client()

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        ctx_block = ""
        if retrieved_context:
            ctx_block = "\n\n---\n\n".join(d["text"] for d in retrieved_context)
            ctx_block = f"CONTEXT:\n{ctx_block}\n\n---\n\n"
        contents = ctx_block + prompt

        t0 = time.monotonic()
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        latency_s = time.monotonic() - t0

        usage = resp.usage_metadata
        return ProviderResponse(
            text=resp.text,
            usage={
                "input_tokens": getattr(usage, "prompt_token_count", 0),
                "output_tokens": getattr(usage, "candidates_token_count", 0),
            },
            provider=self.name,
            model=self.model,
            latency_s=latency_s,
        )
