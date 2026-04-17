# opus/pipeline/tests/test_annual_reports.py
"""Tests for annual report retriever — BSE primary, Screener + NSE fallback."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_BSE_REPORTS = [
    {"year": "2024", "url": "https://bse.example.com/ar2024.pdf", "source": "BSE", "format": "PDF"},
    {"year": "2023", "url": "https://bse.example.com/ar2023.pdf", "source": "BSE", "format": "PDF"},
    {"year": "2022", "url": "https://bse.example.com/ar2022.pdf", "source": "BSE", "format": "PDF"},
]

SAMPLE_SCREENER_DOCS = [
    {"title": "Annual Report 2024", "url": "https://screener.example.com/ar2024.pdf", "type": "annual_report"},
    {"title": "Annual Report 2021", "url": "https://screener.example.com/ar2021.pdf", "type": "annual_report"},
    {"title": "Annual Report 2020", "url": "https://screener.example.com/ar2020.pdf", "type": "annual_report"},
]


def test_fetch_annual_reports_bse_primary():
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:
        MockBSE.return_value.get_annual_reports.return_value = SAMPLE_BSE_REPORTS
        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []
        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    assert len(result) >= 3
    bse_years = {r["year"] for r in result if r["source"] == "BSE"}
    assert "2024" in bse_years


def test_fetch_annual_reports_screener_fills_gaps():
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:
        MockBSE.return_value.get_annual_reports.return_value = SAMPLE_BSE_REPORTS
        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []
        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    years = {r["year"] for r in result}
    assert "2021" in years or "2020" in years


def test_fetch_annual_reports_no_bse_scrip_uses_screener():
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:
        MockSC.return_value.get_financials.return_value = {"documents": SAMPLE_SCREENER_DOCS}
        MockNSE.return_value.get_annual_reports.return_value = []
        result = fetch_annual_reports(bse_scrip="", nse_symbol="HAL", years=5)

    assert len(result) >= 1
    assert all(r["source"] in ("screener", "NSE") for r in result)
    MockBSE.return_value.get_annual_reports.assert_not_called()


def test_fetch_annual_reports_all_fail_returns_empty():
    from opus.pipeline.retrieval.annual_reports import fetch_annual_reports

    with patch("opus.pipeline.retrieval.annual_reports.BSEClient") as MockBSE, \
         patch("opus.pipeline.retrieval.annual_reports.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.annual_reports.NSEClient") as MockNSE:
        MockBSE.return_value.get_annual_reports.side_effect = Exception("BSE down")
        MockSC.return_value.get_financials.side_effect = Exception("Screener down")
        MockNSE.return_value.get_annual_reports.side_effect = Exception("NSE down")
        result = fetch_annual_reports(bse_scrip="541154", nse_symbol="HAL", years=5)

    assert result == []
