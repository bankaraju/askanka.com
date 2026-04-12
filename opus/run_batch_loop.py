"""
OPUS ANKA — Autonomous Batch Loop

Runs the Phase 2 Trust Score batch in a loop until all stocks are scored.
Handles crashes, restarts, and logs everything. Designed to run unattended.

Usage:
    python run_batch_loop.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"
LOGS = Path(__file__).parent / "logs"
PROGRESS_FILE = ARTIFACTS / "batch_progress.json"
LOOP_LOG = LOGS / "batch_loop.log"

MAX_ITERATIONS = 20
SLEEP_BETWEEN = 30  # seconds between restart attempts


def log(msg: str):
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOOP_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_remaining_count() -> tuple[int, int]:
    """Returns (scored, total_needed)."""
    try:
        progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        scored = len(progress.get("scored", []))

        # Count stocks with usable PDFs
        total = 0
        from run_batch_universe import load_fno_stocks
        symbols = load_fno_stocks()
        for sym in symbols:
            pdf_dir = ARTIFACTS / sym / "pdfs"
            if pdf_dir.exists() and list(pdf_dir.glob("annual_report_*.pdf")):
                total += 1
        return scored, total
    except Exception as e:
        log(f"Could not read progress: {e}")
        return 0, 213


def main():
    log("="*70)
    log("ANKA BATCH LOOP — autonomous Phase 2 runner")
    log("="*70)

    for iteration in range(1, MAX_ITERATIONS + 1):
        scored, total = get_remaining_count()
        remaining = total - scored
        log(f"Iteration {iteration}: {scored}/{total} scored, {remaining} remaining")

        if remaining <= 0:
            log("✓ BATCH COMPLETE — all stocks scored")
            break

        log(f"Starting batch runner...")

        try:
            result = subprocess.run(
                ["C:/Python313/python.exe", "-X", "utf8", "run_batch_universe.py", "score"],
                cwd=str(Path(__file__).parent),
                capture_output=False,  # Let it stream to its own logs
                timeout=14400,  # 4 hours max per iteration
            )
            log(f"Batch runner exited with code {result.returncode}")
        except subprocess.TimeoutExpired:
            log(f"Batch runner hit 4-hour timeout — will restart")
        except Exception as e:
            log(f"Batch runner crashed: {e}")

        scored_after, _ = get_remaining_count()
        progress_made = scored_after - scored
        log(f"Iteration {iteration} complete: +{progress_made} stocks scored (total: {scored_after}/{total})")

        if progress_made == 0 and iteration < MAX_ITERATIONS:
            log(f"No progress in iteration {iteration} — waiting {SLEEP_BETWEEN}s before retry")
            time.sleep(SLEEP_BETWEEN)

        if scored_after >= total:
            log("✓ All stocks scored — loop exiting")
            break

    # Final status
    final_scored, final_total = get_remaining_count()
    log("="*70)
    log(f"LOOP FINISHED: {final_scored}/{final_total} stocks scored")
    log("="*70)


if __name__ == "__main__":
    main()
