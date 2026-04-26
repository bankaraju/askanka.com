"""Phase 1 orchestrator: backfill 147 missing F&O tickers, validate, reconcile, write v0.2 parquet.

Usage:
    python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --dry-run
    python -X utf8 -m pipeline.autoresearch.etf_v3_eval.build_extended_replay --tickers-csv pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.cleanliness_gates import run_cleanliness_gates
from pipeline.autoresearch.etf_v3_eval.kite_backfill import BackfillFailure, fetch_minute_bars
from pipeline.autoresearch.etf_v3_eval.manifest import write_manifest
from pipeline.autoresearch.etf_v3_eval.schema_validator import (
    SchemaViolation,
    validate_minute_bars_schema,
)
from pipeline.kite_client import get_kite

logger = logging.getLogger(__name__)

START_DATE = date(2026, 2, 26)
END_DATE = date(2026, 4, 23)
OUTPUT_DIR = Path("pipeline/data/research/etf_v3_evaluation/phase_1_universe")
RAW_OUTPUT = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")


def backfill_one(kite, ticker: str) -> tuple[pd.DataFrame | None, str | None]:
    """Return (frame, None) on success, (None, reason) on failure."""
    try:
        df = fetch_minute_bars(kite, ticker, START_DATE, END_DATE)
    except BackfillFailure as e:
        return None, f"backfill: {e}"
    try:
        validate_minute_bars_schema(df)
    except SchemaViolation as e:
        return None, f"schema: {e}"
    gates = run_cleanliness_gates(df)
    if not gates.passed:
        return None, f"cleanliness: {gates.failures}"
    return df, None


def run(tickers: list[str], dry_run: bool = False) -> dict:
    """Backfill the supplied tickers; return summary dict."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failed_rows: list[dict] = []
    success_frames: list[pd.DataFrame] = []

    if dry_run:
        logger.info("DRY RUN — would backfill %d tickers", len(tickers))
        return {"dry_run": True, "n_tickers": len(tickers)}

    kite = get_kite()
    for i, ticker in enumerate(tickers, start=1):
        logger.info("[%d/%d] %s", i, len(tickers), ticker)
        df, err = backfill_one(kite, ticker)
        if err is not None:
            failed_rows.append({"ticker": ticker, "reason": err})
            continue
        success_frames.append(df)

    pd.DataFrame(failed_rows).to_csv(OUTPUT_DIR / "tickers_failed.csv", index=False)

    if success_frames:
        full = pd.concat(success_frames, ignore_index=True)
        RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        full.to_parquet(RAW_OUTPUT, index=False)

    summary = {
        "n_requested": len(tickers),
        "n_succeeded": len(success_frames),
        "n_failed": len(failed_rows),
        "raw_output": str(RAW_OUTPUT) if success_frames else None,
    }
    (OUTPUT_DIR / "backfill_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    write_manifest(
        out_path=OUTPUT_DIR / "manifest.json",
        run_id=f"phase1_backfill_{START_DATE.isoformat()}_{END_DATE.isoformat()}",
        config={"start": START_DATE.isoformat(), "end": END_DATE.isoformat(), "n_tickers": len(tickers)},
        seed=0,
        artifact_paths=[RAW_OUTPUT, OUTPUT_DIR / "tickers_failed.csv", OUTPUT_DIR / "backfill_summary.json"],
    )
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers-csv", default=str(OUTPUT_DIR / "tickers_added.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tickers = pd.read_csv(args.tickers_csv)["ticker"].tolist()
    summary = run(tickers, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
