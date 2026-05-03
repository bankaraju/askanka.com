"""Sector key -> sectoral index CSV mapping for H-2026-05-04.

Maps each sector_key produced by SectorMapper.map_all() to a published NSE
sectoral index CSV under pipeline/data/sectoral_indices/. Sectors with no
published Nifty index return None — tickers in those sectors are excluded
from the universe (per spec §5.3 own_sector_ret_5d requirement).

The taxonomy has 24 sector_keys; only 11 have a published index. Stocks in
sectors without an index (NBFC_HFC, Capital_Goods, Capital_Markets,
Chemicals, Insurance, Infra_EPC, Consumer_Discretionary, Cement_Building,
Logistics_Transport, Defence, Telecom, Business_Services, Unmapped) are
dropped from the §3 universe at preflight time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

SECTOR_TO_INDEX_FILE: dict[str, str] = {
    "Banks": "BANKNIFTY_daily.csv",
    "IT_Services": "NIFTYIT_daily.csv",
    "Pharma": "NIFTYPHARMA_daily.csv",
    "Hospitals_Diagnostics": "NIFTYPHARMA_daily.csv",
    "FMCG": "NIFTYFMCG_daily.csv",
    "Metals_Mining": "NIFTYMETAL_daily.csv",
    "Power_Utilities": "NIFTYENERGY_daily.csv",
    "Oil_Gas": "NIFTYENERGY_daily.csv",
    "Autos": "NIFTYAUTO_daily.csv",
    "Auto_Ancillaries": "NIFTYAUTO_daily.csv",
    "Real_Estate_Hotels": "NIFTYREALTY_daily.csv",
}


def index_csv_for_sector(sector_key: Optional[str], sectoral_dir: Path) -> Optional[Path]:
    """Resolve sector_key to a sectoral index CSV path. Returns None if the
    sector has no published Nifty index — caller must skip such tickers.
    Path existence is NOT checked here; caller must verify Path.exists().
    """
    if not sector_key:
        return None
    fname = SECTOR_TO_INDEX_FILE.get(sector_key)
    if fname is None:
        return None
    return sectoral_dir / fname


def load_sectoral_index_close(csv_path: Path) -> pd.Series:
    """Read a sectoral index CSV (lowercase date/close columns) into a
    DatetimeIndex'd Close series."""
    df = pd.read_csv(csv_path)
    rename = {c: c.capitalize() for c in df.columns if c.lower() in {"date", "close"}}
    df = df.rename(columns=rename)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").sort_index()["Close"]
