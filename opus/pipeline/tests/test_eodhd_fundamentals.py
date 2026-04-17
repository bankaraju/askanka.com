"""Tests for EODHD Fundamentals API client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SAMPLE_FUNDAMENTALS = {
    "Financials": {
        "Income_Statement": {
            "quarterly": {
                "2025-03-31": {"totalRevenue": "15000000000", "netIncome": "2100000000"},
                "2024-12-31": {"totalRevenue": "14500000000", "netIncome": "1900000000"},
            }
        },
        "Balance_Sheet": {
            "quarterly": {
                "2025-03-31": {"totalAssets": "50000000000"},
            }
        },
    }
}


def test_fetch_fundamentals_returns_quarterly_data():
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals.requests") as mock_req, \
         patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value="test_key"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_FUNDAMENTALS
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp
        result = fetch_fundamentals("HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "eodhd"
    assert "revenue" in result[0]
    assert "pat" in result[0]


def test_fetch_fundamentals_no_key_returns_empty():
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value=None):
        result = fetch_fundamentals("HAL")

    assert result == []


def test_fetch_fundamentals_http_error_returns_empty():
    from opus.pipeline.retrieval.eodhd_fundamentals import fetch_fundamentals

    with patch("opus.pipeline.retrieval.eodhd_fundamentals.requests") as mock_req, \
         patch("opus.pipeline.retrieval.eodhd_fundamentals._api_key", return_value="test_key"):
        mock_req.get.side_effect = Exception("Timeout")
        result = fetch_fundamentals("HAL")

    assert result == []
