import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.survivorship import (
    eligible_universe_at,
    coverage_summary,
)


def test_eligible_universe_pulls_pit_membership(tmp_path):
    src = tmp_path / "fno_universe_history.json"
    src.write_text(json.dumps({
        "snapshots": {
            "2025-12-01": ["RELIANCE","TCS","INFY"],
            "2026-03-01": ["RELIANCE","TCS","HDFCBANK"],
        }
    }), encoding="utf-8")
    elig = eligible_universe_at(src, date(2026, 2, 28))
    assert set(elig) == {"RELIANCE","TCS","INFY"}


def test_eligible_universe_uses_exact_boundary(tmp_path):
    """asof exactly equal to a snapshot date selects that snapshot (<= boundary)."""
    src = tmp_path / "u.json"
    src.write_text(json.dumps({
        "snapshots": {
            "2025-12-01": ["A", "B"],
            "2026-03-01": ["A", "C"],
        }
    }), encoding="utf-8")
    elig = eligible_universe_at(src, date(2026, 3, 1))
    assert set(elig) == {"A", "C"}


def test_eligible_universe_raises_when_asof_predates_history(tmp_path):
    """No silent empty-list fallback when asof is before any snapshot."""
    src = tmp_path / "u.json"
    src.write_text(json.dumps({
        "snapshots": {"2025-12-01": ["A", "B"]}
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="No snapshot on or before"):
        eligible_universe_at(src, date(2025, 1, 1))


def test_coverage_summary_reports_ratios(tmp_path):
    src = tmp_path / "u.json"
    src.write_text(json.dumps({
        "snapshots": {
            "2024-01-01": ["A","B","C"],
            "2025-01-01": ["A","C","D"],
        }
    }), encoding="utf-8")
    summ = coverage_summary(src)
    assert summ["n_tickers_ever"] == 4
    assert summ["n_tickers_current"] == 3
    assert summ["n_tickers_delisted"] == 1
    assert 0 < summ["coverage_ratio"] <= 1
