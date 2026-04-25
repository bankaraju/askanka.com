"""ΔPCR amplifier — STUB. Disabled until per-ticker PCR history exists."""
from __future__ import annotations

import pandas as pd


def apply_pcr_filter(
    ledger: pd.DataFrame, *, enabled: bool = False,
) -> tuple[pd.DataFrame, dict]:
    if enabled:
        raise NotImplementedError(
            "pcr_amplifier requires per-ticker daily PCR history not yet stored "
            "(pipeline/data/oi_history.json is index-level only). Re-enable when "
            "the per-ticker PCR backfill ships."
        )
    return ledger.copy(), {
        "pcr_track": "deferred",
        "n_passed": int(len(ledger)),
        "n_failed": 0,
    }
