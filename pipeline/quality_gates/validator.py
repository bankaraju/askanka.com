"""
Quality Gate System & Anti-Hallucination Guardrails

7 gates that must be checked throughout the pipeline.
Every material claim requires 2+ independent sources.
"""

from dataclasses import dataclass


@dataclass
class GateResult:
    gate: int
    name: str
    passed: bool
    detail: str


def check_gate_1_universe_map(ctx) -> GateResult:
    """All data sources for the entity mapped; gaps identified."""
    has_bse = bool(ctx.bse_scrip)
    has_nse = bool(ctx.nse_symbol)
    has_cin = bool(ctx.cin)
    all_mapped = has_bse and has_nse
    detail = f"BSE={'OK' if has_bse else 'MISSING'} NSE={'OK' if has_nse else 'MISSING'} CIN={'OK' if has_cin else 'MISSING'}"
    return GateResult(1, "Universe Map", all_mapped, detail)


def check_gate_2_gap_closure(ctx) -> GateResult:
    """Missing data points filled or marked unfillable with justification."""
    gaps = []
    if len(ctx.annual_reports) < 5:
        gaps.append(f"annual_reports: {len(ctx.annual_reports)}/5")
    if len(ctx.transcripts) < 8:
        gaps.append(f"transcripts: {len(ctx.transcripts)}/8")
    passed = len(gaps) == 0
    detail = "All filled" if passed else f"Gaps: {', '.join(gaps)}"
    return GateResult(2, "Gap Closure", passed, detail)


def check_gate_3_methodology(ctx) -> GateResult:
    """Key metrics reconstructed and reconciled."""
    has_ratios = len(ctx.ratios) > 0
    detail = f"{len(ctx.ratios)} ratios calculated" if has_ratios else "No ratios computed"
    return GateResult(3, "Methodology Replicated", has_ratios, detail)


def check_gate_4_multi_source(ctx) -> GateResult:
    """Material claims validated by 2+ sources or flagged for divergence."""
    # TODO: Track source count per claim
    return GateResult(4, "Multi-Source Check", False, "Not yet implemented")


def check_gate_5_narrative(ctx) -> GateResult:
    """At least one Narrative vs Numbers conflict surfaced."""
    has_conflicts = any(r.status in ("missed", "quietly_dropped") for r in ctx.promise_delivery)
    detail = "Conflicts surfaced" if has_conflicts else "No narrative conflicts found"
    return GateResult(5, "Narrative Prosecution", has_conflicts, detail)


def check_gate_6_convergence(ctx) -> GateResult:
    """DCF, RIM, and P/B methods checked; 80%+ gaps explained."""
    # TODO: Multi-method valuation convergence
    return GateResult(6, "Method Convergence", False, "Not yet implemented")


def check_gate_7_actionable(ctx) -> GateResult:
    """Final insight follows logically from identified constraints."""
    has_premium = ctx.pattern_premium != 0.0
    detail = f"Pattern Premium: {ctx.pattern_premium:+.1f}%" if has_premium else "No premium calculated"
    return GateResult(7, "Actionable Recommendation", has_premium, detail)


def run_all_gates(ctx) -> list[GateResult]:
    """Run all 7 quality gates and return results."""
    return [
        check_gate_1_universe_map(ctx),
        check_gate_2_gap_closure(ctx),
        check_gate_3_methodology(ctx),
        check_gate_4_multi_source(ctx),
        check_gate_5_narrative(ctx),
        check_gate_6_convergence(ctx),
        check_gate_7_actionable(ctx),
    ]
