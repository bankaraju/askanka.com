"""
Tests for B1: eligible_spreads entries annotated with conviction/z_score/gate_status/tier.

Verifies:
  1. scan_regime() writes conviction, z_score, gate_status, tier into today_regime.json.
  2. _classify_conviction() applies correct thresholds.
  3. Missing today_spread_return does not crash the annotation loop.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import regime_scanner as rs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade_map(tmp_path, regime="RISK-OFF", spreads=None):
    """Write a minimal regime_trade_map.json to tmp_path."""
    spreads = spreads or {}
    trade_map = tmp_path / "trade_map.json"
    trade_map.write_text(json.dumps({
        "today_zone": regime,
        regime: spreads,
    }))
    return trade_map


def _fake_msi():
    return {
        "msi_score": 30.0,
        "regime": "MACRO_STRESS",
        "fii_net": -500.0,
        "dii_net": 200.0,
        "combined_flow": -300.0,
        "timestamp": "2026-04-22T09:25:00+05:30",
        "components": {},
    }


# ---------------------------------------------------------------------------
# Test 1: eligible_spreads carry conviction/z_score/gate_status/tier after scan
# ---------------------------------------------------------------------------

def test_eligible_spreads_carry_conviction_and_z(monkeypatch, tmp_path):
    """After scan_regime, each eligible entry has conviction/z_score/gate_status/tier."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(rs, "_DATA", data_dir)
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", data_dir / "today_regime.json")
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", data_dir / "prev_regime.json")

    # One spread with legs so bootstrap + annotation can run
    spread_name = "Defence vs IT"
    spread_entry = {
        "spread": spread_name,
        "best_win": 70,
        "1d_win": 65,
        "best_period": 5,
        "long_legs": ["HAL.NS", "BEL.NS"],
        "short_legs": ["INFY.NS", "TCS.NS"],
    }
    trade_map = _make_trade_map(tmp_path, regime="RISK-OFF", spreads={spread_name: spread_entry})
    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map)

    # Stub spread_bootstrap.ensure so we don't hit EODHD
    fake_bootstrap = {"status": "ok", "tier": "FULL", "n": 40}
    import spread_bootstrap as _sb
    monkeypatch.setattr(_sb, "ensure", lambda name, long_legs, short_legs: fake_bootstrap)

    # Stub spread_intelligence.apply_gates to return a controlled result
    import spread_intelligence as _si
    def _fake_apply_gates(spread_name, regime_data, spread_stats, today_spread_return, regime):
        return {"status": "ACTIVE", "z_score": 2.5, "percentile": 99.4}
    monkeypatch.setattr(_si, "apply_gates", _fake_apply_gates)

    # Stub spread_statistics so spread_stats is empty (bootstrap handles it)
    try:
        import spread_statistics as _ss
        monkeypatch.setattr(_ss, "_load_stats", lambda: {})
    except Exception:
        pass

    with patch("macro_stress.compute_msi", return_value=_fake_msi()):
        result = rs.scan_regime()

    assert spread_name in result["eligible_spreads"], "Spread missing from eligible_spreads"
    entry = result["eligible_spreads"][spread_name]

    assert "conviction" in entry, "conviction key missing"
    assert entry["conviction"] in ("HIGH", "MEDIUM", "LOW", "PROVISIONAL", "NONE"), (
        f"Unexpected conviction value: {entry['conviction']}"
    )
    assert "z_score" in entry, "z_score key missing"
    assert "gate_status" in entry, "gate_status key missing"
    assert "tier" in entry, "tier key missing"
    assert entry["tier"] in ("FULL", "PROVISIONAL"), f"Unexpected tier: {entry['tier']}"

    # Also check that today_regime.json on disk matches
    written = json.loads((data_dir / "today_regime.json").read_text())
    disk_entry = written["eligible_spreads"][spread_name]
    assert disk_entry["conviction"] == entry["conviction"]
    assert disk_entry["gate_status"] == entry["gate_status"]


