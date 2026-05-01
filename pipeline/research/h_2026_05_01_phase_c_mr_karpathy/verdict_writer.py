"""Verdict writer — fires once at scheduled close (2026-08-01) or extension close (2026-10-31).

Spec section 9 (pass/fail criteria). Single hypothesis, no Bonferroni at verdict.

Inputs: pipeline/data/research/h_2026_05_01_phase_c_mr_karpathy/recommendations.csv
Output: docs/research/h_2026_05_01_phase_c_mr_karpathy/verdict_<YYYY-MM-DD>.{json,md}

Decision tree (from spec):
  - n < MIN_HOLDOUT_N AND date < HOLDOUT_EXTEND_TO -> AUTO_EXTEND
  - n < MIN_HOLDOUT_N AND date == HOLDOUT_EXTEND_TO -> INSUFFICIENT_N -> auto-archive
  - §9.1 + §9.4 + §9.5 PASS -> SIGNAL (or FLAGSHIP if §9.3 stretch met)
  - any of §9.1 / §9.4 / §9.5 FAIL -> RETIRED, mark CONSUMED in registry

This is the SKELETON entry point. Full computation wired before verdict date.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import HOLDOUT_CLOSE, HOLDOUT_EXTEND_TO, HYPOTHESIS_ID, MIN_HOLDOUT_N
from .mr_engine import summarize

REPO = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO / "pipeline" / "data" / "research" / "h_2026_05_01_phase_c_mr_karpathy" / "recommendations.csv"
VERDICT_DIR = REPO / "docs" / "research" / "h_2026_05_01_phase_c_mr_karpathy"


@dataclass
class Verdict:
    hypothesis_id: str
    verdict_date: str
    decision: str               # "PASS_SIGNAL" | "PASS_FLAGSHIP" | "FAIL_RETIRED" | "AUTO_EXTEND" | "INSUFFICIENT_N"
    n: int
    s0: dict
    s1: dict
    s2: dict
    fragility_check_pass: bool
    margin_check_pass: bool
    primary_pass: bool
    stretch_signal_pass: bool
    stretch_flagship_pass: bool
    notes: str = ""


def _read_ledger() -> list[dict]:
    if not LEDGER_PATH.is_file():
        return []
    with LEDGER_PATH.open(encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def write_verdict_files(verdict: Verdict) -> None:
    """Persist verdict as both JSON (machine) and Markdown (human)."""
    VERDICT_DIR.mkdir(parents=True, exist_ok=True)
    base = VERDICT_DIR / f"verdict_{verdict.verdict_date}"
    base.with_suffix(".json").write_text(
        json.dumps(asdict(verdict), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md = _render_markdown(verdict)
    base.with_suffix(".md").write_text(md, encoding="utf-8")


def _render_markdown(v: Verdict) -> str:
    return (
        f"# H-2026-05-01-phase-c-mr-karpathy-v1 Verdict\n\n"
        f"- **Verdict date:** {v.verdict_date}\n"
        f"- **Decision:** `{v.decision}`\n"
        f"- **n:** {v.n} (min required: {MIN_HOLDOUT_N})\n\n"
        f"## S0 (base costs 10 bps round-trip)\n```json\n{json.dumps(v.s0, indent=2)}\n```\n\n"
        f"## S1 (stress 30 bps)\n```json\n{json.dumps(v.s1, indent=2)}\n```\n\n"
        f"## S2 (stress 50 bps)\n```json\n{json.dumps(v.s2, indent=2)}\n```\n\n"
        f"- Primary verdict pass: {v.primary_pass}\n"
        f"- Fragility (3 monthly buckets): {v.fragility_check_pass}\n"
        f"- Margin vs regime-gated-no-Karpathy baseline: {v.margin_check_pass}\n"
        f"- Stretch SIGNAL (Sharpe >= 1.5): {v.stretch_signal_pass}\n"
        f"- Stretch FLAGSHIP (Sharpe >= 2.0, Bharats target): {v.stretch_flagship_pass}\n\n"
        f"## Notes\n{v.notes}\n"
    )


def run(verdict_date: str | None = None) -> Verdict:
    """Compose a verdict for the given date (defaults to today UTC).

    SKELETON: only the count + S0/S1/S2 summaries are wired here. The full
    fragility / margin / permutation tests land before verdict date 2026-08-01.
    """
    if verdict_date is None:
        verdict_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = _read_ledger()
    n = len(rows)

    if n < MIN_HOLDOUT_N:
        decision = "AUTO_EXTEND" if verdict_date < HOLDOUT_EXTEND_TO else "INSUFFICIENT_N"
    else:
        decision = "PENDING_FULL_COMPUTATION"

    return Verdict(
        hypothesis_id=HYPOTHESIS_ID,
        verdict_date=verdict_date,
        decision=decision,
        n=n,
        s0={"status": "SKELETON"},
        s1={"status": "SKELETON"},
        s2={"status": "SKELETON"},
        fragility_check_pass=False,
        margin_check_pass=False,
        primary_pass=False,
        stretch_signal_pass=False,
        stretch_flagship_pass=False,
        notes=(
            f"Skeleton verdict — n={n}; full fragility/margin/permutation pipeline "
            f"lands before holdout close {HOLDOUT_CLOSE}."
        ),
    )
