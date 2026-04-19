"""Map stocks to normalized sectors using taxonomy config + indianapi industry."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "config" / "sector_taxonomy.json"
_DEFAULT_ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "opus" / "artifacts"


class SectorMapper:
    def __init__(self, taxonomy_path: Path = _DEFAULT_TAXONOMY,
                 artifacts_dir: Path = _DEFAULT_ARTIFACTS):
        self._taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        self._artifacts = artifacts_dir
        self._industry_to_sector: dict[str, str] = {}
        self._sector_stocks: dict[str, list[str]] = {}
        self._stock_map: dict[str, dict[str, Any]] = {}

        for sector_key, sector_def in self._taxonomy.get("sectors", {}).items():
            for industry in sector_def.get("industries", []):
                self._industry_to_sector[industry] = sector_key

    def map_all(self) -> dict[str, dict[str, Any]]:
        overrides = self._taxonomy.get("overrides", {})
        self._stock_map = {}
        self._sector_stocks = {}

        for sym_dir in sorted(self._artifacts.iterdir()):
            if not sym_dir.is_dir() or sym_dir.name in ("transcripts",):
                continue
            symbol = sym_dir.name

            if symbol in overrides:
                sector = overrides[symbol]
            else:
                ia_path = sym_dir / "indianapi_stock.json"
                if ia_path.exists():
                    try:
                        ia = json.loads(ia_path.read_text(encoding="utf-8"))
                        raw_industry = ia.get("industry", "Unknown")
                        sector = self._industry_to_sector.get(raw_industry, "Unmapped")
                    except Exception:
                        sector = "Unmapped"
                else:
                    sector = "Unmapped"

            sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
            self._stock_map[symbol] = {
                "sector": sector,
                "display_name": sector_def.get("display_name", sector),
                "subsector": "",
            }
            self._sector_stocks.setdefault(sector, []).append(symbol)

        return self._stock_map

    def get_sector_peers(self, sector: str) -> list[str]:
        return self._sector_stocks.get(sector, [])

    def is_low_peer_count(self, sector: str) -> bool:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        min_peers = sector_def.get("min_peer_count", 5)
        return len(self._sector_stocks.get(sector, [])) < min_peers

    def get_sector_kpis(self, sector: str) -> list[dict]:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        return sector_def.get("kpis", [])

    def get_composite_weights(self, sector: str) -> dict[str, float]:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        return sector_def.get("composite_weights", {"financial": 0.60, "management": 0.40})

    def get_all_sectors(self) -> list[str]:
        return list(self._taxonomy.get("sectors", {}).keys())
