"""Tests for batch retrieval orchestrator."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    fno = tmp_path / "config" / "fno_stocks.json"
    fno.parent.mkdir(parents=True)
    fno.write_text(json.dumps({"symbols": ["HAL", "TCS", "RELIANCE"]}))

    scrip_map = tmp_path / "config" / "bse_scrip_map.json"
    scrip_map.write_text(json.dumps({
        "mappings": {"HAL": {"bse_scrip": "541154"}, "TCS": {"bse_scrip": "532540"}, "RELIANCE": {"bse_scrip": "500325"}}
    }))
    return tmp_path


def test_run_batch_processes_all_stocks(config_dir: Path):
    from opus.pipeline.batch_retrieval import run_batch

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", return_value=[{"quarter": "Q1FY25"}] * 8), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[{"year": "2024"}] * 5), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[{"quarter": "Q1FY25"}] * 10):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert summary["total"] == 3
    assert summary["fully_covered"] == 3
    assert (config_dir / "artifacts" / "retrieval_summary.json").exists()


def test_run_batch_flags_partial_transcripts(config_dir: Path):
    from opus.pipeline.batch_retrieval import run_batch

    call_count = 0
    def variable_transcripts(symbol, **kwargs):
        nonlocal call_count
        call_count += 1
        if symbol == "HAL":
            return [{"quarter": f"Q{i}FY25"} for i in range(8)]
        return [{"quarter": "Q1FY25"}]

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", side_effect=variable_transcripts), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[]), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[]):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert summary["fully_covered"] == 1
    assert summary["partial_transcripts"] == 2


def test_run_batch_resumes_from_progress(config_dir: Path):
    from opus.pipeline.batch_retrieval import run_batch

    progress_dir = config_dir / "artifacts"
    progress_dir.mkdir(parents=True)
    progress = {"completed": ["HAL", "TCS"]}
    (progress_dir / "batch_progress.json").write_text(json.dumps(progress))

    call_count = 0
    def counting_transcripts(symbol, **kwargs):
        nonlocal call_count
        call_count += 1
        return [{"quarter": f"Q{i}FY25"} for i in range(8)]

    with patch("opus.pipeline.batch_retrieval.fetch_transcripts", side_effect=counting_transcripts), \
         patch("opus.pipeline.batch_retrieval.fetch_annual_reports", return_value=[]), \
         patch("opus.pipeline.batch_retrieval.fetch_quarterly_filings", return_value=[]):

        summary = run_batch(
            fno_path=config_dir / "config" / "fno_stocks.json",
            scrip_map_path=config_dir / "config" / "bse_scrip_map.json",
            output_dir=config_dir / "artifacts",
            delay=0,
        )

    assert call_count == 1  # only RELIANCE fetched
