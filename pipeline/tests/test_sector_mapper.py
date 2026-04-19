"""Tests for pipeline/scorecard_v2/sector_mapper.py — 8 tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.scorecard_v2.sector_mapper import SectorMapper

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINI_TAXONOMY = {
    "version": "2.0",
    "sectors": {
        "Banks": {
            "display_name": "Banks (Private & PSU)",
            "industries": ["Regional Banks"],
            "composite_weights": {"financial": 0.70, "management": 0.30},
            "min_peer_count": 3,
            "kpis": [
                {"name": "NIM_proxy", "direction": "higher", "weight": 0.20, "source": "derived"},
                {"name": "ROA", "direction": "higher", "weight": 0.15, "source": "indianapi"},
                {"name": "ROE", "direction": "higher", "weight": 0.15, "source": "screener"},
            ],
        },
        "Oil_Gas": {
            "display_name": "Oil & Gas",
            "industries": ["Oil & Gas Operations"],
            "composite_weights": {"financial": 0.65, "management": 0.35},
            "min_peer_count": 3,
            "kpis": [
                {"name": "ROE", "direction": "higher", "weight": 0.20, "source": "screener"},
                {"name": "ROCE", "direction": "higher", "weight": 0.20, "source": "screener"},
            ],
        },
        "Capital_Goods": {
            "display_name": "Capital Goods & Engineering",
            "industries": ["Misc. Capital Goods"],
            "composite_weights": {"financial": 0.55, "management": 0.45},
            "min_peer_count": 5,
            "kpis": [
                {"name": "ROE", "direction": "higher", "weight": 0.20, "source": "screener"},
            ],
        },
        "Unmapped": {
            "display_name": "Unmapped / Unknown",
            "industries": [],
            "composite_weights": {"financial": 0.60, "management": 0.40},
            "min_peer_count": 3,
            "kpis": [],
        },
    },
    "overrides": {
        "RELIANCE": "Oil_Gas",
        "ADANIENT": "Capital_Goods",
    },
    "common_kpis": ["ROE", "ROCE", "Revenue_Growth_3Y"],
}


@pytest.fixture
def taxonomy_file(tmp_path: Path) -> Path:
    p = tmp_path / "sector_taxonomy.json"
    p.write_text(json.dumps(MINI_TAXONOMY), encoding="utf-8")
    return p


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    art = tmp_path / "artifacts"
    art.mkdir()
    return art


def _make_stock(artifacts_dir: Path, symbol: str, industry: str | None) -> None:
    """Create a minimal artifact directory for a stock."""
    d = artifacts_dir / symbol
    d.mkdir()
    if industry is not None:
        (d / "indianapi_stock.json").write_text(
            json.dumps({"industry": industry, "companyName": symbol}),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_maps_bank_by_industry(taxonomy_file, artifacts_dir):
    """Regional Banks industry → Banks sector."""
    _make_stock(artifacts_dir, "HDFCBANK", "Regional Banks")
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    result = mapper.map_all()
    assert result["HDFCBANK"]["sector"] == "Banks"
    assert result["HDFCBANK"]["display_name"] == "Banks (Private & PSU)"


def test_override_takes_precedence(taxonomy_file, artifacts_dir):
    """RELIANCE override → Oil_Gas regardless of industry field."""
    # Give RELIANCE an industry that would normally map to Banks — override must win
    _make_stock(artifacts_dir, "RELIANCE", "Regional Banks")
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    result = mapper.map_all()
    assert result["RELIANCE"]["sector"] == "Oil_Gas"


def test_unmapped_industry_gets_unmapped_sector(taxonomy_file, artifacts_dir):
    """Industry string not in taxonomy → Unmapped sector."""
    _make_stock(artifacts_dir, "WEIRDCO", "Intergalactic Widget Making")
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    result = mapper.map_all()
    assert result["WEIRDCO"]["sector"] == "Unmapped"


def test_missing_indianapi_file_maps_via_override(taxonomy_file, artifacts_dir):
    """Stock without indianapi file but in overrides still maps correctly."""
    # Create dir but no indianapi_stock.json
    (artifacts_dir / "ADANIENT").mkdir()
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    result = mapper.map_all()
    assert result["ADANIENT"]["sector"] == "Capital_Goods"


def test_missing_indianapi_file_no_override_gets_unmapped(taxonomy_file, artifacts_dir):
    """Stock without indianapi file and no override → Unmapped."""
    (artifacts_dir / "MYSTERYSTOCK").mkdir()
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    result = mapper.map_all()
    assert result["MYSTERYSTOCK"]["sector"] == "Unmapped"


def test_get_sector_peers(taxonomy_file, artifacts_dir):
    """get_sector_peers returns all stocks mapped to that sector."""
    for sym in ("HDFCBANK", "ICICIBANK", "AXISBANK"):
        _make_stock(artifacts_dir, sym, "Regional Banks")
    _make_stock(artifacts_dir, "RELIANCE", "Regional Banks")  # overridden to Oil_Gas
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    mapper.map_all()
    peers = mapper.get_sector_peers("Banks")
    assert set(peers) == {"HDFCBANK", "ICICIBANK", "AXISBANK"}
    assert "RELIANCE" not in peers


def test_low_peer_count_flag(taxonomy_file, artifacts_dir):
    """is_low_peer_count returns True when sector has fewer than min_peer_count stocks."""
    # Capital_Goods has min_peer_count=5; put only 2 stocks there
    _make_stock(artifacts_dir, "ABB", "Misc. Capital Goods")
    _make_stock(artifacts_dir, "SIEMENS", "Misc. Capital Goods")
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    mapper.map_all()
    assert mapper.is_low_peer_count("Capital_Goods") is True
    # Banks has min_peer_count=3; put 3 stocks → should NOT be low
    for sym in ("HDFCBANK", "ICICIBANK", "AXISBANK"):
        _make_stock(artifacts_dir, sym, "Regional Banks")
    mapper2 = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    mapper2.map_all()
    assert mapper2.is_low_peer_count("Banks") is False


def test_get_sector_kpis(taxonomy_file, artifacts_dir):
    """get_sector_kpis returns the KPI list for the sector."""
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    kpis = mapper.get_sector_kpis("Banks")
    assert len(kpis) == 3
    names = [k["name"] for k in kpis]
    assert "NIM_proxy" in names
    assert "ROA" in names


def test_get_composite_weights(taxonomy_file, artifacts_dir):
    """get_composite_weights returns correct financial/management split."""
    mapper = SectorMapper(taxonomy_path=taxonomy_file, artifacts_dir=artifacts_dir)
    weights = mapper.get_composite_weights("Banks")
    assert weights == {"financial": 0.70, "management": 0.30}

    weights_cg = mapper.get_composite_weights("Capital_Goods")
    assert weights_cg == {"financial": 0.55, "management": 0.45}

    # Unknown sector → defaults
    weights_unk = mapper.get_composite_weights("NonExistentSector")
    assert weights_unk == {"financial": 0.60, "management": 0.40}
