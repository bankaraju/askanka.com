"""
Batch data retrieval orchestrator for all 213 F&O stocks.

Coordinates transcript, annual report, and quarterly filing retrieval
across Screener, BSE, NSE, EODHD, and IndianAPI with rate limiting,
caching, and resume capability.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from opus.pipeline.retrieval.transcripts import fetch_transcripts
from opus.pipeline.retrieval.annual_reports import fetch_annual_reports
from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

log = logging.getLogger("opus.batch_retrieval")

IST = timezone(timedelta(hours=5, minutes=30))
MIN_TRANSCRIPTS = 8

DEFAULT_FNO = Path(__file__).parent.parent / "config" / "fno_stocks.json"
DEFAULT_SCRIP_MAP = Path(__file__).parent.parent / "config" / "bse_scrip_map.json"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "artifacts"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def run_batch(
    fno_path: Path = DEFAULT_FNO,
    scrip_map_path: Path = DEFAULT_SCRIP_MAP,
    output_dir: Path = DEFAULT_OUTPUT,
    delay: float = 1.0,
    force: bool = False,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    fno = _load_json(fno_path)
    symbols = fno.get("symbols", [])
    scrip_map = _load_json(scrip_map_path).get("mappings", {})

    progress_path = output_dir / "batch_progress.json"
    progress = _load_json(progress_path)
    completed = set(progress.get("completed", []))

    if force:
        completed = set()

    log.info("Batch retrieval: %d stocks, %d already completed", len(symbols), len(completed))

    fully_covered = 0
    partial_transcripts = 0
    failed = 0

    for i, symbol in enumerate(symbols):
        if symbol in completed:
            fully_covered += 1
            continue

        bse_scrip = scrip_map.get(symbol, {}).get("bse_scrip", "")
        log.info("[%d/%d] %s (BSE: %s)", i + 1, len(symbols), symbol, bse_scrip or "N/A")

        try:
            transcripts = fetch_transcripts(symbol, cache_dir=output_dir / "transcripts")
            annual = fetch_annual_reports(bse_scrip, symbol)
            quarterly = fetch_quarterly_filings(bse_scrip, symbol)

            if len(transcripts) >= MIN_TRANSCRIPTS:
                fully_covered += 1
                log.info("  %s: %d transcripts, %d AR, %d quarterly ✓",
                         symbol, len(transcripts), len(annual), len(quarterly))
            else:
                partial_transcripts += 1
                log.info("  %s: %d transcripts (< %d, flagged for imputation), %d AR, %d quarterly",
                         symbol, len(transcripts), MIN_TRANSCRIPTS, len(annual), len(quarterly))

            completed.add(symbol)
            progress["completed"] = list(completed)
            progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

        except Exception as exc:
            failed += 1
            log.error("  %s: FAILED — %s", symbol, exc)

        if delay > 0 and i < len(symbols) - 1:
            time.sleep(delay)

    summary = {
        "run_date": datetime.now(IST).strftime("%Y-%m-%d"),
        "total": len(symbols),
        "fully_covered": fully_covered,
        "partial_transcripts": partial_transcripts,
        "imputation_needed": partial_transcripts,
        "failed": failed,
    }

    summary_path = output_dir / "retrieval_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Batch complete: %s", json.dumps(summary))

    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    force = "--force" in sys.argv
    run_batch(force=force)
