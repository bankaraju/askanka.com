"""MSI intraday refresh - runs every 15 min during market hours.

Reads cached FII flow from data/today_regime.json (persisted by the
09:25 morning scan), recomputes MSI with live VIX / USD-INR / Nifty /
crude, and atomically rewrites ONLY the MSI-related fields of
today_regime.json. On any failure, the file is left untouched -
morning MSI is held, the file's mtime does not advance, and the
watchdog's existing freshness check will flag it amber.

Exit codes:
    0 - success, file updated
    2 - soft failure (cache missing, compute raised, file absent);
        morning MSI held, scheduler should not treat this as fatal.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from macro_stress import compute_msi  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
REGIME_FILE = _HERE / "data" / "today_regime.json"

log = logging.getLogger("anka.msi_refresh")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON to a sibling .tmp file then os.replace - atomic on NTFS."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    if not REGIME_FILE.exists():
        log.warning("today_regime.json not found - nothing to refresh")
        return 2

    try:
        current = json.loads(REGIME_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to read today_regime.json: %s", exc)
        return 2

    cached = current.get("msi_cached_inputs")
    if not cached or cached.get("fii_net") is None:
        log.warning("no cached FII flow in today_regime.json - holding morning MSI")
        return 2

    try:
        msi = compute_msi(cached_fii=cached)
    except Exception as exc:
        log.warning("compute_msi failed: %s - holding morning MSI", exc)
        return 2

    # Mutate only the MSI fields. Everything else - regime, eligible_spreads,
    # hysteresis - is morning's snapshot and must be preserved byte-for-byte.
    current["msi_score"] = msi["msi_score"]
    current["msi_regime"] = msi["regime"]
    current["msi_updated_at"] = msi["timestamp"]

    try:
        _atomic_write(REGIME_FILE, current)
    except Exception as exc:
        log.error("atomic write failed: %s", exc)
        return 2

    log.info(
        "MSI refreshed: %.1f (%s) at %s",
        msi["msi_score"], msi["regime"], msi["timestamp"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
