"""§6.3 marker: restrict event basket to NEUTRAL-day winning sectors.

Empirical winners on v3-NEUTRAL days per Phase 0 catalog:
PSU BANK, BANK, PSE, ENERGY, INFRA, FIN SERVICE, REALTY, METAL, CONSR DURBL.
"""
from __future__ import annotations

import pandas as pd

NEUTRAL_DAY_WINNER_SECTORS: tuple[str, ...] = (
    "PSU BANK", "BANK", "PSE", "ENERGY", "INFRA",
    "FIN SERVICE", "REALTY", "METAL", "CONSR DURBL",
)


def apply_sector_overlay(events: pd.DataFrame, sectors: tuple[str, ...]) -> pd.DataFrame:
    """Return events whose ``sector`` is in ``sectors`` (winning-sector whitelist).

    Raises ValueError if the events frame lacks a ``sector`` column.

    Note: comparison is case-sensitive and whitespace-sensitive. Callers must
    normalise sector strings upstream if mixed-case inputs are expected.
    """
    if "sector" not in events.columns:
        raise ValueError("events frame must include 'sector' column")
    return events[events["sector"].isin(sectors)].reset_index(drop=True)
