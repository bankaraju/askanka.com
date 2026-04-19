"""Tests for pipeline/scorecard_v2/metric_extractor.py"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pipeline.scorecard_v2.metric_extractor import MetricExtractor, _parse_screener_num


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _write_screener(stock_dir: Path, *, bank: bool = False, **overrides) -> None:
    """Write a minimal screener_financials.json for a stock."""
    if bank:
        profit_loss = [
            {"": "Revenue+",
             "Mar 2021": "50,000", "Mar 2022": "55,000", "Mar 2023": "62,000",
             "Mar 2024": "70,000", "Mar 2025": "80,000", "TTM": "85,000"},
            {"": "Interest",
             "Mar 2021": "20,000", "Mar 2022": "22,000", "Mar 2023": "24,000",
             "Mar 2024": "27,000", "Mar 2025": "30,000", "TTM": "32,000"},
            {"": "Expenses+",
             "Mar 2021": "15,000", "Mar 2022": "16,000", "Mar 2023": "18,000",
             "Mar 2024": "20,000", "Mar 2025": "22,000", "TTM": "24,000"},
            {"": "Financing Profit",
             "Mar 2021": "15,000", "Mar 2022": "17,000", "Mar 2023": "20,000",
             "Mar 2024": "23,000", "Mar 2025": "28,000", "TTM": "29,000"},
            {"": "Financing Margin %",
             "Mar 2021": "30%", "Mar 2022": "31%", "Mar 2023": "32%",
             "Mar 2024": "33%", "Mar 2025": "35%", "TTM": "34%"},
            {"": "Net Profit+",
             "Mar 2021": "10,000", "Mar 2022": "11,000", "Mar 2023": "13,000",
             "Mar 2024": "15,000", "Mar 2025": "18,000", "TTM": "19,000"},
        ]
        balance_sheet = [
            {"": "Equity Capital",
             "Mar 2024": "500", "Mar 2025": "550"},
            {"": "Reserves",
             "Mar 2024": "9,500", "Mar 2025": "11,000"},
            {"": "Deposits",
             "Mar 2024": "1,50,000", "Mar 2025": "1,70,000"},
            {"": "Borrowing",
             "Mar 2024": "20,000", "Mar 2025": "25,000"},
            {"": "Total Assets",
             "Mar 2024": "2,00,000", "Mar 2025": "2,20,000"},
        ]
    else:
        profit_loss = [
            {"": "Sales+",
             "Mar 2021": "1,000", "Mar 2022": "1,200", "Mar 2023": "1,400",
             "Mar 2024": "1,800", "Mar 2025": "2,000", "TTM": "2,100"},
            {"": "Expenses+",
             "Mar 2021": "700", "Mar 2022": "800", "Mar 2023": "900",
             "Mar 2024": "1,100", "Mar 2025": "1,200", "TTM": "1,300"},
            {"": "Operating Profit",
             "Mar 2021": "300", "Mar 2022": "400", "Mar 2023": "500",
             "Mar 2024": "700", "Mar 2025": "800", "TTM": "800"},
            {"": "OPM %",
             "Mar 2021": "30%", "Mar 2022": "33%", "Mar 2023": "36%",
             "Mar 2024": "39%", "Mar 2025": "40%", "TTM": "38%"},
            {"": "Interest",
             "Mar 2021": "50", "Mar 2022": "55", "Mar 2023": "60",
             "Mar 2024": "70", "Mar 2025": "80", "TTM": "80"},
            {"": "Net Profit+",
             "Mar 2021": "200", "Mar 2022": "280", "Mar 2023": "350",
             "Mar 2024": "480", "Mar 2025": "550", "TTM": "570"},
        ]
        balance_sheet = [
            {"": "Equity Capital",
             "Mar 2024": "100", "Mar 2025": "100"},
            {"": "Reserves",
             "Mar 2024": "1,900", "Mar 2025": "2,200"},
            {"": "Borrowings+",
             "Mar 2024": "500", "Mar 2025": "600"},
        ]

    cash_flow = [
        {"": "Cash from Operating Activity+",
         "Mar 2021": "180", "Mar 2022": "250", "Mar 2023": "320",
         "Mar 2024": "450", "Mar 2025": "500"},
        {"": "Cash from Investing Activity+",
         "Mar 2021": "-100", "Mar 2022": "-120", "Mar 2023": "-150",
         "Mar 2024": "-200", "Mar 2025": "-220"},
    ]
    ratios = [
        {"": "ROE %",
         "Mar 2021": "12%", "Mar 2022": "14%", "Mar 2023": "16%",
         "Mar 2024": "18%", "Mar 2025": "20%"},
        {"": "Debtor Days",
         "Mar 2021": "40", "Mar 2022": "42", "Mar 2023": "38",
         "Mar 2024": "35", "Mar 2025": "33"},
    ]
    about = {
        "description": "Test company",
        "ROE": overrides.pop("about_ROE", "20.5"),
        "ROCE": overrides.pop("about_ROCE", "24.0"),
        "Stock P/E": "25",
        "Book Value": "150",
    }

    data = {
        "about": about,
        "profit_loss": profit_loss,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "ratios": ratios,
    }
    stock_dir.mkdir(parents=True, exist_ok=True)
    (stock_dir / "screener_financials.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


def _write_indianapi(stock_dir: Path, roa: str = "2.17", rev_growth_5y: str = "17.04") -> None:
    data = {
        "companyName": "Test",
        "keyMetrics": {
            "mgmtEffectiveness": [
                {"key": "returnOnAverageAssets", "value": roa},
            ],
            "growth": [
                {"key": "revenueGrowthRate5Year", "value": rev_growth_5y},
            ],
        },
    }
    (stock_dir / "indianapi_stock.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseScreenerNum:
    def test_comma_separated_indian_number(self):
        assert _parse_screener_num("1,07,476") == 107476.0

    def test_percentage_string(self):
        assert _parse_screener_num("18%") == 18.0

    def test_plain_float(self):
        assert _parse_screener_num("16.6") == 16.6

    def test_empty_string(self):
        assert _parse_screener_num("") is None

    def test_none(self):
        assert _parse_screener_num(None) is None

    def test_negative_with_commas(self):
        assert _parse_screener_num("-2,411") == -2411.0


class TestMetricExtractor:

    # Test 1 — Common metrics from non-bank screener
    def test_nonbank_common_metrics(self, tmp_path):
        stock_dir = tmp_path / "TESTCO"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("TESTCO")

        assert result["has_screener"] is True
        assert result["is_bank"] is False
        assert result["ROE"] == pytest.approx(20.5)
        assert result["ROCE"] == pytest.approx(24.0)
        assert result["EBITDA_Margin"] == pytest.approx(40.0)  # Mar 2025 OPM%
        assert result["coverage_pct"] > 0

    # Test 2 — Bank NIM proxy
    def test_bank_nim_proxy(self, tmp_path):
        stock_dir = tmp_path / "BANKCO"
        _write_screener(stock_dir, bank=True)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("BANKCO")

        assert result["is_bank"] is True
        assert result["NIM_proxy"] is not None
        # NIM proxy = (Revenue - Interest) / TotalAssets = (80000 - 30000) / 220000
        expected = (80_000 - 30_000) / 220_000
        assert result["NIM_proxy"] == pytest.approx(expected, rel=1e-4)

    # Test 3 — Revenue growth CAGR from 3 years of sales data
    def test_revenue_growth_3y_cagr(self, tmp_path):
        stock_dir = tmp_path / "GROWCO"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("GROWCO")

        # Sales: Mar2022=1200, Mar2025=2000 → 3Y CAGR = (2000/1200)^(1/3) - 1
        expected = ((2000 / 1200) ** (1 / 3) - 1) * 100
        assert result["Revenue_Growth_3Y"] == pytest.approx(expected, rel=1e-3)

    # Test 4 — CFO/PAT ratio
    def test_cfo_pat_ratio(self, tmp_path):
        stock_dir = tmp_path / "CFOCO"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("CFOCO")

        # CFO Mar2025=500, Net Profit Mar2025=550 → 500/550
        assert result["CFO_PAT"] == pytest.approx(500 / 550, rel=1e-3)

    # Test 5 — Debt-to-equity ratio (non-bank)
    def test_debt_to_equity_nonbank(self, tmp_path):
        stock_dir = tmp_path / "DEBTCO"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("DEBTCO")

        # Borrowings+=600, Equity=100, Reserves=2200 → 600/2300
        assert result["Debt_to_Equity"] == pytest.approx(600 / 2300, rel=1e-3)

    # Test 6 — IndianAPI supplements screener
    def test_indianapi_supplement(self, tmp_path):
        stock_dir = tmp_path / "APISTOCK"
        _write_screener(stock_dir, bank=False)
        _write_indianapi(stock_dir, roa="3.50", rev_growth_5y="22.0")
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("APISTOCK")

        assert result["has_indianapi"] is True
        assert result["ROA_indianapi"] == pytest.approx(3.50)
        assert result["Revenue_Growth_5Y_indianapi"] == pytest.approx(22.0)

    # Test 7 — Missing screener returns coverage_pct = 0
    def test_missing_screener_zero_coverage(self, tmp_path):
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("NONEXISTENT")

        assert result["has_screener"] is False
        assert result["coverage_pct"] == 0.0
        assert result["ROE"] is None
        assert result["ROCE"] is None

    # Test 8 — ROE history extracted as list of floats from ratios section
    def test_roe_history_from_ratios(self, tmp_path):
        stock_dir = tmp_path / "ROEHIST"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("ROEHIST")

        # ratios has ROE % for Mar2021-2025 = 12,14,16,18,20
        assert result["ROE_history"] == pytest.approx([12.0, 14.0, 16.0, 18.0, 20.0])

    # Test 9 — Margin history extracted from P&L across years
    def test_margin_history_from_pl(self, tmp_path):
        stock_dir = tmp_path / "MARGCO"
        _write_screener(stock_dir, bank=False)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("MARGCO")

        # OPM% Mar2021-2025 = 30,33,36,39,40
        assert result["Margin_history"] == pytest.approx([30.0, 33.0, 36.0, 39.0, 40.0])

    # Test 10 — Bank cost-to-income
    def test_bank_cost_to_income(self, tmp_path):
        stock_dir = tmp_path / "BANKC2I"
        _write_screener(stock_dir, bank=True)
        extractor = MetricExtractor(tmp_path)
        result = extractor.extract("BANKC2I")

        # Expenses=22000, Revenue=80000 → 22000/80000
        assert result["Cost_to_Income"] == pytest.approx(22_000 / 80_000, rel=1e-3)
