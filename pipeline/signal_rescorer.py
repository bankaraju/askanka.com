"""Live rescore — runs every 15 min during market hours.

Recomputes the conviction score for every open signal using today's fresh
trust/breaks/profile/OI enrichment inputs, and stores the result on the
signal dict as `rescore = {current_score, score_delta, gate_reason_current,
rescored_at}`.

The signal tracker's check_signal_status() consumes this field to trigger
the CONVICTION_DECAY exit (score < 45 AND score_delta > 20) and, for
CORRELATION_BREAK signals, the Z_CROSS exit.

Exit codes:
    0 — success (even if some signals failed to rescore)
    2 — soft failure: open_signals.json missing / unreadable
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

from signal_enrichment import (  # noqa: E402
    load_trust_scores, load_correlation_breaks, load_regime_profile,
    load_oi_anomalies, rescore_signal,
)

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_SIGNALS_FILE = _HERE / "data" / "signals" / "open_signals.json"

log = logging.getLogger("anka.signal_rescorer")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _load_enrichment_inputs():
    return (load_trust_scores(), load_correlation_breaks(),
            load_regime_profile(), load_oi_anomalies())


def _atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    if not OPEN_SIGNALS_FILE.exists():
        log.warning("open_signals.json not found — nothing to rescore")
        return 2

    try:
        signals = json.loads(OPEN_SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to read open_signals.json: %s", exc)
        return 2

    if not signals:
        log.info("no open signals — nothing to rescore")
        return 0

    trust, breaks, profile, oi = _load_enrichment_inputs()

    rescored_count = 0
    failed_count = 0
    for sig in signals:
        try:
            sig["rescore"] = rescore_signal(sig, trust, breaks, profile, oi)
            rescored_count += 1
        except Exception as exc:
            log.warning("rescore failed for signal %s: %s — keeping prior rescore",
                        sig.get("signal_id"), exc)
            failed_count += 1

    try:
        _atomic_write(OPEN_SIGNALS_FILE, signals)
    except Exception as exc:
        log.error("atomic write failed: %s", exc)
        return 2

    log.info("rescore complete: %d ok, %d failed", rescored_count, failed_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
