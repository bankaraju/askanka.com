"""Backfill NSE sectoral indices for H-2026-04-25-001.

Wraps pipeline.research.phase_c_v5.data_prep.backfill_indices.backfill_daily
with the 10 hypothesis-required symbols and writes to
pipeline/data/sectoral_indices/.
"""
from __future__ import annotations
import argparse
import logging
from pathlib import Path

from pipeline.research.phase_c_v5.data_prep.backfill_indices import backfill_daily

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "pipeline" / "data" / "sectoral_indices"

REQUIRED = [
    "BANKNIFTY", "NIFTYIT", "NIFTYPHARMA", "NIFTYAUTO", "NIFTYFMCG",
    "NIFTYMETAL", "NIFTYENERGY", "NIFTYPSUBANK", "NIFTYREALTY", "NIFTYMEDIA",
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1825)
    args = parser.parse_args()
    counts = backfill_daily(REQUIRED, days=args.days, out_dir=OUT)
    for sym, n in counts.items():
        logging.info("%s: %d rows", sym, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
