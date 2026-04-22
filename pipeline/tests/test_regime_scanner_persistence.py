"""Tests that regime_scanner persists msi_updated_at + cached FII/DII fields.

These are consumed by the intraday MSI refresh (plan 2026-04-22-msi-intraday).
If the morning scan does not write them, intraday refresh has no cache to
incrementally update, and the terminal banner has no honest timestamp to show.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import regime_scanner as rs


def test_morning_scan_persists_cached_fii_and_msi_timestamp(tmp_path, monkeypatch):
    # Arrange: redirect regime_scanner to a tmp data dir
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(rs, "_DATA", data_dir)
    monkeypatch.setattr(rs, "_TODAY_REGIME_FILE", data_dir / "today_regime.json")
    monkeypatch.setattr(rs, "_PREV_REGIME_FILE", data_dir / "prev_regime.json")

    # Fake trade map so the scanner doesn't try to read autoresearch files.
    # regime_scanner reads raw_map["today_zone"] and raw_map["results"] (falling
    # back to raw_map itself). We keep the regime keys at the top level so the
    # fallback path matches today_zone="NEUTRAL".
    trade_map = tmp_path / "trade_map.json"
    trade_map.write_text(json.dumps({
        "today_zone": "NEUTRAL",
        "RISK-OFF": {},
        "NEUTRAL": {},
    }))
    monkeypatch.setattr(rs, "_TRADE_MAP", trade_map)

    # Fake MSI so no HTTP calls happen. The import inside scan_regime is
    # `from macro_stress import compute_msi` — patch at module level.
    fake_msi = {
        "msi_score": 42.4,
        "regime": "MACRO_NEUTRAL",
        "fii_net": -1234.5,
        "dii_net": 890.1,
        "combined_flow": -344.4,
        "timestamp": "2026-04-22T09:25:00+05:30",
        "components": {},
    }
    with patch("macro_stress.compute_msi", return_value=fake_msi):
        rs.scan_regime()

    written = json.loads((data_dir / "today_regime.json").read_text())
    assert written["msi_score"] == 42.4
    assert written["msi_updated_at"] == "2026-04-22T09:25:00+05:30"
    # Cached FII fields: raw numbers, not nested
    assert written["msi_cached_inputs"]["fii_net"] == -1234.5
    assert written["msi_cached_inputs"]["dii_net"] == 890.1
    assert written["msi_cached_inputs"]["combined_flow"] == -344.4
