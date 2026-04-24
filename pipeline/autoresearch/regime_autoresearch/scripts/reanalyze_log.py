"""Re-evaluate all APPROVED historical proposals in proposal_log.jsonl
under the current (3-gate) verdict and produce a comparison report.

After commit fdce57d introduced passes_all_folds_populated, the
historical log still carried 2-gate verdicts. This one-off analysis
script re-runs each APPROVED historical proposal at HEAD, re-computes
the verdict under all 3 gates (delta_in + min_events + all_folds),
and emits a comparison table.

Guardrails:
  - Does NOT mutate proposal_log.jsonl. Uses a tmp log path for
    run_in_sample's persistence side-effect, deleted at the end.
  - No new Haiku calls — we're re-using the DSL already in the log.
  - If run_in_sample errors on a historical proposal (e.g. pair
    construction), we log "SKIP - <reason>" and continue.
"""
from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR
from pipeline.autoresearch.regime_autoresearch.dsl import Proposal
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    run_in_sample,
)
from pipeline.autoresearch.regime_autoresearch.incumbents import load_table
from pipeline.autoresearch.regime_autoresearch.scripts.run_pilot import (
    _build_panel,
    _compute_hurdle,
    _compute_verdict,
    _get_event_dates,
)

LOG_PATH = DATA_DIR / "proposal_log.jsonl"


