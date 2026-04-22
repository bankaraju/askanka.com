"""
Tests for today_regime.json schema contract.

today_regime.json must expose BOTH:
  - 'zone'   (canonical key — all UI/API consumers read this)
  - 'regime' (alias for legacy callers — backward compat for one release cycle)

Both keys must be present and equal (same ETF-derived regime string).
"""

import json
from pathlib import Path

import pytest


def test_today_regime_has_zone_key():
    """Production-file assertion: today_regime.json must have 'zone' key matching 'regime'.

    Note: this is a live-file assertion. It will fail if the overnight batch
    has not yet run (today_regime.json absent) or if the writer regresses.
    """
    p = Path(__file__).resolve().parent.parent / "data" / "today_regime.json"
    assert p.exists(), f"today_regime.json not found at {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("zone"), "today_regime.json must expose 'zone' (UI + API consumers read it)"
    assert data.get("regime"), "today_regime.json must expose 'regime' (legacy alias)"
    assert data.get("zone") == data.get("regime"), (
        f"'zone' ({data.get('zone')!r}) must equal 'regime' ({data.get('regime')!r})"
    )


def test_regime_scanner_write_today_regime_emits_zone(tmp_path, monkeypatch):
    """
    Unit test: regime_scanner.scan_regime() must write both 'zone' and 'regime' keys.

    We monkeypatch file-path constants and the MSI loader so no network calls are made.
    The test constructs a minimal regime_trade_map.json fixture in tmp_path.
    """
    import sys

    # Build a minimal regime_trade_map.json fixture
    trade_map_file = tmp_path / "regime_trade_map.json"
    trade_map_file.write_text(
        json.dumps({
            "today_zone": "RISK-ON",
            "updated_at": "2026-04-22T04:45:00+05:30",
            # No 'results' key → eligible_spreads will be empty (fine for this test)
        }),
        encoding="utf-8",
    )

    # Build a minimal prev_regime.json fixture (2 consecutive days → stable)
    prev_regime_file = tmp_path / "prev_regime.json"
    prev_regime_file.write_text(
        json.dumps({"regime": "RISK-ON", "consecutive_days": 2}),
        encoding="utf-8",
    )

    import pipeline.regime_scanner as rs

    # Redirect file paths to tmp_path
    out_file = tmp_path / "today_regime.json"
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", out_file)
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", prev_regime_file)
    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map_file)
    monkeypatch.setattr(rs, "_DATA", tmp_path)

    # Patch compute_msi inside regime_scanner's namespace to avoid live network calls
    fake_msi = {
        "msi_score": 60.0,
        "regime": "MACRO_NEUTRAL",
        "timestamp": "2026-04-22T04:45:00+05:30",
        "components": {},
    }

    # regime_scanner imports compute_msi lazily inside the function;
    # we inject a fake module into sys.modules so the import resolves to our stub.
    import types
    fake_macro_stress = types.ModuleType("macro_stress")
    fake_macro_stress.compute_msi = lambda: fake_msi
    monkeypatch.setitem(sys.modules, "macro_stress", fake_macro_stress)

    result = rs.scan_regime()

    assert out_file.exists(), "scan_regime() must write today_regime.json"
    written = json.loads(out_file.read_text(encoding="utf-8"))

    assert "zone" in written, "Writer must emit 'zone' key (canonical)"
    assert "regime" in written, "Writer must emit 'regime' key (legacy alias)"
    assert written["zone"] == written["regime"], (
        f"'zone' ({written['zone']!r}) must equal 'regime' ({written['regime']!r})"
    )
    assert written["zone"] == "RISK-ON", f"Expected RISK-ON, got {written['zone']!r}"
    assert result.get("zone") == "RISK-ON", "Returned dict must also have 'zone'"
