"""Daily capture of today_regime.json into the PIT regime tape forward feed.

Run by AnkaPitRegimeTapeCapture at 05:00 IST (after AnkaETFSignal at 04:45).
Audit: docs/superpowers/specs/2026-04-28-pit-regime-tape-data-source-audit.md §G1.

Idempotent — re-running for the same date overwrites only if the new
captured row's `feed_captured_at` is earlier than the existing one (i.e.,
later runs do not silently overwrite the canonical first capture).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TODAY_REGIME_PATH = REPO_ROOT / "pipeline" / "data" / "today_regime.json"
FORWARD_DIR = REPO_ROOT / "pipeline" / "data" / "pit_regime_tape" / "forward"

ALLOWED_ZONES = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}


def capture(target_date: str | None = None, dry_run: bool = False) -> dict:
    """Read today_regime.json, write a frozen snapshot to forward/<date>.json.

    Args:
        target_date: 'YYYY-MM-DD' override; defaults to today (IST).
        dry_run: print what would be written without writing.

    Returns:
        The frozen row dict.
    """
    if not TODAY_REGIME_PATH.is_file():
        raise FileNotFoundError(f"source missing: {TODAY_REGIME_PATH}")

    src = json.loads(TODAY_REGIME_PATH.read_text(encoding="utf-8"))
    zone = src.get("zone") or src.get("regime")
    if zone not in ALLOWED_ZONES:
        raise ValueError(
            f"zone {zone!r} not in allowed vocabulary {ALLOWED_ZONES} — "
            "today_regime.json may be corrupt or stale"
        )

    if target_date is None:
        target_date = datetime.now(IST).strftime("%Y-%m-%d")

    captured_at = datetime.now(IST).isoformat()
    row = {
        "date": target_date,
        "zone": zone,
        "signal_score": src.get("msi_score") or src.get("signal_score"),
        "engine_version": src.get("regime_source", "unknown"),
        "feed": "forward",
        "feed_captured_at": captured_at,
        "source_timestamp": src.get("timestamp"),
        "source_path": TODAY_REGIME_PATH.relative_to(REPO_ROOT).as_posix(),
    }

    out_path = FORWARD_DIR / f"{target_date}.json"
    if out_path.is_file():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        existing_capture = existing.get("feed_captured_at", "")
        if existing_capture and existing_capture <= captured_at:
            # Earlier capture wins — preserve canonical first row.
            return existing

    if dry_run:
        print(f"[DRY RUN] would write {out_path}:")
        print(json.dumps(row, indent=2))
        return row

    FORWARD_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD; defaults to today IST")
    parser.add_argument("--dry-run", action="store_true",
                        help="print without writing")
    args = parser.parse_args(argv)

    try:
        row = capture(target_date=args.date, dry_run=args.dry_run)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not args.dry_run:
        print(f"captured {row['date']} zone={row['zone']} -> "
              f"pit_regime_tape/forward/{row['date']}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
