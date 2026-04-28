"""Shadow-mode dispatcher.

Calls primary (the current production stack) synchronously. If a shadow
provider is configured, also calls it but never lets a shadow failure or
shadow latency block the production path. Logs both via AuditLogger and
runs the per-task rubric on each output.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 6)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pipeline.gemma4_pilot.audit_logger import AuditLogger
from pipeline.llm_providers.base import Provider


RubricFn = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
"""Signature: rubric_fn(text, meta) -> {'score': float, 'pass': bool, 'notes': str}"""


@dataclass
class ShadowDispatcher:
    audit_root: Path
    rubric_fn: RubricFn

    def __post_init__(self):
        self._logger = AuditLogger(root=self.audit_root)

    def dispatch(
        self,
        *,
        task: str,
        date_iso: str,
        primary: Provider,
        shadow: Provider | None,
        prompt: str,
        retrieved_context: Sequence[Mapping[str, Any]] | None,
        meta: Mapping[str, Any],
    ) -> str:
        primary_resp, primary_err = self._safe_generate(
            primary, prompt, retrieved_context
        )
        if primary_err is not None:
            # Production failure -- propagate, do not silently swallow
            raise primary_err

        primary_score = self._safe_rubric(primary_resp.text, meta)

        shadow_block: dict[str, Any]
        if shadow is None:
            shadow_block = {"provider": None}
        else:
            shadow_resp, shadow_err = self._safe_generate(
                shadow, prompt, retrieved_context
            )
            if shadow_err is not None:
                shadow_block = {
                    "provider": getattr(shadow, "name", "shadow"),
                    "error": str(shadow_err),
                }
            else:
                shadow_score = self._safe_rubric(shadow_resp.text, meta)
                shadow_block = {
                    "provider": shadow_resp.provider,
                    "model": shadow_resp.model,
                    "text": shadow_resp.text,
                    "latency_s": shadow_resp.latency_s,
                    "usage": dict(shadow_resp.usage),
                    "rubric_score": shadow_score["score"],
                    "rubric_pass": shadow_score["pass"],
                    "rubric_notes": shadow_score["notes"],
                }

        ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
        record = {
            "ts": dt.datetime.now(ist).isoformat(),
            "task": task,
            "meta": dict(meta),
            "primary": {
                "provider": primary_resp.provider,
                "model": primary_resp.model,
                "text": primary_resp.text,
                "latency_s": primary_resp.latency_s,
                "usage": dict(primary_resp.usage),
                "rubric_score": primary_score["score"],
                "rubric_pass": primary_score["pass"],
                "rubric_notes": primary_score["notes"],
            },
            "shadow": shadow_block,
        }
        self._logger.log(task=task, date_iso=date_iso, record=record)

        return primary_resp.text

    @staticmethod
    def _safe_generate(provider, prompt, ctx):
        try:
            r = provider.generate(prompt, retrieved_context=ctx)
            return r, None
        except Exception as exc:  # noqa: BLE001
            return None, exc

    def _safe_rubric(self, text, meta):
        try:
            return self.rubric_fn(text, meta)
        except Exception as exc:  # noqa: BLE001
            return {"score": 0.0, "pass": False, "notes": f"rubric_error: {exc}"}
