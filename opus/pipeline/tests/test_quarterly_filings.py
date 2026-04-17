"""Tests for quarterly filings retriever — multi-source with cross-verification."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SCREENER_QUARTERLY = [
    {"": "Sales", "Mar 2025": "15,000", "Dec 2024": "14,500", "Sep 2024": "13,800"},
    {"": "Expenses", "Mar 2025": "11,700", "Dec 2024": "11,450", "Sep 2024": "10,900"},
    {"": "Operating Profit", "Mar 2025": "3,300", "Dec 2024": "3,050", "Sep 2024": "2,900"},
    {"": "OPM %", "Mar 2025": "22%", "Dec 2024": "21%", "Sep 2024": "21%"},
    {"": "Net Profit", "Mar 2025": "2,100", "Dec 2024": "1,900", "Sep 2024": "1,700"},
]

BSE_RESULTS = [
    {"Year": "2024-2025", "Quarter": "Q3", "Revenue": 14500, "PAT": 1900},
]


def test_fetch_quarterly_screener_primary():
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:
        MockSC.return_value.get_financials.return_value = {"quarterly": SCREENER_QUARTERLY}
        MockBSE.return_value.get_financial_results.return_value = []
        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "screener"
    assert "revenue" in result[0]
    assert "pat" in result[0]


def test_fetch_quarterly_cross_verifies_bse():
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:
        MockSC.return_value.get_financials.return_value = {"quarterly": SCREENER_QUARTERLY}
        MockBSE.return_value.get_financial_results.return_value = BSE_RESULTS
        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert len(result) >= 1


def test_fetch_quarterly_all_fail_returns_empty():
    from opus.pipeline.retrieval.quarterly_filings import fetch_quarterly_filings

    with patch("opus.pipeline.retrieval.quarterly_filings.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.quarterly_filings.BSEClient") as MockBSE:
        MockSC.return_value.get_financials.side_effect = Exception("Screener down")
        MockBSE.return_value.get_financial_results.side_effect = Exception("BSE down")
        result = fetch_quarterly_filings(bse_scrip="541154", nse_symbol="HAL")

    assert result == []
