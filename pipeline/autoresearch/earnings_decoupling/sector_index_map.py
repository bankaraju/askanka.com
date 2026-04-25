"""Map peer-cohort sector → NSE sectoral-index ticker.

Source taxonomy: pipeline.scorecard_v2.sector_mapper.SectorMapper.
Hypothesis spec §3 lists 10 NSE sectoral indices. Symbols whose mapped sector
does not have a sectoral-index home are dropped at event_ledger time with
status=DROPPED_NO_SECTOR_MAP.
"""
from __future__ import annotations

# SectorMapper canonical sector keys (pipeline.scorecard_v2.sector_mapper.SectorMapper.map_all)
# → NSE sectoral index ticker (registered under nse_sectoral_indices_v1 dataset audit).
# Sectors with no clean sectoral-index home are intentionally omitted — those events
# drop with status=DROPPED_NO_SECTOR_MAP at event_ledger time.
SECTOR_TO_INDEX: dict[str, str] = {
    "Banks": "BANKNIFTY",
    "IT_Services": "NIFTYIT",
    "Pharma": "NIFTYPHARMA",
    "Hospitals_Diagnostics": "NIFTYPHARMA",
    "Autos": "NIFTYAUTO",
    "Auto_Ancillaries": "NIFTYAUTO",
    "FMCG": "NIFTYFMCG",
    "Metals_Mining": "NIFTYMETAL",
    "Oil_Gas": "NIFTYENERGY",
    "Power_Utilities": "NIFTYENERGY",
    "Real_Estate_Hotels": "NIFTYREALTY",
}


def build_sector_index_map(symbols: list[str], peer_meta: dict[str, str]) -> dict[str, str]:
    """peer_meta maps symbol → sector name (from SectorMapper).
    Returns symbol → NSE sectoral index ticker, omitting symbols without a mapping.
    """
    return {s: SECTOR_TO_INDEX[peer_meta[s]]
            for s in symbols
            if s in peer_meta and peer_meta[s] in SECTOR_TO_INDEX}
