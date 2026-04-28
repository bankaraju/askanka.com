"""Provider protocol -- every LLM backend implements this to be routable.

Wrapper pattern (resolved §10 of design doc): each provider gets a prompt
+ a list of retrieved-context documents, returns ProviderResponse.
Routing decisions live in llm_router, not in the providers themselves.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    usage: Mapping[str, int]
    provider: str
    model: str
    latency_s: float
    raw: Mapping[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        ...