def _load_approved_rows(log_path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [r for r in rows if r.get("approval_status") == "APPROVED"]


def main() -> int:
    approved = _load_approved_rows(LOG_PATH)
    print(
        f"Evaluating {len(approved)} historical APPROVED proposals under "
        f"3-gate verdict..."
    )
    print()

    panel = _build_panel()
    pseudo = {"NIFTY", "VIX", "REGIME"}
    tickers = sorted(
        t for t in panel["ticker"].unique() if t not in pseudo
    )

    # Group by regime so the hurdle is computed once per regime.
    by_regime: dict[str, list[dict]] = {}
    for r in approved:
        by_regime.setdefault(r["regime"], []).append(r)

    results: list[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_log = Path(tmp) / "reanalyze_scratch.jsonl"

        for regime, regime_rows in by_regime.items():
            event_dates = _get_event_dates(panel, regime)
            # Hurdle differs by hold_horizon (scarcity fallback computes
            # regime-conditional buy-and-hold over the same horizon as
            # the proposal). Compute per-horizon to stay faithful to
            # run_pilot's behaviour.
            hurdle_cache: dict[int, tuple[float, str]] = {}

            for row in regime_rows:
                h = row["hold_horizon"]
                if h not in hurdle_cache:
                    hurdle_cache[h] = _compute_hurdle(
                        regime, panel=panel, event_dates=event_dates,
                        hold_horizon=h,
                    )
                hurdle_sharpe, hurdle_source = hurdle_cache[h]

                try:
                    p = Proposal(
                        feature=row["feature"],
                        construction_type=row["construction_type"],
                        threshold_op=row["threshold_op"],
                        threshold_value=row["threshold_value"],
                        hold_horizon=row["hold_horizon"],
                        regime=row["regime"],
                        pair_id=row.get("pair_id"),
                    )
                    result = run_in_sample(
                        p, panel=panel, event_dates=event_dates,
                        tickers=tickers, log_path=tmp_log,
                        incumbent_sharpe=hurdle_sharpe,
                    )
                except Exception as exc:  # noqa: BLE001 — scripted analysis
                    print(
                        f"SKIP - {row.get('proposal_id', '?')} "
                        f"({row.get('feature', '?')}): "
                        f"{type(exc).__name__}: {exc}"
                    )
                    results.append({
                        "proposal_id": row.get("proposal_id", "?"),
                        "regime": regime,
                        "feature": row.get("feature", "?"),
                        "op": row.get("threshold_op", "?"),
                        "k": row.get("threshold_value", "?"),
                        "h": row.get("hold_horizon", "?"),
                        "old_verdict": (
                            "PASS" if row.get("passes_delta_in") else "FAIL"
                        ),
                        "new_net_sharpe": None,
                        "new_n_events": None,
                        "fold_n_events": None,
                        "fold_sharpes": None,
                        "passes_delta_in": False,
                        "passes_min_events": False,
                        "passes_all_folds": False,
                        "new_verdict": "SKIP",
                    })
                    continue

                verdict = _compute_verdict(
                    n_events=result.get("n_events_in_sample"),
                    net_sharpe=result.get("net_sharpe_in_sample"),
                    hurdle_sharpe=hurdle_sharpe,
                    fold_n_events=result.get("fold_n_events"),
                    insufficient_for_folds=bool(
                        result.get("insufficient_for_folds", False)
                    ),
                )

                results.append({
                    "proposal_id": row["proposal_id"],
                    "regime": regime,
                    "feature": row["feature"],
                    "op": row["threshold_op"],
                    "k": row["threshold_value"],
                    "h": row["hold_horizon"],
                    "old_verdict": (
                        "PASS" if row.get("passes_delta_in") else "FAIL"
                    ),
                    "new_net_sharpe": round(
                        float(result["net_sharpe_in_sample"]), 3
                    ),
                    "new_n_events": int(result["n_events_in_sample"]),
                    "fold_n_events": result.get("fold_n_events"),
                    "fold_sharpes": result.get("fold_sharpes"),
                    "passes_delta_in": verdict["passes_delta_in"],
                    "passes_min_events": verdict["passes_min_events"],
                    "passes_all_folds": (
                        verdict["passes_all_folds_populated"]
                    ),
                    "new_verdict": (
                        "PASS" if verdict["verdict_pass"] else "FAIL"
                    ),
                })

    # Print the comparison table.
    header = (
        f"{'id':15} {'feature':28} {'op':10} {'k':>3} {'h':>3} "
        f"{'old':>4} {'sharpe':>7} {'folds':>20} {'gates':<25} {'new'}"
    )
    print(header)
    print("-" * 140)
    for r in results:
        passed = (
            f"D:{'Y' if r['passes_delta_in'] else 'N'} "
            f"E:{'Y' if r['passes_min_events'] else 'N'} "
            f"F:{'Y' if r['passes_all_folds'] else 'N'}"
        )
        folds_str = (
            str(r["fold_n_events"]) if r["fold_n_events"] else "(single)"
        )
        sharpe_str = (
            f"{r['new_net_sharpe']:+.3f}"
            if r["new_net_sharpe"] is not None else "   n/a"
        )
        print(
            f"{r['proposal_id'][:13]:15} {r['feature'][:26]:28} "
            f"{r['op']:10} {str(r['k']):>3} {str(r['h']):>3} "
            f"{r['old_verdict']:>4} {sharpe_str:>7} {folds_str:>20} "
            f"{passed:<25} {r['new_verdict']}"
        )

    print()
    n_pass_new = sum(1 for r in results if r["new_verdict"] == "PASS")
    n_pass_old = sum(1 for r in results if r["old_verdict"] == "PASS")
    n_total = len(results)
    print(
        f"Summary: {n_pass_new}/{n_total} pass under 3-gate verdict"
    )
    print(
        f"  (was {n_pass_old}/{n_total} under 2-gate verdict)"
    )

    # Detail any surviving PASSes.
    survivors = [r for r in results if r["new_verdict"] == "PASS"]
    if survivors:
        print()
        print("SURVIVORS (still PASS under 3-gate):")
        for r in survivors:
            print(
                f"  {r['proposal_id']} | {r['feature']} "
                f"{r['op']} {r['k']} h={r['h']} | "
                f"sharpe={r['new_net_sharpe']:+.3f} | "
                f"folds_n={r['fold_n_events']} | "
                f"fold_sharpes={r['fold_sharpes']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
