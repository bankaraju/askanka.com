# opus/pipeline/tests/test_transcripts.py
"""Tests for transcript fetcher — Screener PDF download + text extraction."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_SCREENER_DOCS = [
    {"title": "Q3FY25 Concall Transcript", "url": "https://example.com/q3fy25.pdf", "type": "transcript"},
    {"title": "Q2FY25 Earnings Call Transcript", "url": "https://example.com/q2fy25.pdf", "type": "transcript"},
    {"title": "Annual Report 2024", "url": "https://example.com/ar2024.pdf", "type": "annual_report"},
]


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "transcripts"


def _fake_pdf_bytes(text: str = "This is a test transcript with enough words " * 20) -> bytes:
    """Create minimal valid-looking bytes (mock will handle extraction)."""
    return b"%PDF-1.4 fake content " + text.encode()


def test_fetch_transcripts_returns_screener_results(cache_dir: Path):
    """Screener returns 2 transcript links → 2 transcripts fetched."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    fake_text = "Management discussion about quarterly results and future guidance plans " * 60

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.transcripts.requests") as mock_req, \
         patch("opus.pipeline.retrieval.transcripts._extract_pdf_text", return_value=fake_text):

        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = SAMPLE_SCREENER_DOCS[:2]
        MockSC.return_value = mock_sc_instance

        mock_resp = MagicMock()
        mock_resp.content = _fake_pdf_bytes()
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 2
    assert result[0]["source"] == "screener"
    assert result[0]["word_count"] >= 500
    assert "quarter" in result[0]
    assert "text" in result[0]
    assert "fetched_at" in result[0]


def test_fetch_transcripts_filters_short_pdfs(cache_dir: Path):
    """PDFs with < 500 words are skipped."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    short_text = "Too short"

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC, \
         patch("opus.pipeline.retrieval.transcripts.requests") as mock_req, \
         patch("opus.pipeline.retrieval.transcripts._extract_pdf_text", return_value=short_text):

        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = SAMPLE_SCREENER_DOCS[:1]
        MockSC.return_value = mock_sc_instance

        mock_resp = MagicMock()
        mock_resp.content = _fake_pdf_bytes()
        mock_req.get.return_value = mock_resp

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 0


def test_fetch_transcripts_uses_cache(cache_dir: Path):
    """Cached transcript is returned without HTTP call."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    sym_dir = cache_dir / "HAL"
    sym_dir.mkdir(parents=True)
    cached = {"quarter": "Q3FY25", "text": "cached text " * 100, "source": "screener",
              "url": "https://example.com/q3.pdf", "word_count": 600, "fetched_at": "2026-04-17"}
    (sym_dir / "Q3FY25.json").write_text(json.dumps(cached))

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC:
        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.return_value = []
        MockSC.return_value = mock_sc_instance

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert len(result) == 1
    assert result[0]["quarter"] == "Q3FY25"


def test_fetch_transcripts_empty_on_failure(cache_dir: Path):
    """Screener failure → empty list, no exception."""
    from opus.pipeline.retrieval.transcripts import fetch_transcripts

    with patch("opus.pipeline.retrieval.transcripts.ScreenerClient") as MockSC:
        mock_sc_instance = MagicMock()
        mock_sc_instance.get_transcript_urls.side_effect = Exception("Network error")
        MockSC.return_value = mock_sc_instance

        result = fetch_transcripts("HAL", cache_dir=cache_dir)

    assert result == []


def test_quarter_extraction_from_title():
    """Extract quarter label from transcript PDF title."""
    from opus.pipeline.retrieval.transcripts import _extract_quarter_from_title

    assert _extract_quarter_from_title("Q3FY25 Concall Transcript") == "Q3FY25"
    assert _extract_quarter_from_title("Q1 FY 2024 Earnings Call") == "Q1FY24"
    assert _extract_quarter_from_title("Q4FY2025 Results") == "Q4FY25"
    assert _extract_quarter_from_title("No quarter info here").startswith("UNKNOWN_")
