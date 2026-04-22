import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signal_rescorer


def _make_open_signals(path: Path, signals: list):
    path.write_text(json.dumps(signals, indent=2), encoding="utf-8")


def test_happy_path_attaches_rescore_to_each_signal(tmp_path, monkeypatch):
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [
        {"signal_id": "S1", "conviction_score": 80, "source": "SPREAD",
         "spread_name": "Defence vs IT", "long_legs": [], "short_legs": []},
        {"signal_id": "S2", "conviction_score": 70, "source": "CORRELATION_BREAK",
         "spread_name": "Phase C: BHEL", "long_legs": [], "short_legs": []},
    ])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs",
                        lambda: ({}, {}, {}, {}))
    def fake_rescore(sig, trust, breaks, profile, oi):
        return {"current_score": 55, "score_delta": 15 if sig["signal_id"] == "S1" else -5,
                "gate_reason_current": "ok", "gate_blocked_current": False,
                "rescored_at": "2026-04-22T11:30:00+05:30"}
    monkeypatch.setattr(signal_rescorer, "rescore_signal", fake_rescore)

    rc = signal_rescorer.main()
    assert rc == 0

    written = json.loads(open_file.read_text())
    assert written[0]["rescore"]["current_score"] == 55
    assert written[0]["rescore"]["score_delta"] == 15
    assert written[1]["rescore"]["current_score"] == 55


def test_empty_open_signals_is_noop(tmp_path, monkeypatch):
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs", lambda: ({}, {}, {}, {}))
    rc = signal_rescorer.main()
    assert rc == 0
    assert json.loads(open_file.read_text()) == []


def test_missing_file_exits_quietly(tmp_path, monkeypatch):
    open_file = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    assert signal_rescorer.main() == 2


def test_rescore_failure_leaves_prior_rescore_intact(tmp_path, monkeypatch):
    open_file = tmp_path / "open_signals.json"
    _make_open_signals(open_file, [
        {"signal_id": "S1", "conviction_score": 80, "source": "SPREAD",
         "long_legs": [], "short_legs": [], "rescore": {"current_score": 60}},
        {"signal_id": "S2", "conviction_score": 70, "source": "SPREAD",
         "long_legs": [], "short_legs": []},
    ])
    monkeypatch.setattr(signal_rescorer, "OPEN_SIGNALS_FILE", open_file)
    monkeypatch.setattr(signal_rescorer, "_load_enrichment_inputs", lambda: ({}, {}, {}, {}))

    def flaky_rescore(sig, *a, **kw):
        if sig["signal_id"] == "S1":
            raise RuntimeError("boom")
        return {"current_score": 55, "score_delta": 15,
                "gate_reason_current": "ok", "gate_blocked_current": False,
                "rescored_at": "2026-04-22T11:30:00+05:30"}
    monkeypatch.setattr(signal_rescorer, "rescore_signal", flaky_rescore)

    rc = signal_rescorer.main()
    assert rc == 0

    written = json.loads(open_file.read_text())
    assert written[0]["rescore"]["current_score"] == 60  # untouched from prior
    assert written[1]["rescore"]["current_score"] == 55  # freshly written
