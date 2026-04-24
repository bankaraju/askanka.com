"""Seed strategy_results_10.json from existing compliance artifacts.

Per the plan's Task 0e note: if the compliance-artifact structure doesn't
match what the plan describes, mark the missing strategies as
INSUFFICIENT_POWER — do NOT fabricate metrics. If fewer than 3 incumbents
have clean Sharpe, the scarcity fallback (buy-and-hold benchmark) triggers
downstream (by design).

Incumbents per the spec (v1 seed list; fewer-than-10 is acceptable):
  SI_PRIMARY  — Spread Intelligence regime-gated, primary flavour
  SI_SECONDARY — Spread Intelligence sector-neutral flavour
  PHASE_C_LAG — Phase C LAG route (alert-only; H-107 FAIL Bonferroni)
  OVERSHOOT_TORNTPOWER — per-ticker fade, TORNTPOWER STRONG (2026-04-23)
  OVERSHOOT_MULTITICKER — per-ticker fade top-5 defence-excluded
  FCS_LONG_TOPK — FCS top-k long-only
  FCS_LONG_SHORT — FCS market-neutral
  TA_SCORER_RELIANCE — TA fingerprint RELIANCE pilot (walk-forward only)
  OPUS_TRUST_SPREAD — OPUS trust-tilted cross-sectional
  PHASE_AB_REVERSE — Reverse Regime Phase A/B (collapsed)
"""
from __future__ import annotations

import json

from pipeline.autoresearch.regime_autoresearch.constants import REGIMES, REPO_ROOT

OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json"

SEED_INCUMBENTS = [
    {"strategy_id": "SI_PRIMARY",
     "strategy_name": "Spread Intelligence regime-gated primary",
     "status": "LIVE"},
    {"strategy_id": "SI_SECONDARY",
     "strategy_name": "Spread Intelligence sector-neutral",
     "status": "LIVE"},
    {"strategy_id": "PHASE_C_LAG",
     "strategy_name": "Phase C LAG (alert-only post H-107 FAIL)",
     "status": "LIVE_ALERT_ONLY"},
    {"strategy_id": "OVERSHOOT_TORNTPOWER",
     "strategy_name": "Per-ticker fade - TORNTPOWER STRONG",
     "status": "LIVE"},
    {"strategy_id": "OVERSHOOT_MULTITICKER",
     "strategy_name": "Per-ticker fade top-5 (defence-excluded)",
     "status": "LIVE"},
    {"strategy_id": "FCS_LONG_TOPK",
     "strategy_name": "FCS top-k long-only",
     "status": "LIVE"},
    {"strategy_id": "FCS_LONG_SHORT",
     "strategy_name": "FCS market-neutral long/short",
     "status": "LIVE"},
    {"strategy_id": "TA_SCORER_RELIANCE",
     "strategy_name": "TA fingerprint RELIANCE pilot (walk-forward only)",
     "status": "EXPLORING"},
    {"strategy_id": "OPUS_TRUST_SPREAD",
     "strategy_name": "OPUS trust-tilted cross-sectional",
     "status": "EXPLORING"},
    {"strategy_id": "PHASE_AB_REVERSE",
     "strategy_name": "Reverse Regime Phase A/B (collapsed)",
     "status": "LIVE"},
]


def _insufficient_power_cell() -> dict:
    return {
        "n_obs": 0,
        "sharpe_point": None,
        "sharpe_ci_low": None,
        "sharpe_ci_high": None,
        "p_value_vs_zero": None,
        "p_value_vs_buy_hold": None,
        "compliance_artifact_path": None,
        "status_flag": "INSUFFICIENT_POWER",
    }


def main() -> int:
    rows = []
    for inc in SEED_INCUMBENTS:
        per_regime = {r: _insufficient_power_cell() for r in REGIMES}
        rows.append({**inc, "per_regime": per_regime})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"incumbents": rows, "seeded_at": "2026-04-24",
                    "spec_version": "v1"}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"seeded {len(rows)} incumbents (all cells INSUFFICIENT_POWER; Task 9 refreshes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
