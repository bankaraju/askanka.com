"""Tests for TA daily scanner."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
import pandas as pd


SAMPLE_FINGERPRINT = {
    "symbol": "HAL",
    "fingerprint": [
        {"pattern": "BB_SQUEEZE", "direction": "LONG", "significance": "STRONG",
         "occurrences": 18, "win_rate_5d": 0.72, "avg_return_5d": 2.8},
        {"pattern": "RSI_OVERSOLD_BOUNCE", "direction": "LONG", "significance": "MODERATE",
         "occurrences": 12, "win_rate_5d": 0.58, "avg_return_5d": 1.5},
    ],
}


@pytest.fixture
def setup_dirs(tmp_path: Path):
    fp_dir = tmp_path / "ta_fingerprints"
    fp_dir.mkdir()
    (fp_dir / "HAL.json").write_text(json.dumps(SAMPLE_FINGERPRINT))

    hist_dir = tmp_path / "ta_historical"
    hist_dir.mkdir()
    rows = ["Date,Open,High,Low,Close,Volume"]
    for i in range(50):
        d = pd.Timestamp("2025-01-01") + pd.Timedelta(days=i)
        rows.append(f"{d.strftime('%Y-%m-%d')},{100+i},{102+i},{98+i},{101+i},1000000")
    (hist_dir / "HAL.csv").write_text("\n".join(rows))

    return {"fingerprints": fp_dir, "historical": hist_dir, "output": tmp_path}


def test_scan_returns_alerts(setup_dirs):
    from ta_daily_scanner import scan_stock
    alerts = scan_stock("HAL",
                        fingerprint_dir=setup_dirs["fingerprints"],
                        historical_dir=setup_dirs["historical"])
    assert isinstance(alerts, list)
    for a in alerts:
        assert "symbol" in a
        assert "pattern" in a
        assert "status" in a
        assert a["status"] in ("TRIGGERED", "APPROACHING")


def test_scan_missing_fingerprint_returns_empty(setup_dirs):
    from ta_daily_scanner import scan_stock
    alerts = scan_stock("NONEXISTENT",
                        fingerprint_dir=setup_dirs["fingerprints"],
                        historical_dir=setup_dirs["historical"])
    assert alerts == []


def test_scan_all_writes_output(setup_dirs):
    from ta_daily_scanner import scan_all
    scan_all(symbols=["HAL"],
             fingerprint_dir=setup_dirs["fingerprints"],
             historical_dir=setup_dirs["historical"],
             output_path=setup_dirs["output"] / "ta_alerts.json")
    assert (setup_dirs["output"] / "ta_alerts.json").exists()
    data = json.loads((setup_dirs["output"] / "ta_alerts.json").read_text())
    assert "date" in data
    assert "alerts" in data
