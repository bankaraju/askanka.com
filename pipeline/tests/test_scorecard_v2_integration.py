"""Integration tests for pipeline/scorecard_v2 orchestrator — 2 tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.scorecard_v2 import run_scorecard_v2


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------

def _write_bank_screener(stock_dir: Path) -> None:
    """Write a minimal bank-format screener_financials.json."""
    data = {
        "about": {"ROE": "18.0", "ROCE": "15.0"},
        "profit_loss": [
            {"": "Revenue+",
             "Mar 2021": "50,000", "Mar 2022": "55,000", "Mar 2023": "62,000",
             "Mar 2024": "70,000", "Mar 2025": "80,000"},
            {"": "Interest",
             "Mar 2021": "20,000", "Mar 2022": "22,000", "Mar 2023": "24,000",
             "Mar 2024": "27,000", "Mar 2025": "30,000"},
            {"": "Expenses+",
             "Mar 2021": "15,000", "Mar 2022": "16,000", "Mar 2023": "18,000",
             "Mar 2024": "20,000", "Mar 2025": "22,000"},
            {"": "Financing Margin %",
             "Mar 2021": "30%", "Mar 2022": "31%", "Mar 2023": "32%",
             "Mar 2024": "33%", "Mar 2025": "35%"},
            {"": "Net Profit+",
             "Mar 2021": "10,000", "Mar 2022": "11,000", "Mar 2023": "13,000",
             "Mar 2024": "15,000", "Mar 2025": "18,000"},
        ],
        "balance_sheet": [
            {"": "Equity Capital", "Mar 2024": "500", "Mar 2025": "550"},
            {"": "Reserves", "Mar 2024": "9,500", "Mar 2025": "11,000"},
            {"": "Deposits", "Mar 2024": "1,50,000", "Mar 2025": "1,70,000"},
            {"": "Borrowing", "Mar 2024": "20,000", "Mar 2025": "25,000"},
            {"": "Total Assets", "Mar 2024": "2,00,000", "Mar 2025": "2,20,000"},
        ],
        "cash_flow": [
            {"": "Cash from Operating Activity+",
             "Mar 2021": "9,000", "Mar 2022": "10,000", "Mar 2023": "12,000",
             "Mar 2024": "14,000", "Mar 2025": "17,000"},
        ],
        "ratios": [
            {"": "ROE %",
             "Mar 2021": "14%", "Mar 2022": "15%", "Mar 2023": "16%",
             "Mar 2024": "17%", "Mar 2025": "18%"},
        ],
    }
    stock_dir.mkdir(parents=True, exist_ok=True)
    (stock_dir / "screener_financials.json").write_text(json.dumps(data), encoding="utf-8")


def _write_indianapi(stock_dir: Path, industry: str) -> None:
    data = {
        "companyName": stock_dir.name,
        "industry": industry,
        "keyMetrics": {
            "mgmtEffectiveness": [
                {"key": "returnOnAverageAssets", "value": "1.8"},
            ],
            "growth": [
                {"key": "revenueGrowthRate5Year", "value": "12.0"},
            ],
        },
    }
    (stock_dir / "indianapi_stock.json").write_text(json.dumps(data), encoding="utf-8")


def _write_nonbank_screener(stock_dir: Path) -> None:
    """Write a minimal non-bank screener_financials.json."""
    data = {
        "about": {"ROE": "22.0", "ROCE": "28.0"},
        "profit_loss": [
            {"": "Sales+",
             "Mar 2021": "1,000", "Mar 2022": "1,200", "Mar 2023": "1,400",
             "Mar 2024": "1,800", "Mar 2025": "2,000"},
            {"": "OPM %",
             "Mar 2021": "18%", "Mar 2022": "19%", "Mar 2023": "20%",
             "Mar 2024": "21%", "Mar 2025": "22%"},
            {"": "Net Profit+",
             "Mar 2021": "100", "Mar 2022": "130", "Mar 2023": "160",
             "Mar 2024": "220", "Mar 2025": "260"},
        ],
        "balance_sheet": [
            {"": "Equity Capital", "Mar 2024": "100", "Mar 2025": "100"},
            {"": "Reserves", "Mar 2024": "1,900", "Mar 2025": "2,200"},
            {"": "Borrowings+", "Mar 2024": "500", "Mar 2025": "600"},
        ],
        "cash_flow": [
            {"": "Cash from Operating Activity+",
             "Mar 2021": "90", "Mar 2022": "110", "Mar 2023": "140",
             "Mar 2024": "200", "Mar 2025": "240"},
        ],
        "ratios": [
            {"": "ROE %",
             "Mar 2021": "18%", "Mar 2022": "20%", "Mar 2023": "21%",
             "Mar 2024": "22%", "Mar 2025": "22%"},
        ],
    }
    stock_dir.mkdir(parents=True, exist_ok=True)
    (stock_dir / "screener_financials.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared taxonomy builders
# ---------------------------------------------------------------------------

def _write_bank_only_taxonomy(path: Path) -> None:
    taxonomy = {
        "version": "2.0",
        "sectors": {
            "Banks": {
                "display_name": "Banks (Private & PSU)",
                "industries": ["Regional Banks"],
                "composite_weights": {"financial": 0.70, "management": 0.30},
                "min_peer_count": 5,
                "kpis": [
                    {"name": "NIM_proxy", "direction": "higher", "weight": 0.20},
                    {"name": "ROE", "direction": "higher", "weight": 0.15},
                    {"name": "Revenue_Growth_3Y", "direction": "higher", "weight": 0.15},
                ],
            },
        },
        "overrides": {},
        "common_kpis": ["ROE", "ROCE"],
    }
    path.write_text(json.dumps(taxonomy), encoding="utf-8")


def _write_two_sector_taxonomy(path: Path) -> None:
    taxonomy = {
        "version": "2.0",
        "sectors": {
            "Banks": {
                "display_name": "Banks (Private & PSU)",
                "industries": ["Regional Banks"],
                "composite_weights": {"financial": 0.70, "management": 0.30},
                "min_peer_count": 3,
                "kpis": [
                    {"name": "NIM_proxy", "direction": "higher", "weight": 0.20},
                    {"name": "ROE", "direction": "higher", "weight": 0.20},
                ],
            },
            "IT_Services": {
                "display_name": "IT Services & Consulting",
                "industries": ["IT Services & Consulting"],
                "composite_weights": {"financial": 0.60, "management": 0.40},
                "min_peer_count": 3,
                "kpis": [
                    {"name": "ROE", "direction": "higher", "weight": 0.25},
                    {"name": "EBITDA_Margin", "direction": "higher", "weight": 0.25},
                    {"name": "Revenue_Growth_3Y", "direction": "higher", "weight": 0.25},
                ],
            },
        },
        "overrides": {},
        "common_kpis": ["ROE", "ROCE"],
    }
    path.write_text(json.dumps(taxonomy), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_pipeline_without_llm(tmp_path: Path) -> None:
    """5 bank stocks → full pipeline run → all required fields present, scores 0-100."""
    taxonomy_path = tmp_path / "sector_taxonomy.json"
    _write_bank_only_taxonomy(taxonomy_path)

    artifacts_dir = tmp_path / "artifacts"
    bank_symbols = ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "SBIBANK"]
    for sym in bank_symbols:
        stock_dir = artifacts_dir / sym
        _write_bank_screener(stock_dir)
        _write_indianapi(stock_dir, "Regional Banks")

    output_path = tmp_path / "out" / "trust_scores_v2.json"

    result = run_scorecard_v2(
        taxonomy_path=taxonomy_path,
        artifacts_dir=artifacts_dir,
        output_path=output_path,
        skip_llm=True,
    )

    # Basic structure
    assert result["version"] == "2.0"
    assert result["total_scored"] == 5
    stocks = result["stocks"]
    assert len(stocks) == 5

    # All required fields present on every stock
    required_fields = {
        "financial_score", "management_score", "composite_score",
        "sector_grade", "sector_rank", "grade_reason",
    }
    for entry in stocks:
        missing = required_fields - set(entry.keys())
        assert not missing, f"{entry['symbol']} missing fields: {missing}"

    # All scores are in [0, 100]
    for entry in stocks:
        assert 0 <= entry["financial_score"] <= 100, f"{entry['symbol']} financial_score out of range"
        assert 0 <= entry["management_score"] <= 100, f"{entry['symbol']} management_score out of range"
        assert 0 <= entry["composite_score"] <= 100, f"{entry['symbol']} composite_score out of range"

    # Grades are valid
    valid_grades = {"A", "B", "C", "D", "F"}
    for entry in stocks:
        assert entry["sector_grade"] in valid_grades, f"{entry['symbol']} invalid grade: {entry['sector_grade']}"

    # sector_rank values form a contiguous 1..5 sequence
    ranks = sorted(entry["sector_rank"] for entry in stocks)
    assert ranks == list(range(1, 6))

    # Output file exists and is valid JSON matching in-memory result
    assert output_path.exists()
    on_disk = json.loads(output_path.read_text(encoding="utf-8"))
    assert on_disk["total_scored"] == 5
    assert len(on_disk["stocks"]) == 5


def test_multiple_sectors(tmp_path: Path) -> None:
    """1 bank + 1 IT stock → each maps to its correct sector."""
    taxonomy_path = tmp_path / "sector_taxonomy.json"
    _write_two_sector_taxonomy(taxonomy_path)

    artifacts_dir = tmp_path / "artifacts"

    # Bank stock
    bank_dir = artifacts_dir / "HDFCBANK"
    _write_bank_screener(bank_dir)
    _write_indianapi(bank_dir, "Regional Banks")

    # IT stock
    it_dir = artifacts_dir / "TCS"
    _write_nonbank_screener(it_dir)
    _write_indianapi(it_dir, "IT Services & Consulting")

    output_path = tmp_path / "out" / "trust_scores_v2.json"

    result = run_scorecard_v2(
        taxonomy_path=taxonomy_path,
        artifacts_dir=artifacts_dir,
        output_path=output_path,
        skip_llm=True,
    )

    assert result["total_scored"] == 2

    by_symbol = {s["symbol"]: s for s in result["stocks"]}
    assert "HDFCBANK" in by_symbol
    assert "TCS" in by_symbol

    assert by_symbol["HDFCBANK"]["sector"] == "Banks"
    assert by_symbol["TCS"]["sector"] == "IT_Services"

    # Each single-stock sector gets rank 1 and grade A
    assert by_symbol["HDFCBANK"]["sector_rank"] == 1
    assert by_symbol["TCS"]["sector_rank"] == 1
    assert by_symbol["HDFCBANK"]["sector_grade"] == "A"
    assert by_symbol["TCS"]["sector_grade"] == "A"
