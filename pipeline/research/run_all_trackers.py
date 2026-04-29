"""Single entrypoint — run every registered tracker, emit master_evidence.json.

This is the daily 16:30 IST aggregator: pulls every closed-trade ledger,
runs the standard cohort recipe per family, writes one consolidated
JSON that any session (or downstream consumer) can read to know where
the evidence currently stands.

Usage:
  python -m pipeline.research.run_all_trackers          # write master JSON
  python -m pipeline.research.run_all_trackers --print  # also print to stdout

Produces:
  pipeline/data/research/master_evidence.json

Intentional design: each tracker run is independent. If one fails (e.g.
empty ledger), it gets recorded with status=ERROR but the others still
publish. Failure isolation keeps the master state robust.
"""
from __future__ import annotations

import argparse
import json
import logging
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = PIPELINE_ROOT / "data" / "research"
MASTER_OUT = RESEARCH_DIR / "master_evidence.json"
IST = timezone(timedelta(hours=5, minutes=30))

log = logging.getLogger("anka.run_all_trackers")


def _run_neutral_cohort() -> dict:
    """The proven NEUTRAL VWAP/ORB filter cells."""
    from pipeline.research import neutral_cohort_tracker as nct
    trades = nct.build_cohort_table()
    cells = nct.aggregate_cells(trades)
    summary = nct.write_outputs(trades, cells)
    return summary


def _run_h001_full() -> dict:
    """All H-001 closed trades, all regimes, by sigma_bucket and side."""
    from pipeline.research.cohort_harness import TrackerSpec, run_tracker
    spec = TrackerSpec(
        name="h001_full",
        ledger_path=PIPELINE_ROOT / "data" / "research" / "h_2026_04_26_001" / "recommendations.csv",
        regime_col="regime",
        regime_filter=None,  # all regimes
        extra_columns=["regime", "side", "sigma_bucket", "filter_tag"],
        out_subdir="h001_cohort",
    )
    return run_tracker(spec)


def _run_secrsi() -> dict:
    """SECRSI sector-RS pair tracker."""
    path = PIPELINE_ROOT / "data" / "research" / "h_2026_04_27_secrsi" / "recommendations.csv"
    if not path.exists():
        return {"tracker": "secrsi", "status": "NO_LEDGER", "n_trades": 0}
    from pipeline.research.cohort_harness import TrackerSpec, run_tracker
    spec = TrackerSpec(
        name="secrsi",
        ledger_path=path,
        extra_columns=["side"] if path.exists() else [],
        out_subdir="secrsi_cohort",
    )
    return run_tracker(spec)


# Registry: name → callable.
TRACKERS = {
    "neutral_cohort": _run_neutral_cohort,
    "h001_full": _run_h001_full,
    "secrsi": _run_secrsi,
}


def run_all() -> dict:
    results: dict[str, dict] = {}
    for name, fn in TRACKERS.items():
        try:
            log.info("running tracker: %s", name)
            results[name] = fn()
        except Exception as exc:
            log.error("tracker %s failed: %s", name, exc)
            results[name] = {
                "tracker": name,
                "status": "ERROR",
                "error": str(exc),
                "trace": traceback.format_exc(),
            }

    publish_count = sum(r.get("n_publish", 0) for r in results.values()
                        if isinstance(r, dict))
    monitor_count = sum(r.get("n_monitor", 0) for r in results.values()
                        if isinstance(r, dict))

    master = {
        "as_of": datetime.now(IST).isoformat(),
        "n_trackers": len(results),
        "n_ok": sum(1 for r in results.values() if r.get("status") != "ERROR"),
        "n_error": sum(1 for r in results.values() if r.get("status") == "ERROR"),
        "total_publish_cells": publish_count,
        "total_monitor_cells": monitor_count,
        "trackers": results,
    }
    MASTER_OUT.parent.mkdir(parents=True, exist_ok=True)
    MASTER_OUT.write_text(json.dumps(master, indent=2, default=str), encoding="utf-8")
    return master


def main() -> None:
    p = argparse.ArgumentParser(description="Run every registered cohort tracker")
    p.add_argument("--print", action="store_true", help="also print summaries")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    master = run_all()
    print(f"=== Master Evidence — {master['as_of']} ===")
    print(f"Trackers: {master['n_ok']} OK / {master['n_error']} ERROR")
    print(f"PUBLISH cells: {master['total_publish_cells']}")
    print(f"MONITOR cells: {master['total_monitor_cells']}")
    print(f"Output: {MASTER_OUT.relative_to(PIPELINE_ROOT)}")
    print()

    if args.print:
        for name, res in master["trackers"].items():
            if res.get("status") == "ERROR":
                print(f"  [{name}] ERROR: {res.get('error')}")
                continue
            print(f"  [{name}] N={res.get('n_trades','?')} "
                  f"baseline={res.get('baseline_win_pct','?')}%  "
                  f"PUB={res.get('n_publish',0)} MON={res.get('n_monitor',0)}")


if __name__ == "__main__":
    main()
