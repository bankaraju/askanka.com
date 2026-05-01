"""Theme Detector v1 — weekly orchestrator.

Loads frozen theme universe + signal modules, runs Belief + Confirmation
aggregation, applies credibility penalty, runs lifecycle classifier, writes
output JSON.

Run signature:
    python -m pipeline.research.theme_detector.detector \
        --run-date 2026-05-04 \
        --themes pipeline/research/theme_detector/themes_frozen.json \
        --state-dir pipeline/data/research/theme_detector/state \
        --output-dir pipeline/data/research/theme_detector

NOT a trading rule. NO files match kill-switch regex.

Spec: docs/superpowers/specs/2026-05-01-theme-detector-design.md
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline.research.theme_detector import DETECTOR_VERSION
from pipeline.research.theme_detector.credibility import (
    compute_credibility_penalty,
    compute_current_strength,
)
from pipeline.research.theme_detector.lifecycle import (
    ThemeState,
    classify_transition,
    is_downstream_entry_permitted,
)
from pipeline.research.theme_detector.signals.base import Signal, SignalResult
from pipeline.research.theme_detector.signals.belief.fii_drift import FIIDriftSignal
from pipeline.research.theme_detector.signals.belief.ipo_cluster import IPOClusterSignal
from pipeline.research.theme_detector.signals.confirmation.cap_drift import CapDriftSignal
from pipeline.research.theme_detector.signals.confirmation.earnings_breadth import (
    EarningsBreadthSignal,
)
from pipeline.research.theme_detector.signals.confirmation.fo_inclusion import FOInclusionSignal
from pipeline.research.theme_detector.signals.confirmation.rs_breakout import RSBreakoutSignal
from pipeline.research.theme_detector.signals.confirmation.sector_breadth import (
    SectorBreadthSignal,
)
from pipeline.research.theme_detector.state import load_state, save_state

# Phase 1 signal roster. B1/B2/B4/C4 are Phase 2/3 (added when data lands).
BELIEF_SIGNALS: list[Signal] = [FIIDriftSignal(), IPOClusterSignal()]
CONFIRMATION_SIGNALS: list[Signal] = [
    RSBreakoutSignal(),
    CapDriftSignal(),
    FOInclusionSignal(),
    EarningsBreadthSignal(),
    SectorBreadthSignal(),
]

# Per-signal weights within bucket (FROZEN at v1; renormalized over available
# signals when some emit None).
BELIEF_WEIGHTS = {
    "B1_ma_flow": 0.30,
    "B2_capex": 0.25,
    "B3_fii_drift": 0.20,
    "B4_block_deals": 0.05,
    "B5_ipo_cluster": 0.20,
}
CONFIRMATION_WEIGHTS = {
    "C1_rs_breakout": 0.30,
    "C2_cap_drift": 0.20,
    "C3_fo_inclusion": 0.10,
    "C4_options_skew": 0.05,
    "C5_earnings_breadth": 0.20,
    "C6_sector_breadth": 0.15,
}


def aggregate_bucket(results: list[SignalResult], weights: dict[str, float]) -> float:
    """Aggregate a bucket's per-signal scores into [0, 1].

    Renormalizes weights over signals that returned non-None. If ALL signals are
    None, returns 0.0 with no penalty (the bucket simply has no information).
    """
    available = [(r, weights.get(r.signal_id, 0.0)) for r in results if r.score is not None]
    if not available:
        return 0.0
    total_w = sum(w for _, w in available)
    if total_w <= 0:
        return 0.0
    weighted = sum(r.score * w for r, w in available) / total_w
    return max(0.0, min(1.0, weighted))


def run_detector(
    run_date: date,
    themes: list[dict],
    states: dict[str, ThemeState],
) -> dict[str, Any]:
    """Run one weekly cycle. Returns the output dict + updated state dict."""
    out_themes: list[dict[str, Any]] = []
    next_states: dict[str, ThemeState] = {}
    stage_counts = {
        "DORMANT": 0, "PRE_IGNITION": 0, "IGNITION": 0,
        "MATURE": 0, "DECAY": 0, "FALSE_POSITIVE": 0,
    }

    run_date_str = run_date.isoformat()

    for theme in themes:
        theme_id = theme["theme_id"]
        belief_results = [s.compute_for_theme(theme, run_date) for s in BELIEF_SIGNALS]
        conf_results = [s.compute_for_theme(theme, run_date) for s in CONFIRMATION_SIGNALS]

        belief_score = aggregate_bucket(belief_results, BELIEF_WEIGHTS)
        confirmation_score = aggregate_bucket(conf_results, CONFIRMATION_WEIGHTS)

        prior_state = states.get(theme_id, ThemeState(theme_id=theme_id))
        next_state = classify_transition(
            prior_state, belief_score, confirmation_score, run_date_str
        )

        penalty = compute_credibility_penalty(
            belief_score, confirmation_score, next_state.lifecycle_stage_age_weeks
        )
        strength = compute_current_strength(belief_score, confirmation_score, penalty)

        next_states[theme_id] = next_state
        stage_counts[next_state.lifecycle_stage] += 1

        signal_breakdown = {r.signal_id: r.score for r in belief_results + conf_results}

        out_themes.append({
            "theme_id": theme_id,
            "lifecycle_stage": next_state.lifecycle_stage,
            "lifecycle_stage_age_weeks": next_state.lifecycle_stage_age_weeks,
            "first_detected_date": next_state.first_detected_date,
            "first_pre_ignition_date": next_state.first_pre_ignition_date,
            "first_ignition_date": next_state.first_ignition_date,
            "belief_score": round(belief_score, 4),
            "confirmation_score": round(confirmation_score, 4),
            "credibility_penalty": round(penalty, 4),
            "current_strength": round(strength, 4),
            "signal_breakdown": signal_breakdown,
            "members": _members_payload(theme),
            "warnings": next_state.warnings,
            "downstream_entry_permitted": is_downstream_entry_permitted(
                next_state.lifecycle_stage
            ),
        })

    output = {
        "run_date": run_date_str,
        "detector_version": DETECTOR_VERSION,
        "n_themes_total": len(out_themes),
        "stage_counts": stage_counts,
        "themes": out_themes,
    }
    return {"output": output, "next_states": next_states}


def _members_payload(theme: dict) -> list[dict]:
    """Render theme members for output. At v1 each member emits theme_strength_per_name=0.5
    placeholder; the per-name ranking layer is wired in Phase 1 closeout once cap
    + ADV data is reliably available.
    """
    rule = theme.get("rule_definition", {})
    if "members" in rule:
        return [
            {
                "symbol": sym,
                "theme_strength_per_name": 0.5,
                "free_float_weight_pct": None,
                "adv_60d_inr_cr": None,
                "fno_eligible": None,
            }
            for sym in rule["members"]
        ]
    return []


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-date", required=True, help="YYYY-MM-DD (Sunday weekly)")
    p.add_argument("--themes", required=True, type=Path)
    p.add_argument("--state-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()

    run_dt = datetime.strptime(args.run_date, "%Y-%m-%d").date()

    themes = json.loads(args.themes.read_text(encoding="utf-8"))["themes"]

    state_path = args.state_dir / "theme_states.json"
    states = load_state(state_path)

    result = run_detector(run_dt, themes, states)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"themes_{args.run_date}.json"
    out_path.write_text(json.dumps(result["output"], indent=2), encoding="utf-8")

    save_state(state_path, result["next_states"])

    print(f"[theme_detector] {args.run_date}: wrote {out_path}")
    print(f"  stage_counts: {result['output']['stage_counts']}")


if __name__ == "__main__":
    main()
