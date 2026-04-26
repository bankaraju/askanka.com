# pipeline/autoresearch/etf_v3_eval/phase_2/gate_ladder.py
"""§15.1 RESEARCH → PAPER-SHADOW gate evaluator.

Per §15.1: pass Sections 1 (S0+S1), 2, 5A, 6, 7, 8, 9, 9A, 9B, 10, 11B.
Pre-registered hypothesis required (Section 14).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

_GENERATOR_VERSION = "phase_2_v1"

# Required keys that must be present in the evidence dict.
_REQUIRED_KEYS = frozenset({
    "s0_pass",
    "s1_pass",
    "data_audit_tag",
    "survivorship_disclosed",
    "entry_timing_pass",
    "direction_audit_verdict",
    "n_trades",
    "min_required",
    "fragility_verdict",
    "naive_benchmark_beaten",
    "purged_walkforward",
    "alpha_after_beta_pass",
    "hypothesis_registered",
})

# Valid enum-like values for tagged fields.
_VALID_DATA_AUDIT_TAGS = {"CLEAN", "DATA-IMPAIRED", "AUTO-FAIL"}
_VALID_DIRECTION_VERDICTS = {"aligned", "suspect"}


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class GateLadderReport:
    verdict: GateVerdict
    failed_gates: List[str] = field(default_factory=list)

    def report_dict(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Return a JSON-serializable dict suitable for writing to gate_ladder_verdict.json."""
        return {
            "verdict": self.verdict.value,
            "failed_gates": list(self.failed_gates),
            "evidence": copy.deepcopy(evidence),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "generator_version": _GENERATOR_VERSION,
        }


def evaluate_research_to_paper_shadow(evidence: dict) -> GateLadderReport:
    """Evaluate whether Phase 2 results pass the §15.1 RESEARCH → PAPER-SHADOW gate.

    Args:
        evidence: Dict containing all required gate inputs. Raises KeyError if
            any required key is missing; raises ValueError if enum-like fields
            contain unknown values.

    Returns:
        GateLadderReport with verdict (PASS/FAIL) and list of failed gate names.
    """
    # Polish delta 1: validate all required keys are present.
    missing = _REQUIRED_KEYS - evidence.keys()
    if missing:
        # Sort for deterministic error messages.
        missing_sorted = sorted(missing)
        raise KeyError(
            f"evidence dict is missing required keys: {missing_sorted}"
        )

    # Polish delta 2: validate enum-like values.
    data_audit_tag = evidence["data_audit_tag"]
    if data_audit_tag not in _VALID_DATA_AUDIT_TAGS:
        raise ValueError(
            f"data_audit_tag must be one of {sorted(_VALID_DATA_AUDIT_TAGS)}, "
            f"got {data_audit_tag!r}"
        )

    direction_audit_verdict = evidence["direction_audit_verdict"]
    if direction_audit_verdict not in _VALID_DIRECTION_VERDICTS:
        raise ValueError(
            f"direction_audit_verdict must be one of {sorted(_VALID_DIRECTION_VERDICTS)}, "
            f"got {direction_audit_verdict!r}"
        )

    failed: list[str] = []

    # §1 S0 + S1 cleanliness
    if not evidence["s0_pass"]:
        failed.append("s0_pass")
    if not evidence["s1_pass"]:
        failed.append("s1_pass")

    # §2 data audit (AUTO-FAIL fails; CLEAN and DATA-IMPAIRED pass)
    if data_audit_tag == "AUTO-FAIL":
        failed.append("data_audit")

    # §5A survivorship bias disclosure
    if not evidence["survivorship_disclosed"]:
        failed.append("survivorship")

    # §6 entry timing
    if not evidence["entry_timing_pass"]:
        failed.append("entry_timing")

    # §7 direction audit
    if direction_audit_verdict != "aligned":
        failed.append("direction_audit")

    # §8 sample size — honour evidence dict's min_required (polish delta 5)
    if evidence["n_trades"] < evidence["min_required"]:
        failed.append("sample_size")

    # §9 fragility
    if evidence["fragility_verdict"] != "stable":
        failed.append("fragility")

    # §9B naive benchmark
    if not evidence["naive_benchmark_beaten"]:
        failed.append("naive_benchmark")

    # §10 purged walk-forward
    if not evidence["purged_walkforward"]:
        failed.append("purged_walkforward")

    # §11B alpha after beta
    if not evidence["alpha_after_beta_pass"]:
        failed.append("alpha_after_beta")

    # §14 hypothesis registry (pre-registration)
    if not evidence["hypothesis_registered"]:
        failed.append("hypothesis_registry")

    return GateLadderReport(
        verdict=GateVerdict.PASS if not failed else GateVerdict.FAIL,
        failed_gates=failed,
    )
