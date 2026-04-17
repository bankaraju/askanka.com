"""Tests for IndianAPI financial data client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


SAMPLE_FINANCIAL_RESPONSE = {
    "financial_data": [
        {"quarter": "Q3FY25", "revenue": 15000, "pat": 2100, "opm": 22.5},
        {"quarter": "Q2FY25", "revenue": 14500, "pat": 1900, "opm": 21.0},
    ]
}

SAMPLE_ANNOUNCEMENTS = [
    {"headline": "Q3FY25 Analyst Meet Transcript", "date": "2025-01-15", "link": "https://example.com/concall.pdf"},
    {"headline": "Board Meeting Outcome", "date": "2025-01-10", "link": "https://example.com/board.pdf"},
]


def test_fetch_financials_returns_data():
    from opus.pipeline.retrieval.indianapi_client import fetch_financials

    with patch("opus.pipeline.retrieval.indianapi_client.requests") as mock_req, \
         patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value="test_key"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_FINANCIAL_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp
        result = fetch_financials("HAL")

    assert len(result) >= 1
    assert result[0]["source"] == "indianapi"


def test_fetch_financials_no_key_returns_empty():
    from opus.pipeline.retrieval.indianapi_client import fetch_financials

    with patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value=None):
        result = fetch_financials("HAL")

    assert result == []


def test_fetch_concall_announcements_filters_transcripts():
    from opus.pipeline.retrieval.indianapi_client import fetch_concall_announcements

    with patch("opus.pipeline.retrieval.indianapi_client.requests") as mock_req, \
         patch("opus.pipeline.retrieval.indianapi_client._api_key", return_value="test_key"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_ANNOUNCEMENTS
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp
        result = fetch_concall_announcements("HAL")

    assert len(result) == 1
    assert "Transcript" in result[0]["headline"]
