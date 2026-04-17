"""Tests for sector peer trust score imputation."""
from __future__ import annotations

import json
import pytest
from pathlib import Path


SAMPLE_SCORES = {
    "HAL": {"trust_score": 80, "grade": "A", "source": "DIRECT"},
    "BEL": {"trust_score": 75, "grade": "A", "source": "DIRECT"},
    "BDL": {"trust_score": 60, "grade": "B+", "source": "DIRECT"},
}

SAMPLE_UNIVERSE = {
    "version": "2.0",
    "sectors": {
        "defence": {
            "stocks": ["HAL", "BEL", "BDL", "BHARATFORGE", "DATAPATTNS"],
        },
        "it": {
            "stocks": ["TCS", "INFY"],
        },
    },
}


@pytest.fixture
def universe_path(tmp_path: Path) -> Path:
    p = tmp_path / "universe.json"
    p.write_text(json.dumps(SAMPLE_UNIVERSE))
    return p


def test_impute_uses_sector_peer_average(universe_path: Path):
    from opus.pipeline.analysis.peer_imputer import impute_trust_score
    result = impute_trust_score("BHARATFORGE", SAMPLE_SCORES, universe_path=universe_path)
    assert result is not None
    assert result["trust_source"] == "PEER_IMPUTED"
    expected_avg = (80 + 75 + 60) / 3
    assert abs(result["trust_score"] - expected_avg) < 1.0
    assert result["grade"] <= "B+"
    assert "HAL" in result["peer_symbols"]


def test_impute_caps_at_b_plus(universe_path: Path):
    from opus.pipeline.analysis.peer_imputer import impute_trust_score
    high_scores = {
        "HAL": {"trust_score": 90, "grade": "A+", "source": "DIRECT"},
        "BEL": {"trust_score": 85, "grade": "A", "source": "DIRECT"},
    }
    result = impute_trust_score("BHARATFORGE", high_scores, universe_path=universe_path)
    assert result is not None
    assert result["grade"] == "B+"


def test_impute_no_peers_returns_none(universe_path: Path):
    from opus.pipeline.analysis.peer_imputer import impute_trust_score
    result = impute_trust_score("RANDOMSTOCK", SAMPLE_SCORES, universe_path=universe_path)
    assert result is None


def test_impute_no_scored_peers_returns_none(universe_path: Path):
    from opus.pipeline.analysis.peer_imputer import impute_trust_score
    result = impute_trust_score("TCS", {}, universe_path=universe_path)
    assert result is None
