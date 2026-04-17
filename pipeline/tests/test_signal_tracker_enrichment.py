import json
import sys
import pytest
from pathlib import Path

# Ensure pipeline/ is on sys.path so bare imports (from config import ...)
# inside signal_tracker.py and signal_enrichment.py resolve correctly.
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def rigour_env(tmp_path, monkeypatch):
    """Set up minimal rigour fixtures and redirect paths."""
    # Write minimal fixtures
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({
        "positions": [
            {"symbol": "HAL", "side": "LONG", "trust_grade": "A", "trust_score": 80}
        ]
    }))

    breaks = tmp_path / "breaks.json"
    breaks.write_text(json.dumps({"breaks": []}))

    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({
        "stock_profiles": {
            "HAL": {"summary": {"hit_rate": 0.6, "tradeable_rate": 0.9,
                               "persistence_rate": 0.4, "episode_count": 10,
                               "avg_drift_1d": 0.001}}
        }
    }))

    oi = tmp_path / "oi.json"
    oi.write_text(json.dumps([]))

    # Patch enrichment paths
    import signal_enrichment as se
    monkeypatch.setattr(se, "TRUST_PATH", trust)
    monkeypatch.setattr(se, "BREAKS_PATH", breaks)
    monkeypatch.setattr(se, "REGIME_PROFILE_PATH", profile)
    monkeypatch.setattr(se, "OI_ANOMALIES_PATH", oi)

    # Redirect signal output to tmp
    import signal_tracker as st
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    monkeypatch.setattr(st, "SIGNALS_DIR", signals_dir)
    monkeypatch.setattr(st, "OPEN_FILE", signals_dir / "open_signals.json")
    monkeypatch.setattr(st, "CLOSED_FILE", signals_dir / "closed_signals.json")
    (signals_dir / "open_signals.json").write_text("[]")
    (signals_dir / "closed_signals.json").write_text("[]")

    # Ensure enrichment is enabled
    monkeypatch.setattr("signal_tracker.SIGNAL_ENRICHMENT_ENABLED", True)
    monkeypatch.setattr("signal_tracker.SIGNAL_GATE_ENABLED", False)

    return {"signals_dir": signals_dir, "trust": trust}


def test_save_signal_attaches_enrichment(rigour_env):
    from signal_tracker import save_signal, load_open_signals

    signal = {
        "signal_id": "SIG-TEST-ENRICH",
        "spread_name": "Defence vs IT",
        "long_legs": [{"ticker": "HAL", "price": 4284.80}],
        "short_legs": [{"ticker": "TCS", "price": 2572.00}],
        "status": "OPEN",
        "tier": "SIGNAL",
    }
    save_signal(signal)

    loaded = load_open_signals()
    assert len(loaded) == 1
    s = loaded[0]
    assert "trust_scores" in s
    assert s["trust_scores"]["HAL"]["trust_grade"] == "A"
    assert "conviction_score" in s
    assert "gate_reason" in s
    assert "rigour_trail" in s
    assert s["gate_blocked"] is False  # gate disabled


def test_save_signal_works_when_enrichment_disabled(rigour_env, monkeypatch):
    monkeypatch.setattr("signal_tracker.SIGNAL_ENRICHMENT_ENABLED", False)
    from signal_tracker import save_signal, load_open_signals

    signal = {"signal_id": "SIG-NOENRICH", "long_legs": [], "short_legs": []}
    save_signal(signal)

    loaded = load_open_signals()
    assert len(loaded) == 1
    assert "trust_scores" not in loaded[0]  # enrichment skipped
