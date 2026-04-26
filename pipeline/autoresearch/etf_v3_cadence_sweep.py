"""ETF v3 — empirical refit-cadence sweep.

The cycle-3 verdict picked the v3 CURATED-30 winner at refit_interval=5
(weekly) without testing the choice. Five days is a tradition inherited
from production v2's Saturday-22:00 schedule, not an empirical optimum.

This sweep runs the SAME rolling walk-forward at cadences 3, 5, 7, 10, 15
trading days on the SAME panel + SAME curated-30 + SAME 756-day lookback
+ SAME 2000-iter Karpathy + SAME seed scheme. For each cadence we report:

  - pooled OOS accuracy + edge over majority baseline
  - 95% bootstrap CI on accuracy
  - year-by-year decomposition (decay test)
  - mean cosine similarity between consecutive weight vectors
    (weight-stability proxy — closer to 1.0 = less churn = less overfit
    risk; closer to 0 = the optimizer is finding a different solution
    every refit, which is a red flag even if pooled accuracy is high)

The decision rule:
  1. Pooled edge > 0 with non-negative 95%-CI lower bound preferred.
  2. Among edges within bootstrap noise of the best, prefer higher
     weight stability (cosine_sim >= 0.85 considered stable).
  3. Among ties on stability, prefer the LONGER cadence (less compute,
     less rebalance churn for live trading).

Output: pipeline/data/research/etf_v3/2026-04-26-cadence-sweep-verdict.md
        pipeline/data/research/etf_v3/cadence_sweep_summary.json

Usage:
    python -m pipeline.autoresearch.etf_v3_cadence_sweep \\
        --cadences 3 5 7 10 15 --feature-set curated
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from pipeline.autoresearch.etf_v3_rolling_refit import (
    RollingRefitConfig,
    run_rolling_refit,
)

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"


def _bootstrap_ci(per_window_detail, n_iter=2000, seed=42):
    rng = np.random.default_rng(seed)
    flat = []
    for w in per_window_detail:
        n = w["pred_n"]
        acc = w["pred_acc_pct"]
        s = round(n * acc / 100.0)
        flat.extend([1] * s + [0] * (n - s))
    arr = np.asarray(flat)
    if len(arr) == 0:
        return None
    boot = np.array([
        arr[rng.integers(0, len(arr), len(arr))].mean() * 100
        for _ in range(n_iter)
    ])
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def _year_break(per_window_detail):
    out = {}
    for yr in ["2024", "2025", "2026"]:
        yws = [w for w in per_window_detail if w["refit_anchor"].startswith(yr)]
        if not yws:
            continue
        n_pred = sum(w["pred_n"] for w in yws)
        n_correct = sum(round(w["pred_n"] * w["pred_acc_pct"] / 100) for w in yws)
        out[yr] = round(n_correct / max(n_pred, 1) * 100, 2)
    return out


def _weight_stability(per_window_detail) -> dict:
    """Compute cosine similarity between consecutive weight vectors.

    Returns mean, std, min, and per-pair list. High mean = stable optimizer.
    Low mean = the search is finding qualitatively different solutions each
    refit, which usually means overfitting to noise in the trailing window.
    """
    vecs = []
    keys: list[str] = []
    for w in per_window_detail:
        wts = w.get("weights") or {}
        if not wts:
            continue
        if not keys:
            keys = sorted(wts.keys())
        vecs.append(np.array([wts.get(k, 0.0) for k in keys], dtype=float))
    if len(vecs) < 2:
        return {"available": False, "n_pairs": 0}
    sims = []
    for a, b in zip(vecs[:-1], vecs[1:]):
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            continue
        sims.append(float(np.dot(a, b) / (na * nb)))
    if not sims:
        return {"available": False, "n_pairs": 0}
    return {
        "available": True,
        "n_pairs": len(sims),
        "cos_sim_mean": float(np.mean(sims)),
        "cos_sim_std": float(np.std(sims)),
        "cos_sim_min": float(np.min(sims)),
        "cos_sim_max": float(np.max(sims)),
    }


def run_sweep(
    cadences: list[int],
    feature_set: str = "curated",
    lookback_days: int = 756,
    n_iterations: int = 2000,
    seed: int = 42,
    eval_start: str = "2024-04-23",
    eval_end: str = "2026-04-23",
) -> dict:
    rows = []
    for cadence in cadences:
        logger.info("=" * 60)
        logger.info("Running cadence=%d days, feature_set=%s", cadence, feature_set)
        logger.info("=" * 60)
        cfg = RollingRefitConfig(
            refit_interval_days=cadence,
            lookback_days=lookback_days,
            n_iterations=n_iterations,
            seed=seed,
            eval_start=eval_start,
            eval_end=eval_end,
            feature_set=feature_set,
        )
        result = run_rolling_refit(cfg)
        pwd = result["per_window_detail"]
        ci = _bootstrap_ci(pwd) or (None, None)
        years = _year_break(pwd)
        stab = _weight_stability(pwd)

        row = {
            "cadence_days": cadence,
            "n_refits": result["n_refit_windows"],
            "n_oos_pred": result["n_total_oos_predictions"],
            "acc_pct": round(result["overall_acc_pct"], 2),
            "baseline_pct": round(result["overall_baseline_majority_pct"], 2),
            "edge_pp": round(result["overall_edge_pp"], 2),
            "ci_lo": round(ci[0], 2) if ci[0] is not None else None,
            "ci_hi": round(ci[1], 2) if ci[1] is not None else None,
            "frac_pos": round(result["fraction_windows_positive"], 3),
            "year_2024": years.get("2024"),
            "year_2025": years.get("2025"),
            "year_2026": years.get("2026"),
            "weight_stability": stab,
        }
        rows.append(row)
        logger.info("cadence=%d -> acc=%.2f edge=%+.2fpp CI=[%s, %s] cos_sim_mean=%s",
                    cadence, row["acc_pct"], row["edge_pp"],
                    row["ci_lo"], row["ci_hi"],
                    f"{stab.get('cos_sim_mean'):.3f}" if stab.get('available') else "n/a")

    return {
        "feature_set": feature_set,
        "lookback_days": lookback_days,
        "n_iterations": n_iterations,
        "seed": seed,
        "eval_window": [eval_start, eval_end],
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "rows": rows,
    }


def _format_verdict_md(summary: dict) -> str:
    rows = summary["rows"]
    lines = []
    lines.append("# ETF v3 — Refit Cadence Sweep Verdict")
    lines.append("")
    lines.append(f"**Generated:** {summary['generated_at_utc']}")
    lines.append(f"**Feature set:** {summary['feature_set']} (curated 30 ETFs)")
    lines.append(f"**Lookback:** {summary['lookback_days']} trading days")
    lines.append(f"**Optimizer:** Karpathy random search, "
                 f"{summary['n_iterations']} iter, seed={summary['seed']}")
    lines.append(f"**Eval window:** {summary['eval_window'][0]} -> {summary['eval_window'][1]}")
    lines.append("")
    lines.append("## Headline table")
    lines.append("")
    lines.append("| cadence | refits | OOS-n | acc | edge | 95% CI | "
                 "frac+ | 2024 | 2025 | 2026 | wt-stab |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        ci = (f"[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]"
              if r['ci_lo'] is not None else "n/a")
        wstab = (f"{r['weight_stability'].get('cos_sim_mean'):.3f}"
                 if r['weight_stability'].get('available') else "n/a")
        lines.append(
            f"| {r['cadence_days']}d | {r['n_refits']} | {r['n_oos_pred']} | "
            f"{r['acc_pct']:.2f}% | {r['edge_pp']:+.2f}pp | {ci} | "
            f"{r['frac_pos']:.2f} | "
            f"{r['year_2024']:.2f}% | {r['year_2025']:.2f}% | "
            f"{r['year_2026']:.2f}% | {wstab} |"
        )
    lines.append("")

    # Recommendation logic
    lines.append("## Recommendation logic")
    lines.append("")
    valid = [r for r in rows if r["edge_pp"] is not None]
    if not valid:
        lines.append("- No valid runs.")
        return "\n".join(lines)

    best_edge = max(r["edge_pp"] for r in valid)
    near_best = [r for r in valid if r["edge_pp"] >= best_edge - 0.5]
    stable_near_best = [
        r for r in near_best
        if r["weight_stability"].get("available")
        and r["weight_stability"].get("cos_sim_mean", 0) >= 0.85
    ]
    if stable_near_best:
        winner = max(stable_near_best, key=lambda r: r["cadence_days"])
        rationale = (
            f"Edge within 0.5pp of best ({best_edge:+.2f}pp) AND weight "
            f"stability >= 0.85 — picked LONGEST stable cadence to minimise "
            f"refit churn / live-trading rebalance cost."
        )
    elif near_best:
        winner = max(near_best, key=lambda r: r["edge_pp"])
        rationale = (
            f"No cadence cleared the wt-stab >= 0.85 bar — picked highest-edge "
            f"cadence ({winner['edge_pp']:+.2f}pp) but flag instability for "
            f"forward-shadow monitoring."
        )
    else:
        winner = max(valid, key=lambda r: r["edge_pp"])
        rationale = "Picked highest pooled edge; no other cadence within 0.5pp."

    lines.append(f"- **Best pooled edge:** {best_edge:+.2f}pp")
    lines.append(f"- **Within 0.5pp of best:** "
                 f"{[r['cadence_days'] for r in near_best]}")
    lines.append(f"- **Stable (cos_sim >= 0.85) AND within 0.5pp:** "
                 f"{[r['cadence_days'] for r in stable_near_best]}")
    lines.append(f"- **Decision:** **cadence={winner['cadence_days']} days**")
    lines.append(f"- **Rationale:** {rationale}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- **Weight stability** is mean cosine similarity between consecutive "
        "refit weight vectors. 1.0 = identical; 0 = orthogonal. Values < 0.7 "
        "suggest the optimizer is overfitting to short-window noise."
    )
    lines.append(
        "- **frac+** is the fraction of refit windows with positive edge "
        "vs majority baseline. Production cadence should ideally be in the "
        "0.55+ range."
    )
    lines.append(
        "- **Per-year decay test:** if 2026 < 2024 by more than 5pp, the "
        "configuration is regime-fragile regardless of pooled edge."
    )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="ETF v3 refit-cadence sweep")
    p.add_argument("--cadences", type=int, nargs="+", default=[3, 5, 7, 10, 15],
                   help="trading-day intervals to test")
    p.add_argument("--feature-set", choices=["all", "curated"], default="curated")
    p.add_argument("--lookback-days", type=int, default=756)
    p.add_argument("--n-iterations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--eval-start", default="2024-04-23")
    p.add_argument("--eval-end", default="2026-04-23")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    summary = run_sweep(
        cadences=args.cadences,
        feature_set=args.feature_set,
        lookback_days=args.lookback_days,
        n_iterations=args.n_iterations,
        seed=args.seed,
        eval_start=args.eval_start,
        eval_end=args.eval_end,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "cadence_sweep_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", json_path)

    md_path = OUT_DIR / "2026-04-26-cadence-sweep-verdict.md"
    md_path.write_text(_format_verdict_md(summary), encoding="utf-8")
    logger.info("wrote %s", md_path)

    print(_format_verdict_md(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
