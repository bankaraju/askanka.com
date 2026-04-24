"""LLM proposer constrained to the DSL grammar.

View isolation is the critical §0.3 safeguard: this class exposes in-sample
log + strategy_results_10.json but REFUSES access to holdout_outcomes.jsonl.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, PROPOSER_CONTEXT_WINDOW_SIZE, PROPOSER_MODEL, REGIMES,
)
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal, validate


_REGIME_TO_SLUG = {
    "RISK-OFF": "risk_off",
    "CAUTION":  "caution",
    "NEUTRAL":  "neutral",
    "RISK-ON":  "risk_on",
    "EUPHORIA": "euphoria",
}


def log_path_for_regime(regime: str) -> Path:
    """Return the per-regime proposal log path.

    v2 shards the single v1 proposal_log.jsonl into five regime-specific
    files to avoid file-lock contention when Mode 2 runs 5 concurrent
    workers. v1 NEUTRAL history is preserved verbatim in
    proposal_log_neutral.jsonl.
    """
    slug = _REGIME_TO_SLUG.get(regime)
    if slug is None:
        raise ValueError(
            f"unknown regime {regime!r}; expected one of {REGIMES}"
        )
    return DATA_DIR / f"proposal_log_{slug}.jsonl"


@dataclass
class ProposerView:
    in_sample_log: Path
    holdout_log: Path
    strategy_results: Path

    def read_in_sample_tail(self, n: int = PROPOSER_CONTEXT_WINDOW_SIZE) -> list[dict]:
        if not self.in_sample_log.exists():
            return []
        lines = self.in_sample_log.read_text(encoding="utf-8").splitlines()
        return [json.loads(ln) for ln in lines[-n:] if ln.strip()]

    def read_holdout_tail(self, n: int) -> list[dict]:
        raise PermissionError(
            "proposer cannot read holdout_outcomes.jsonl — view isolation invariant"
        )

    def read_strategy_results(self) -> dict:
        if not self.strategy_results.exists():
            return {}
        return json.loads(self.strategy_results.read_text(encoding="utf-8"))


def generate_proposal(view: ProposerView, regime: str, llm_call) -> Proposal:
    """Ask the LLM to emit one grammar-valid Proposal JSON.

    `llm_call` is an injectable callable (Anthropic client.messages.create)
    so tests can pass a deterministic mock. Returns a validated Proposal;
    raises ValueError if the LLM emits an out-of-grammar payload.
    """
    context = {
        "regime": regime,
        "recent_in_sample": view.read_in_sample_tail(),
        "incumbents": view.read_strategy_results(),
    }
    raw_json = llm_call(model=PROPOSER_MODEL, context=context)
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    p = Proposal(**data)
    validate(p)  # raises ValueError on grammar violation
    return p
