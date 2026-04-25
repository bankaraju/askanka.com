"""18-month backfill for the earnings calendar.

Fetches /corporate_actions for every F&O ticker once. The endpoint
already returns multi-year history per stock, so a single pass per
ticker yields the full 18-month window (and more — older entries are
kept for survivorship audits).

Run-once:
    python -m pipeline.scripts.backfill_earnings_calendar

Idempotent re-runs are safe; ``store.append_history`` dedupes by
(symbol, event_date, asof). Per-symbol HTTP failures are quarantined
and logged, not raised, per data validation policy §9.3."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from pipeline.earnings_calendar import run_for_universe

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "pipeline" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill_earnings_calendar")


def _load_universe() -> list[str]:
    """Canonical F&O list. Prefers ``fno_universe_history.json`` when
    available (point-in-time correct); otherwise falls back to the
    ``fno_historical/*.csv`` directory listing. The fallback is
    survivorship-uncorrected — a known caveat per backtesting-specs §6.2."""
    hist_p = REPO_ROOT / "pipeline" / "data" / "fno_universe_history.json"
    if hist_p.exists():
        body = json.loads(hist_p.read_text())
        if "snapshots" in body:
            snaps = body.get("snapshots", [])
            if snaps:
                latest = max(snaps, key=lambda s: s.get("date", ""))
                return sorted(latest.get("symbols", []))
        elif body:
            latest_key = max(body.keys())
            return sorted(body[latest_key])
    csv_dir = REPO_ROOT / "pipeline" / "data" / "fno_historical"
    return sorted([p.stem for p in csv_dir.glob("*.csv")])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--asof", default=dt.date.today().isoformat())
    p.add_argument(
        "--data-dir",
        default=str(REPO_ROOT / "pipeline" / "data" / "earnings_calendar"),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on universe size (smoke-test convenience)",
    )
    args = p.parse_args()

    asof = dt.date.fromisoformat(args.asof)
    universe = _load_universe()
    if args.limit is not None:
        universe = universe[: args.limit]
    log.info("universe size: %d", len(universe))

    report = run_for_universe(universe, data_dir=args.data_dir, asof=asof)
    log.info("backfill report: %s", json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
