"""Single entry point for pilot-routed LLM calls.

Each call site replaces its direct provider call with `dispatch_for_task(...)`.
Routing per `pipeline/config/llm_routing.json` (live / shadow / disabled).

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 11)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline.gemma4_pilot.rubrics import (
    article_draft,
    concall_supplement,
    eod_narrative,
    news_classification,
)
from pipeline.gemma4_pilot.shadow_dispatcher import ShadowDispatcher
from pipeline.llm_providers.anthropic_provider import AnthropicProvider
from pipeline.llm_providers.gemini_provider import GeminiProvider
from pipeline.llm_providers.openai_compat import OpenAICompatProvider
from pipeline.llm_router import LLMRouter, RoutingConfig

_AUDIT_ROOT = (
    Path(__file__).resolve().parents[1] / "data" / "research" / "gemma4_pilot"
)

_RUBRICS = {
    "concall_supplement": concall_supplement.score,
    "news_classification": news_classification.score,
    "eod_narrative": eod_narrative.score,
    "article_draft": article_draft.score,
}


def _build_providers() -> dict:
    return {
        "gemini-flash": GeminiProvider(
            name="gemini-flash", model="gemini-2.5-flash"
        ),
        "claude-haiku": AnthropicProvider(
            name="claude-haiku", model="claude-haiku-4-5-20251001"
        ),
        "gemma4-local": OpenAICompatProvider(
            name="gemma4-local",
            base_url="http://127.0.0.1:11434/v1",
            model="gemma4:26b",
            api_key="ollama",
        ),
    }


def _build_router() -> LLMRouter:
    return LLMRouter(
        config=RoutingConfig.load(),
        providers=_build_providers(),
    )


def dispatch_for_task(
    *,
    task: str,
    prompt: str,
    retrieved_context: Sequence[Mapping[str, Any]] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> str:
    """Pilot entry point. Routes per pipeline/config/llm_routing.json,
    runs shadow if configured, returns production text."""
    rubric_fn = _RUBRICS.get(task)
    if rubric_fn is None:
        raise ValueError(f"unknown pilot task: {task!r}")
    router = _build_router()
    primary, shadow = router.providers_for(task)
    dispatcher = ShadowDispatcher(audit_root=_AUDIT_ROOT, rubric_fn=rubric_fn)
    return dispatcher.dispatch(
        task=task,
        date_iso=dt.date.today().isoformat(),
        primary=primary,
        shadow=shadow,
        prompt=prompt,
        retrieved_context=retrieved_context,
        meta=meta or {},
    )
