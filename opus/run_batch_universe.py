"""
OPUS ANKA — Batch Universe Processor

Processes ALL 213 F&O stocks through the ANKA Trust Score pipeline.
Designed to run unattended for hours. Handles rate limits, failures, restarts.

Phase 1: Data collection (Screener + NSE annual reports) — ~60 min for 213 stocks
Phase 2: Deep Trust Score analysis (Claude API reads annual reports) — ~10-15 hours

Progress saved after each stock. Restarts from where it left off.

Usage:
    python run_batch_universe.py collect    # Phase 1: data collection only
    python run_batch_universe.py score      # Phase 2: deep Trust Score only
    python run_batch_universe.py all        # Both phases sequentially
    python run_batch_universe.py status     # Check progress
"""

import json
import os
import sys
import time
import subprocess
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ARTIFACTS = Path(__file__).parent / "artifacts"
CONFIG = Path(__file__).parent / "config"
LOGS = Path(__file__).parent / "logs"
PROGRESS_FILE = ARTIFACTS / "batch_progress.json"

LOGS.mkdir(exist_ok=True)


def load_fno_stocks() -> list[str]:
    fno = json.loads((CONFIG / "fno_stocks.json").read_text())
    return fno["symbols"]


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"collected": [], "scored": [], "failed_collect": [], "failed_score": [], "started": datetime.now(IST).isoformat()}


def save_progress(progress: dict):
    progress["updated"] = datetime.now(IST).isoformat()
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def log(msg: str):
    ts = datetime.now(IST).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOGS / "batch_universe.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Phase 1: Data Collection ────────────────────────────────────────

def run_collect(symbols: list[str]):
    """Collect Screener financials + NSE annual reports for all stocks."""
    progress = load_progress()
    done = set(progress["collected"])
    failed = set(progress.get("failed_collect", []))
    remaining = [s for s in symbols if s not in done]

    log(f"PHASE 1: DATA COLLECTION — {len(remaining)} remaining of {len(symbols)}")

    for i, sym in enumerate(remaining):
        log(f"  [{len(done)+1}/{len(symbols)}] {sym}...")

        try:
            result = subprocess.run(
                ["C:/Python313/python.exe", "-X", "utf8", "run_research.py", sym],
                capture_output=True, text=True, timeout=120, encoding="utf-8",
                cwd=str(Path(__file__).parent),
            )
            if result.returncode == 0:
                done.add(sym)
                progress["collected"] = sorted(done)
                log(f"    OK")
            else:
                err = result.stderr[-200:] if result.stderr else "unknown"
                log(f"    FAILED: {err}")
                failed.add(sym)
                progress["failed_collect"] = sorted(failed)
        except subprocess.TimeoutExpired:
            log(f"    TIMEOUT")
            failed.add(sym)
            progress["failed_collect"] = sorted(failed)
        except Exception as e:
            log(f"    ERROR: {e}")
            failed.add(sym)
            progress["failed_collect"] = sorted(failed)

        save_progress(progress)

        # Rate limiting: Screener blocks after too many rapid requests
        if (len(done) + len(failed)) % 40 == 0:
            log(f"  Rate limit pause (60s)...")
            time.sleep(60)
        else:
            time.sleep(1.5)

    log(f"PHASE 1 COMPLETE: {len(done)} collected, {len(failed)} failed")
    return progress


# ── Phase 2: Deep Trust Score ────────────────────────────────────────

