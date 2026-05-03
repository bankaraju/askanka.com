"""Section 12 verdict computation + section 1.B null-band routing for H-2026-05-04."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"


def classify_n_qualifying_band(n: int) -> str:
    if n == 0:
        return "FAIL_NO_QUALIFIERS"
    if n <= 4:
        return "FAIL_INSUFFICIENT_QUALIFIERS"
    if n <= 25:
        return "EXPECTED_BAND"
    if n <= 80:
        return "AMPLIFIED_AUDIT_REQUIRED"
    return "FAIL_LEAKAGE_SUSPECT"


def compute_basket_metrics(rows: list[dict]) -> dict:
    """Pooled-basket metrics from closed ledger rows."""
    if not rows:
        return {"n_trades": 0, "hit_rate_pct": 0.0, "mean_pnl_pct": 0.0,
                "sum_pnl_inr": 0.0, "max_drawdown_pct": 0.0}
    pnls_pct = []
    pnls_inr = []
    for r in rows:
        pnl = float(r["pnl_inr"])
        pos = float(r["position_inr"])
        pnls_inr.append(pnl)
        pnls_pct.append(100 * pnl / pos)
    arr = np.array(pnls_pct)
    cum = np.cumsum(np.array(pnls_inr))
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / 50000.0  # drawdown as % of single position size
    return {
        "n_trades": int(len(arr)),
        "hit_rate_pct": float(100 * (arr > 0).mean()),
        "mean_pnl_pct": float(arr.mean()),
        "sum_pnl_inr": float(np.sum(pnls_inr)),
        "max_drawdown_pct": float(dd.min()) if len(dd) else 0.0,
    }


def compute_comparator_baselines(closed_rows: list[dict], holdout_window: tuple) -> dict:
    """Compute B0-B4 pooled metrics. Each baseline is a counterfactual rerun.

    B0 always_long: every qualifying day, LONG every qualifying ticker
    B1 random_direction: same days, coin-flip direction
    B2 flipped: same predictions, opposite side (must lose money)
    B3 passive_nifty: LONG NIFTY 09:15 -> 14:25 every day
    B4 ta_only: see leakage_audit.run_audit_c_ablation (separate run)
    """
    if not closed_rows:
        return {"B2_flipped_mean_pnl_pct": 0.0, "B2_must_lose": False,
                "note": "no closed rows yet"}
    # B2 (flipped): trivially derived — flip the sign of every PnL
    b2_pnl_pct = -float(np.mean([float(r["pnl_inr"]) / float(r["position_inr"]) * 100 for r in closed_rows]))
    # B0/B1/B3 require re-walking the holdout days with different rules — implementation:
    # for v1, we record only B2 inline (most diagnostic). B0/B1/B3/B4 require separate
    # backtest runs over the holdout window which are scoped as Task 13 Step 5 add-on.
    return {"B2_flipped_mean_pnl_pct": b2_pnl_pct, "B2_must_lose": b2_pnl_pct < 0,
            "note": "B0/B1/B3 require separate backtest re-runs; performed at verdict time, not here"}


def main() -> int:
    manifest_path = OUT_DIR / "manifest.json"
    ledger_path = OUT_DIR / "recommendations.csv"
    if not manifest_path.exists():
        print("[verdict] FAIL: no manifest.json")
        return 1
    manifest = json.loads(manifest_path.read_text())
    n_qualifying = manifest["n_qualifying"]
    band = classify_n_qualifying_band(n_qualifying)

    closed_rows = []
    if ledger_path.exists():
        for r in csv.DictReader(open(ledger_path, "r", encoding="utf-8")):
            if r["exit_date"]:
                closed_rows.append(r)

    metrics = compute_basket_metrics(closed_rows)

    # Per spec section 12 PASS bar
    pass_n = n_qualifying >= 5
    pass_trades = metrics["n_trades"] >= 60
    pass_hit = metrics["hit_rate_pct"] >= 55.0
    pass_pnl = metrics["mean_pnl_pct"] >= 0.4

    if band in ("FAIL_NO_QUALIFIERS", "FAIL_INSUFFICIENT_QUALIFIERS", "FAIL_LEAKAGE_SUSPECT"):
        terminal_state = band
    elif band == "AMPLIFIED_AUDIT_REQUIRED":
        terminal_state = "PENDING_AMPLIFIED_AUDIT"
    elif pass_n and pass_trades and pass_hit and pass_pnl:
        terminal_state = "PASS_PRELIMINARY"  # subject to fragility + comparator checks
    else:
        terminal_state = "FAIL_INSUFFICIENT_EDGE"

    holdout_window = (manifest.get("holdout_start", "2026-05-04"),
                      manifest.get("holdout_end", "2026-08-04"))
    comparators = compute_comparator_baselines(closed_rows, holdout_window)

    out = {
        "hypothesis_id": "H-2026-05-04-cross-asset-perstock-lasso-v1",
        "verdict_at": datetime.now().isoformat(),
        "n_qualifying": n_qualifying, "n_qualifying_band": band,
        "metrics": metrics,
        "section_12_gates": {
            "n_qualifying>=5": pass_n,
            "n_trades>=60": pass_trades,
            "hit_rate>=55": pass_hit,
            "mean_pnl>=0.4": pass_pnl,
        },
        "comparators": comparators,
        "terminal_state": terminal_state,
    }
    (OUT_DIR / "terminal_state.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    return 0 if terminal_state.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
