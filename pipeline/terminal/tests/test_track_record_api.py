"""Tests for track record API endpoint."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_track(tmp_path, monkeypatch):
    import pipeline.terminal.api.track_record as tr_mod
    track = {
        "updated_at": "2026-04-18T16:00:00+05:30",
        "total_closed": 3,
        "win_rate_pct": 66.7,
        "avg_pnl_pct": 1.5,
        "recent": [
            {"signal_id": "SIG-001", "spread_name": "Defence vs IT", "open_date": "2026-04-10",
             "close_date": "2026-04-12", "days_open": 2, "final_pnl_pct": 3.2, "peak_pnl_pct": 4.1, "close_reason": "target_hit"},
            {"signal_id": "SIG-002", "spread_name": "Banks vs IT", "open_date": "2026-04-11",
             "close_date": "2026-04-14", "days_open": 3, "final_pnl_pct": -1.5, "peak_pnl_pct": 0.8, "close_reason": "stopped"},
            {"signal_id": "SIG-003", "spread_name": "Pharma vs Banks", "open_date": "2026-04-13",
             "close_date": "2026-04-15", "days_open": 2, "final_pnl_pct": 2.1, "peak_pnl_pct": 2.5, "close_reason": "trailing_stop"},
        ],
    }
    f = tmp_path / "track.json"
    f.write_text(json.dumps(track))
    monkeypatch.setattr(tr_mod, "_TRACK_FILE", f)


def test_track_record_summary(mock_track):
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/track-record").json()
    assert data["total_closed"] == 3
    assert data["win_rate_pct"] == 66.7
    assert len(data["trades"]) == 3


def test_equity_curve(mock_track):
    """Equity curve plots per-trade running average (each trade = 1 unit), not
    portfolio-sized cumulative. Sum is exposed alongside as `total_pnl_sum_pct`
    for the "if sized 1u/trade" view (rewrite #310)."""
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/track-record/equity-curve").json()
    assert len(data["curve"]) == 3
    assert data["n"] == 3
    # 3.2 + (-1.5) + 2.1 = 3.8 sum
    assert data["total_pnl_sum_pct"] == 3.8
    # mean of [3.2, -1.5, 2.1] = 1.2666... → rounded to 1.27
    assert data["avg_pnl_pct"] == 1.27
    # Curve values are running per-trade averages, chronological by close_date.
    assert data["curve"][-1]["value"] == round(3.8 / 3, 3)


def test_track_record_missing_file(tmp_path, monkeypatch):
    import pipeline.terminal.api.track_record as tr_mod
    monkeypatch.setattr(tr_mod, "_TRACK_FILE", tmp_path / "nope.json")
    from pipeline.terminal.app import app
    data = TestClient(app).get("/api/track-record").json()
    assert data["trades"] == []
    assert data["win_rate_pct"] == 0