def run_score(symbols: list[str]):
    """Run deep Trust Score analysis on stocks WITHOUT a valid score.

    A stock is considered "already scored" if its trust_score.json exists AND
    has guidance_scored > 0. Stocks with 0 items (failed extractions from prior
    runs) are eligible for re-scoring with the new provider.
    """
    progress = load_progress()
    done_set = set(progress.get("scored", []))
    failed = set(progress.get("failed_score", []))

    # Check each stock's actual trust_score.json to determine real done status
    real_done = set()
    for sym in done_set:
        ts_file = ARTIFACTS / sym / "trust_score.json"
        if ts_file.exists():
            try:
                t = json.loads(ts_file.read_text(encoding="utf-8"))
                grade = t.get("trust_score_grade", "?")
                if t.get("guidance_scored", 0) > 0 and grade not in ("?", "", "INSUFFICIENT_DATA"):
                    real_done.add(sym)
            except Exception:
                pass

    # Update progress to reflect reality
    progress["scored"] = sorted(real_done)
    save_progress(progress)

    # Build scoreable list: any stock with PDFs that isn't validly scored yet
    scoreable = []
    for sym in symbols:
        if sym in real_done:
            continue
        pdf_dir = ARTIFACTS / sym / "pdfs"
        if pdf_dir.exists() and list(pdf_dir.glob("annual_report_*.pdf")):
            scoreable.append(sym)
            failed.discard(sym)  # Give failed stocks another shot with new provider

    log(f"PHASE 2: DEEP TRUST SCORE — {len(scoreable)} to score ({len(real_done)} already valid)")
    log(f"  Provider: {os.getenv('ANKA_LLM_PROVIDER', 'gemini')}")
    done = real_done

    for i, sym in enumerate(scoreable):
        log(f"  [{len(done)+1}/{len(done)+len(scoreable)}] {sym}...")

        try:
            result = subprocess.run(
                ["C:/Python313/python.exe", "-X", "utf8", "run_trust_score.py", sym],
                capture_output=True, text=True, timeout=600, encoding="utf-8",
                cwd=str(Path(__file__).parent),
            )

            if result.returncode == 0:
                # Stock is considered "done" if narrative extraction produced items
                # (even if scoring yields INSUFFICIENT_DATA — that's an honest result)
                narr_file = ARTIFACTS / sym / "narratives.json"
                has_narratives = False
                total_items = 0
                if narr_file.exists():
                    try:
                        narr = json.loads(narr_file.read_text(encoding="utf-8"))
                        for r in narr:
                            total_items += len(r.get("guidance", r.get("claims", [])))
                        has_narratives = total_items > 0
                    except Exception:
                        pass

                if has_narratives:
                    # Log the actual grade from trust_score.json
                    ts_file = ARTIFACTS / sym / "trust_score.json"
                    grade_line = ""
                    if ts_file.exists():
                        for line in result.stdout.split("\n"):
                            if "ANKA TRUST SCORE:" in line:
                                grade_line = line.strip()
                                break
                    log(f"    {grade_line or 'DONE'} ({total_items} items)")
                    done.add(sym)
                    progress["scored"] = sorted(done)
                else:
                    log(f"    INVALID: extraction produced no items — marked for retry")
                    failed.add(sym)
                    progress["failed_score"] = sorted(failed)
            else:
                err = result.stderr[-200:] if result.stderr else "unknown"
                log(f"    FAILED: {err}")
                failed.add(sym)
                progress["failed_score"] = sorted(failed)
        except subprocess.TimeoutExpired:
            log(f"    TIMEOUT (>10min)")
            failed.add(sym)
            progress["failed_score"] = sorted(failed)
        except Exception as e:
            log(f"    ERROR: {e}")
            failed.add(sym)
            progress["failed_score"] = sorted(failed)

        save_progress(progress)

        # Claude API rate limiting: ~3 calls per stock, be gentle
        time.sleep(5)

    log(f"PHASE 2 COMPLETE: {len(done)} scored, {len(failed)} failed")
    return progress


# ── Status Check ─────────────────────────────────────────────────────

def show_status():
    progress = load_progress()
    symbols = load_fno_stocks()

    collected = len(progress.get("collected", []))
    scored = len(progress.get("scored", []))
    failed_c = len(progress.get("failed_collect", []))
    failed_s = len(progress.get("failed_score", []))

    print(f"ANKA Batch Universe — Status")
    print(f"{'='*50}")
    print(f"Total F&O stocks:     {len(symbols)}")
    print(f"Data collected:       {collected} ({collected/len(symbols)*100:.0f}%)")
    print(f"Deep scored:          {scored} ({scored/len(symbols)*100:.0f}%)")
    print(f"Failed collection:    {failed_c}")
    print(f"Failed scoring:       {failed_s}")
    print(f"Remaining collection: {len(symbols) - collected - failed_c}")
    print(f"Remaining scoring:    {collected - scored - failed_s}")
    print(f"Started:              {progress.get('started', '?')}")
    print(f"Last update:          {progress.get('updated', '?')}")

    # Show scored results
    if scored > 0:
        print(f"\nScored stocks:")
        results = []
        for sym in progress.get("scored", []):
            ts = ARTIFACTS / sym / "trust_score.json"
            if ts.exists():
                t = json.loads(ts.read_text())
                results.append((sym, t.get("trust_score_grade", "?"), t.get("trust_score_pct", 0)))
        results.sort(key=lambda x: x[2], reverse=True)
        for sym, grade, score in results:
            print(f"  {sym:14s} {grade:>3s} {score:>5.0f}%")


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    symbols = load_fno_stocks()

    if mode == "collect":
        run_collect(symbols)
    elif mode == "score":
        run_score(symbols)
    elif mode == "status":
        show_status()
    elif mode == "all":
        run_collect(symbols)
        run_score(symbols)
    else:
        print(f"Usage: python run_batch_universe.py [collect|score|status|all]")
