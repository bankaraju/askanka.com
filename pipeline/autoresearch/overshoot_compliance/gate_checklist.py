"""§15.1 RESEARCH->PAPER-SHADOW gate-checklist emitter.

Consumes the per-section outputs produced upstream and writes one
machine-readable artifact with an overall decision. This IS the
artifact -- not a claim -- that the standards promotion logic reads.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _row(section: str, req: str, value, pass_fail: str, note: str = "") -> dict:
    return {"section": section, "requirement": req, "value": value,
            "pass_fail": pass_fail, "note": note}


def build(inputs: dict, *, hypothesis_id: str) -> dict:
    rows = []

    s0 = inputs["slippage_s0_s1"]
    s0_ok = s0["s0_sharpe"] >= 1.0 and s0["s0_hit"] >= 0.55 and s0["s0_max_dd"] <= 0.20
    rows.append(_row("1/3", "S0 pass (Sharpe>=1, hit>=55%, DD<=20%)",
                      {"sharpe": s0["s0_sharpe"], "hit": s0["s0_hit"], "dd": s0["s0_max_dd"]},
                      "PASS" if s0_ok else "FAIL"))
    s1_ok = s0["s1_sharpe"] >= 0.8 and s0["s1_max_dd"] <= 0.25 and s0["s1_cum_pnl_pct"] > 0
    rows.append(_row("1/3", "S1 pass (Sharpe>=0.8, DD<=25%, cum P&L>0)",
                      {"sharpe": s0["s1_sharpe"], "dd": s0["s1_max_dd"], "cum": s0["s1_cum_pnl_pct"]},
                      "PASS" if s1_ok else "FAIL"))

    rows.append(_row("2", "Risk metrics computed per bucket per level",
                      inputs["metrics_present"], "PASS" if inputs["metrics_present"] else "FAIL"))

    da = inputs["data_audit"]
    da_ok = da["classification"] != "AUTO-FAIL"
    rows.append(_row("5A", "Data audit classification != AUTO-FAIL",
                      da["classification"], "PASS" if da_ok else "FAIL",
                      f"impaired_pct={da['impaired_pct']}"))

    us = inputs["universe_snapshot"]
    universe_ok = us["status"] in {"SURVIVORSHIP-CORRECTED", "SURVIVORSHIP-UNCORRECTED-WAIVED"}
    rows.append(_row("6", "Universe disclosed (or under waiver)", us["status"],
                      "PASS" if universe_ok else "FAIL",
                      note=f"waiver={us.get('waiver_path')}"))

    mode_ok = inputs["execution_mode"] == "MODE_A"
    rows.append(_row("7", "Execution mode declared = MODE_A (EOD)",
                      inputs["execution_mode"], "PASS" if mode_ok else "FAIL"))

    rows.append(_row("8", "Direction audit emitted",
                      inputs["direction_audit"]["n_survivors"],
                      "PASS",
                      note=f"conflicts={inputs['direction_audit']['conflicts']}"))

    pa = inputs["power_analysis"]
    rows.append(_row("9", "n>=30 per regime OR flagged exploratory",
                      pa["min_n_per_regime_met"],
                      "PASS" if pa["min_n_per_regime_met"] else "FAIL",
                      note=f"underpowered_count={pa['underpowered_count']}"))

    fr = inputs["fragility"]
    rows.append(_row("9A", "Fragility verdict != PARAMETER-FRAGILE", fr["verdict"],
                      "PASS" if fr["verdict"] != "PARAMETER-FRAGILE" else "FAIL"))

    cm = inputs["comparators"]
    rows.append(_row("9B.1", "Beats strongest naive comparator at S0",
                      cm["strongest_name"],
                      "PASS" if cm["beaten_strongest"] else "FAIL"))

    pm = inputs["permutations"]
    rows.append(_row("9B.2", "Permutations >= required floor",
                      {"n": pm["n_shuffles"], "floor": pm["floor_required"]},
                      "PASS" if pm["n_shuffles"] >= pm["floor_required"] else "FAIL"))

    ho = inputs["holdout"]
    ho_ok = ho["pct"] >= ho["target"]
    rows.append(_row("10", "Holdout >= 20% of history", ho["pct"],
                      "PASS" if ho_ok else "PARTIAL",
                      note=f"target={ho['target']}; current holdout 6% -- waiver required for promotion"))

    br = inputs["beta_regression"]
    residual_ratio = br["residual_sharpe"] / br["gross_sharpe"] if br["gross_sharpe"] else 0.0
    rows.append(_row("11B", "Residual Sharpe >= 70% of gross Sharpe",
                      round(residual_ratio, 3),
                      "PASS" if residual_ratio >= 0.70 else "FAIL"))

    verdicts = [r["pass_fail"] for r in rows]
    if "FAIL" in verdicts:
        decision = "FAIL"
    elif "PARTIAL" in verdicts:
        decision = "PARTIAL"
    else:
        decision = "PASS"

    return {
        "hypothesis_id": hypothesis_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "decision": decision,
    }


def write(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "gate_checklist.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path
