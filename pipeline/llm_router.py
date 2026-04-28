"""Central LLM routing layer.

Per task: pick a provider in {live, shadow, disabled} mode.

  live      -- gemma serves prod traffic; current stack runs as shadow
                (logged only).
  shadow    -- current stack serves prod traffic; gemma runs as shadow
                (logged only). Days 1-7 default.
  disabled  -- current stack serves prod traffic; gemma not invoked at
                all. Used for auto-rollback after a guardrail fires.

Mode flips are JSON edits (pipeline/config/llm_routing.json), no code
change. The dispatcher (Task 6) consumes (primary, shadow) and decides
which output is served vs. logged based on the mode field; the router
itself is mode-blind, returning the configured (primary, shadow) tuple
for live and shadow modes alike.

Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 4)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "llm_routing.json"


@dataclass(frozen=True)
class RoutingConfig:
    default_primary: str
    default_fallback: str
    tasks: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "RoutingConfig":
        cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
        raw = json.loads(cfg_path.read_text())
        return cls(
            default_primary=raw["default_primary"],
            default_fallback=raw["default_fallback"],
            tasks=raw.get("tasks", {}),
        )


@dataclass
class LLMRouter:
    config: RoutingConfig
    providers: Mapping[str, Any]  # name -> Provider instance

    def providers_for(self, task: str) -> tuple[Any, Any | None]:
        """Return (primary_provider, shadow_provider_or_None) for the named task."""
        task_cfg = self.config.tasks.get(task)
        if task_cfg is None:
            return self.providers[self.config.default_primary], None

        mode = task_cfg["mode"]
        primary_name = task_cfg.get("primary", self.config.default_primary)

        if mode in ("live", "shadow"):
            shadow_name = task_cfg.get("shadow")
            return (
                self.providers[primary_name],
                self.providers.get(shadow_name) if shadow_name else None,
            )
        if mode == "disabled":
            return self.providers[primary_name], None
        raise ValueError(f"unknown mode {mode!r} for task {task!r}")
