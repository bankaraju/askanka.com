import json
from pathlib import Path
from pipeline.autoresearch.earnings_decoupling.universe import is_in_fno, load_history


def test_load_history_reads_snapshots(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({
        "snapshots": [
            {"date": "2025-01-31", "symbols": ["RELIANCE", "TCS"]},
            {"date": "2025-02-28", "symbols": ["RELIANCE", "TCS", "INFY"]},
        ]
    }))
    h = load_history(p)
    assert len(h) == 2
    assert h[0]["date"] == "2025-01-31"


def test_is_in_fno_uses_most_recent_prior_snapshot(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({
        "snapshots": [
            {"date": "2025-01-31", "symbols": ["RELIANCE", "TCS"]},
            {"date": "2025-02-28", "symbols": ["RELIANCE", "TCS", "INFY"]},
        ]
    }))
    h = load_history(p)
    assert is_in_fno(h, "INFY", "2025-02-15") is False, "INFY admitted only Feb-end"
    assert is_in_fno(h, "INFY", "2025-03-15") is True
    assert is_in_fno(h, "RELIANCE", "2025-01-31") is True
    assert is_in_fno(h, "WIPRO", "2025-03-15") is False


def test_is_in_fno_event_before_first_snapshot_returns_false(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"snapshots": [{"date": "2025-01-31", "symbols": ["RELIANCE"]}]}))
    h = load_history(p)
    assert is_in_fno(h, "RELIANCE", "2024-12-15") is False
