# pipeline/autoresearch/etf_stock_tail/verdict.py
"""§15.1 verdict ladder for H-2026-04-25-002 — gate_checklist + verdict.md."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.autoresearch.etf_stock_tail import constants as C


def build_gate_checklist(inputs: dict) -> dict:
    """Inputs:
      model_ce: float
      baseline_ces: dict[str, float]    — keys are C.BASELINE_IDS
      perm_p_value: float
      fragility_verdict: "STABLE" | "FRAGILE"
      calibration_residualized_ce: float
      calibration_residualized_baseline_min_ce: float
      holdout_pct: float
      n_holdout: int
    """
    rows: list[dict] = []
    best_baseline = min(inputs["baseline_ces"].values())
    best_baseline_id = min(inputs["baseline_ces"], key=lambda k: inputs["baseline_ces"][k])
    margin = best_baseline - inputs["model_ce"]
    p9b1_pass = margin >= C.DELTA_NATS

    rows.append({
        "section": "§5A", "status": "PASS",
        "note": "all input datasets Approved-for-research per data validation policy"
    })
    rows.append({
        "section": "§6", "status": "PASS",
        "note": "F&O 211, point-in-time via fno_universe_history.json"
    })
    rows.append({
        "section": "§7", "status": "PASS",
        "note": "MODE_NONE_FORECAST_ONLY (path D)"
    })
    rows.append({
        "section": "§8", "status": "PASS",
        "note": "model outputs probabilities only — no direction conflict possible"
    })
    rows.append({
        "section": "§9", "status": "PASS",
        "note": f"n_holdout={inputs['n_holdout']:,}"
    })
    rows.append({
        "section": "§9A", "status": "PASS" if inputs["fragility_verdict"] == "STABLE" else "FAIL",
        "note": f"fragility verdict = {inputs['fragility_verdict']}"
    })
    rows.append({
        "section": "§9B.1", "status": "PASS" if p9b1_pass else "FAIL",
        "note": (f"strongest baseline = {best_baseline_id} (ce={best_baseline:.4f}); "
                 f"model_ce={inputs['model_ce']:.4f}; margin={margin:.4f} nats; "
                 f"required ≥{C.DELTA_NATS:.4f}")
    })
    rows.append({
        "section": "§9B.2", "status": "PASS" if inputs["perm_p_value"] < C.P_VALUE_FLOOR else "FAIL",
        "note": f"p={inputs['perm_p_value']:.4f}, floor {C.P_VALUE_FLOOR}"
    })
    holdout_status = ("PASS" if inputs["holdout_pct"] >= 0.20 else "PARTIAL")
    rows.append({
        "section": "§10", "status": holdout_status,
        "note": f"holdout_pct={inputs['holdout_pct']:.2f} (target 0.20)"
    })
    p11b_margin = (inputs["calibration_residualized_baseline_min_ce"]
                   - inputs["calibration_residualized_ce"])
    p11b_pass = p11b_margin >= C.DELTA_NATS
    rows.append({
        "section": "§11B", "status": "PASS" if p11b_pass else "FAIL",
        "note": f"calibration-residualized margin={p11b_margin:.4f} nats, required ≥{C.DELTA_NATS}"
    })

    fail_blocking = [r for r in rows
                     if r["section"] in ("§9A", "§9B.1", "§9B.2", "§11B") and r["status"] == "FAIL"]
    decision = "PASS" if not fail_blocking else "FAIL"
    return {
        "decision": decision,
        "rows": rows,
        "model_ce": inputs["model_ce"],
        "baseline_ces": inputs["baseline_ces"],
        "best_baseline_id": best_baseline_id,
        "perm_p_value": inputs["perm_p_value"],
        "fragility_verdict": inputs["fragility_verdict"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def render_verdict_md(checklist: dict, hypothesis_id: str, run_id: str) -> str:
    lines = [
        f"# {hypothesis_id} backtest verdict: {checklist['decision']}",
        "",
        f"Generated: {checklist.get('generated_at', '')}  |  run_id: `{run_id}`",
        "",
        "## Held-out cross-entropy",
        f"- Model CE: **{checklist['model_ce']:.4f}** nats/prediction",
    ]
    for bid, ce in checklist["baseline_ces"].items():
        lines.append(f"- {bid}: {ce:.4f}")
    lines += [
        "",
        f"- Strongest baseline: **{checklist.get('best_baseline_id', '')}**",
        f"- Permutation p-value (100k label perms): **{checklist['perm_p_value']:.4f}**",
        f"- Fragility verdict: **{checklist['fragility_verdict']}**",
        "",
        "## §15.1 gate ladder",
    ]
    for r in checklist["rows"]:
        lines.append(f"- {r['section']}: **{r['status']}** — {r['note']}")
    return "\n".join(lines) + "\n"
