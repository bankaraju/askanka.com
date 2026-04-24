"""Mode 2 orchestrator — spawns 5 regime workers, waits, writes summary.

Each worker runs the proposer+in-sample loop for its regime. Workers are
independent subprocesses so file-lock contention on per-regime proposal
logs is impossible by construction.

Usage:
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 --cap 5 --regime NEUTRAL
    python -m pipeline.autoresearch.regime_autoresearch.scripts.run_mode2 --dry-run --cap 0
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, REGIMES,
)


def _run_worker(regime: str, cap: int, dry_run: bool) -> dict:
    """Spawn `run_pilot.py` as a subprocess for one regime. Returns summary."""
    cmd = [
        sys.executable, "-m",
        "pipeline.autoresearch.regime_autoresearch.scripts.run_pilot",
        "--regime", regime,
        "--auto-approve",
    ]
    if cap is not None:
        cmd += ["--max-iterations", str(cap)]
    if dry_run:
        cmd += ["--dry-run"]
    start = datetime.now(timezone.utc).isoformat()
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=86400)
        return {
            "regime": regime,
            "exit_code": out.returncode,
            "started_at": start,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout_tail": "\n".join(out.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(out.stderr.splitlines()[-30:]),
        }
    except subprocess.TimeoutExpired:
        return {
            "regime": regime,
            "exit_code": -1,
            "started_at": start,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "stdout_tail": "", "stderr_tail": "TIMEOUT after 86400s",
        }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=None,
                    help="per-regime hard proposal cap "
                         "(default: PROPOSALS_PER_REGIME_HARD_CAP)")
    ap.add_argument("--regime", choices=REGIMES, default=None,
                    help="run only one regime (default: all 5 in parallel)")
    ap.add_argument("--dry-run", action="store_true",
                    help="workers exit after startup, do not propose")
    ap.add_argument("--summary-dir", type=Path, default=DATA_DIR,
                    help="where to write run_mode2_summary_*.json")
    args = ap.parse_args(argv)

    regimes_to_run = [args.regime] if args.regime else list(REGIMES)
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cap": args.cap, "dry_run": args.dry_run,
        "regime_results": [],
    }

    if args.dry_run and (args.cap == 0):
        # Fast path for tests: record each regime as a no-op exit=0.
        for r in regimes_to_run:
            summary["regime_results"].append({
                "regime": r, "exit_code": 0,
                "started_at": summary["started_at"],
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "stdout_tail": "dry-run cap=0", "stderr_tail": "",
            })
    else:
        # Parallel workers, bounded to 5 (one per regime).
        with ProcessPoolExecutor(max_workers=len(regimes_to_run)) as pool:
            futures = {
                pool.submit(_run_worker, r, args.cap, args.dry_run): r
                for r in regimes_to_run
            }
            for fut in as_completed(futures):
                summary["regime_results"].append(fut.result())

    summary["ended_at"] = datetime.now(timezone.utc).isoformat()
    ts = summary["started_at"].replace(":", "").replace("-", "")[:15]
    out_path = args.summary_dir / f"run_mode2_summary_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[run_mode2] wrote {out_path}")
    return 0 if all(r["exit_code"] == 0
                      for r in summary["regime_results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
