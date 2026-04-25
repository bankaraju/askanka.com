"""Map peer-cohort sector → NSE sectoral-index ticker.

Source taxonomy: pipeline.scorecard_v2.sector_mapper.SectorMapper.
Hypothesis spec §3 lists 10 NSE sectoral indices. Symbols whose mapped sector
does not have a sectoral-index home are dropped at event_ledger time with
status=DROPPED_NO_SECTOR_MAP.
"""
from __future__ import annotations

# canonical sector names (the SectorMapper output) → backfill_indices.py symbol
SECTOR_TO_INDEX: dict[str, str] = {
    "Banks": "BANKNIFTY",
    "Information Technology": "NIFTYIT",
    "Pharma": "NIFTYPHARMA",
    "Pharmaceuticals": "NIFTYPHARMA",
    "Healthcare": "NIFTYPHARMA",
    "Auto": "NIFTYAUTO",
    "Automobile": "NIFTYAUTO",
    "Consumer Goods": "NIFTYFMCG",
    "FMCG": "NIFTYFMCG",
    "Metal": "NIFTYMETAL",
    "Metals": "NIFTYMETAL",
    "Energy": "NIFTYENERGY",
    "Oil & Gas": "NIFTYENERGY",
    "PSU Bank": "NIFTYPSUBANK",
    "Realty": "NIFTYREALTY",
    "Real Estate": "NIFTYREALTY",
    "Media": "NIFTYMEDIA",
    "Entertainment": "NIFTYMEDIA",
}


def build_sector_index_map(symbols: list[str], peer_meta: dict[str, str]) -> dict[str, str]:
    """peer_meta maps symbol → sector name (from SectorMapper).
    Returns symbol → NSE sectoral index ticker, omitting symbols without a mapping.
    """
    return {s: SECTOR_TO_INDEX[peer_meta[s]]
            for s in symbols
            if s in peer_meta and peer_meta[s] in SECTOR_TO_INDEX}
