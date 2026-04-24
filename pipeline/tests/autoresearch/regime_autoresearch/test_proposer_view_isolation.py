"""The proposer MUST be unable to read holdout_outcomes.jsonl."""
from __future__ import annotations

import pytest

from pipeline.autoresearch.regime_autoresearch.proposer import ProposerView


def test_view_exposes_in_sample_log(tmp_path):
    in_sample = tmp_path / "proposal_log.jsonl"
    in_sample.write_text('{"proposal_id": "P-1", "result": "rejected_in_sample"}\n')
    view = ProposerView(in_sample_log=in_sample, holdout_log=tmp_path / "holdout.jsonl",
                         strategy_results=tmp_path / "sr.json")
    assert view.read_in_sample_tail(1)[0]["proposal_id"] == "P-1"


def test_view_blocks_holdout(tmp_path):
    holdout = tmp_path / "holdout.jsonl"
    holdout.write_text('{"proposal_id": "P-2", "result": "holdout_pass"}\n')
    view = ProposerView(in_sample_log=tmp_path / "in_sample.jsonl",
                         holdout_log=holdout, strategy_results=tmp_path / "sr.json")
    with pytest.raises(PermissionError, match="holdout"):
        view.read_holdout_tail(1)


def test_view_respects_context_cap(tmp_path):
    in_sample = tmp_path / "proposal_log.jsonl"
    lines = [f'{{"proposal_id": "P-{i}"}}\n' for i in range(250)]
    in_sample.write_text("".join(lines))
    view = ProposerView(in_sample_log=in_sample, holdout_log=tmp_path / "h.jsonl",
                         strategy_results=tmp_path / "sr.json")
    tail = view.read_in_sample_tail(200)
    assert len(tail) == 200
    assert tail[-1]["proposal_id"] == "P-249"