# ---------------------------------------------------------------------------
# Test 2: _classify_conviction thresholds
# ---------------------------------------------------------------------------

def test_conviction_classifier_thresholds():
    """_classify_conviction applies documented thresholds correctly."""
    from regime_scanner import _classify_conviction

    # HIGH path: z >= 2.0 AND best_win >= 65
    assert _classify_conviction({"best_win": 70}, {"status": "ACTIVE", "z_score": 2.5}, "FULL") == "HIGH"

    # MEDIUM path: z >= 1.5 AND best_win >= 55
    assert _classify_conviction({"best_win": 58}, {"status": "ACTIVE", "z_score": 1.7}, "FULL") == "MEDIUM"

    # LOW path: in-gate (ACTIVE) but below thresholds
    assert _classify_conviction({"best_win": 50}, {"status": "ACTIVE", "z_score": 1.2}, "FULL") == "LOW"

    # NONE path: INSUFFICIENT_DATA dominates regardless of z_score
    assert _classify_conviction({"best_win": 70}, {"status": "INSUFFICIENT_DATA", "z_score": 2.5}, "FULL") == "NONE"

    # NONE path: INACTIVE
    assert _classify_conviction({"best_win": 70}, {"status": "INACTIVE", "z_score": 2.5}, "FULL") == "NONE"

    # PROVISIONAL dominates everything
    assert _classify_conviction({"best_win": 70}, {"status": "ACTIVE", "z_score": 2.5}, "PROVISIONAL") == "PROVISIONAL"

    # AT_MEAN → LOW (in-gate, divergence insufficient)
    assert _classify_conviction({"best_win": 60}, {"status": "AT_MEAN", "z_score": 0.5}, "FULL") == "LOW"

    # Edge: missing z_score treated as 0 → below HIGH/MEDIUM thresholds → LOW if ACTIVE
    assert _classify_conviction({"best_win": 80}, {"status": "ACTIVE"}, "FULL") == "LOW"


# ---------------------------------------------------------------------------
# Test 3: missing today_spread_return does not crash
# ---------------------------------------------------------------------------

def test_missing_today_return_does_not_crash(monkeypatch, tmp_path):
    """When today_spread_return is unavailable, annotation completes without raising."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(rs, "_DATA", data_dir)
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", data_dir / "today_regime.json")
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", data_dir / "prev_regime.json")

    spread_name = "Coal vs OMCs"
    spread_entry = {
        "spread": spread_name,
        "best_win": 68,
        "best_period": 3,
        "long_legs": ["COALINDIA.NS"],
        "short_legs": ["IOC.NS"],
    }
    trade_map = _make_trade_map(tmp_path, regime="RISK-OFF", spreads={spread_name: spread_entry})
    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map)

    import spread_bootstrap as _sb
    monkeypatch.setattr(_sb, "ensure", lambda name, long_legs, short_legs: {"status": "ok", "tier": "FULL", "n": 35})

    # apply_gates raises when given None — the annotation loop must handle this gracefully
    import spread_intelligence as _si
    def _crashing_apply_gates(spread_name, regime_data, spread_stats, today_spread_return, regime):
        if today_spread_return is None:
            raise ValueError("today_spread_return cannot be None")
        return {"status": "ACTIVE", "z_score": 2.1}
    monkeypatch.setattr(_si, "apply_gates", _crashing_apply_gates)

    with patch("macro_stress.compute_msi", return_value=_fake_msi()):
        result = rs.scan_regime()  # Must not raise

    entry = result["eligible_spreads"].get(spread_name, {})
    # Even if gates crashed, the entry must still have the annotation keys
    assert "conviction" in entry
    assert "gate_status" in entry
    assert "tier" in entry
    # With no today_return and a crashing gate, conviction should be NONE or PROVISIONAL
    assert entry["conviction"] in ("NONE", "PROVISIONAL")
