"""H-2026-05-01-phase-c-mr-karpathy-v1 engine package.

Spec: docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
Registry: docs/superpowers/hypothesis-registry.jsonl (terminal_state PRE_REGISTERED)
Holdout window: 2026-05-04 -> 2026-08-01 (auto-extend to 2026-10-31 if n < 100).
Single-touch locked.
"""
from __future__ import annotations

HYPOTHESIS_ID = "H-2026-05-01-phase-c-mr-karpathy-v1"
SPEC_REF = "docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md"
HOLDOUT_OPEN = "2026-05-04"
HOLDOUT_CLOSE = "2026-08-01"
HOLDOUT_EXTEND_TO = "2026-10-31"
MIN_HOLDOUT_N = 100
