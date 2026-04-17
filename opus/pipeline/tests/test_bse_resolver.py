# opus/pipeline/tests/test_bse_resolver.py
"""Tests for BSE scrip resolver — maps NSE symbols to BSE scrip codes."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_BSE_SUGGEST_RESPONSE = [
    {"scrip_code": "500325", "scrip_name": "Reliance Industries Ltd.", "isin": "INE002A01018", "status": "Active"},
    {"scrip_code": "890144", "scrip_name": "Reliance Capital Ltd.", "isin": "INE013A01015", "status": "Active"},
]


def test_resolve_single_symbol_returns_best_match():
    """BSE Suggest API returns multiple results; resolver picks the best match."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BSE_SUGGEST_RESPONSE
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = resolve_bse_scrip("RELIANCE")

    assert result is not None
    assert result["bse_scrip"] == "500325"
    assert result["isin"] == "INE002A01018"
    assert "company_name" in result


def test_resolve_returns_none_on_empty_response():
    """Empty API response → None."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.status_code = 200
        mock_req.get.return_value = mock_resp

        result = resolve_bse_scrip("NONEXISTENT")

    assert result is None


def test_resolve_returns_none_on_http_error():
    """HTTP error → None, no exception raised."""
    from opus.pipeline.retrieval.bse_resolver import resolve_bse_scrip

    with patch("opus.pipeline.retrieval.bse_resolver.requests") as mock_req:
        mock_req.get.side_effect = Exception("Connection timeout")
        result = resolve_bse_scrip("TCS")

    assert result is None


def test_batch_resolve_all_caches_to_file(tmp_path: Path):
    """batch_resolve writes results to bse_scrip_map.json."""
    from opus.pipeline.retrieval.bse_resolver import batch_resolve

    symbols = ["HAL", "TCS"]
    cache_path = tmp_path / "bse_scrip_map.json"

    def fake_resolve(sym):
        return {"bse_scrip": f"999{sym}", "company_name": f"{sym} Ltd.", "isin": f"INE{sym}"}

    with patch("opus.pipeline.retrieval.bse_resolver.resolve_bse_scrip", side_effect=fake_resolve):
        result = batch_resolve(symbols, cache_path=cache_path)

    assert len(result["mappings"]) == 2
    assert "HAL" in result["mappings"]
    assert cache_path.exists()
    cached = json.loads(cache_path.read_text())
    assert cached["count"] == 2


def test_batch_resolve_skips_already_cached(tmp_path: Path):
    """Symbols already in cache file are not re-fetched."""
    from opus.pipeline.retrieval.bse_resolver import batch_resolve

    cache_path = tmp_path / "bse_scrip_map.json"
    existing = {
        "resolved_at": "2026-04-17",
        "count": 1,
        "mappings": {"HAL": {"bse_scrip": "541154", "company_name": "HAL", "isin": "INE066F01020"}},
    }
    cache_path.write_text(json.dumps(existing))

    call_count = 0
    def fake_resolve(sym):
        nonlocal call_count
        call_count += 1
        return {"bse_scrip": f"999{sym}", "company_name": f"{sym} Ltd.", "isin": f"INE{sym}"}

    with patch("opus.pipeline.retrieval.bse_resolver.resolve_bse_scrip", side_effect=fake_resolve):
        result = batch_resolve(["HAL", "TCS"], cache_path=cache_path)

    assert call_count == 1  # only TCS fetched, HAL skipped
    assert len(result["mappings"]) == 2
