"""Sector-mapping integration tests for the H-2026-05-04 runner.

Catches the defect class that produced "0 cells fit" on the first VPS deploy:
  - wrong import path for sector_mapper
  - sector_keys with no published Nifty index silently dropping every ticker
  - lowercase column names in sectoral_indices CSVs

These tests touch real on-disk data when present; they skip when the data is
not in the checkout (e.g., CI without sectoral_indices/).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.sector_mapping import (
    SECTOR_TO_INDEX_FILE,
    index_csv_for_sector,
    load_sectoral_index_close,
)

REPO = Path(__file__).resolve().parents[4]
SECTORAL_DIR = REPO / "pipeline" / "data" / "sectoral_indices"
UNIVERSE_PATH = (
    REPO
    / "pipeline"
    / "research"
    / "h_2026_05_04_cross_asset_perstock_lasso"
    / "universe_frozen.json"
)


def test_index_csv_for_sector_returns_none_for_unmapped_sectors():
    assert index_csv_for_sector(None, SECTORAL_DIR) is None
    assert index_csv_for_sector("Unmapped", SECTORAL_DIR) is None
    assert index_csv_for_sector("Defence", SECTORAL_DIR) is None
    assert index_csv_for_sector("NBFC_HFC", SECTORAL_DIR) is None


def test_index_csv_for_sector_returns_path_for_mapped_sectors():
    assert index_csv_for_sector("Banks", SECTORAL_DIR) == SECTORAL_DIR / "BANKNIFTY_daily.csv"
    assert index_csv_for_sector("IT_Services", SECTORAL_DIR) == SECTORAL_DIR / "NIFTYIT_daily.csv"
    assert index_csv_for_sector("Pharma", SECTORAL_DIR) == SECTORAL_DIR / "NIFTYPHARMA_daily.csv"


def test_every_mapped_sector_has_a_real_csv_on_disk():
    if not SECTORAL_DIR.exists():
        pytest.skip("sectoral_indices/ not present")
    for sector_key, fname in SECTOR_TO_INDEX_FILE.items():
        path = SECTORAL_DIR / fname
        assert path.exists(), f"{sector_key} -> {fname} missing on disk"


def test_load_sectoral_index_close_handles_lowercase_columns():
    if not SECTORAL_DIR.exists():
        pytest.skip("sectoral_indices/ not present")
    path = SECTORAL_DIR / "BANKNIFTY_daily.csv"
    if not path.exists():
        pytest.skip("BANKNIFTY_daily.csv not present")
    s = load_sectoral_index_close(path)
    assert len(s) > 100
    assert s.index.is_monotonic_increasing
    assert s.dtype.kind in ("f", "i")
    assert s.notna().sum() > 0


def test_frozen_universe_has_at_least_30_sector_resolvable_tickers():
    """Catches the bug we just fixed: if every ticker drops out of the
    sector lookup, the runner produces 0 cells. Require >= 30 to confirm
    SectorMapper.map_all() + index_csv_for_sector are wired correctly."""
    if not UNIVERSE_PATH.exists() or not SECTORAL_DIR.exists():
        pytest.skip("universe_frozen.json or sectoral_indices/ not present")
    if not (REPO / "opus" / "artifacts").exists():
        pytest.skip("opus/artifacts/ not present (SectorMapper depends on it)")

    from pipeline.scorecard_v2.sector_mapper import SectorMapper

    universe = json.loads(UNIVERSE_PATH.read_text())["tickers"]
    sector_map = SectorMapper().map_all()

    n_resolvable = 0
    for ticker in universe:
        info = sector_map.get(ticker)
        sector_key = info.get("sector") if info else None
        path = index_csv_for_sector(sector_key, SECTORAL_DIR)
        if path is not None and path.exists():
            n_resolvable += 1

    assert n_resolvable >= 30, (
        f"Only {n_resolvable}/{len(universe)} tickers resolve to a sectoral "
        f"index CSV — runner will fit 0 cells. Check SECTOR_TO_INDEX_FILE."
    )
