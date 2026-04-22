import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import msi_refresh


def _write_morning_regime(path: Path, **overrides):
    data = {
        "timestamp": "2026-04-22T09:25:00+05:30",
        "regime": "RISK-OFF",
        "regime_source": "etf_engine",
        "msi_score": 42.4,
        "msi_regime": "MACRO_NEUTRAL",
        "msi_updated_at": "2026-04-22T09:25:00+05:30",
        "msi_cached_inputs": {
            "fii_net": -1200.0, "dii_net": 800.0, "combined_flow": -400.0,
        },
        "regime_stable": True,
        "consecutive_days": 2,
        "trade_map_key": "RISK-OFF",
        "eligible_spreads": {"Defence vs IT": {"1d_win": 45}},
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_happy_path_updates_msi_fields_only(tmp_path, monkeypatch):
    """On success, only msi_score / msi_regime / msi_updated_at change;
    every other field (including eligible_spreads) is preserved byte-for-byte."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file)
    monkeypatch.setattr(msi_refresh, "REGIME_FILE", regime_file)

    fake_msi = {
        "msi_score": 48.2, "regime": "MACRO_NEUTRAL",
        "fii_net": -1200.0, "dii_net": 800.0, "combined_flow": -400.0,
        "timestamp": "2026-04-22T11:30:00+05:30",
    }
    with patch.object(msi_refresh, "compute_msi", return_value=fake_msi) as mock_compute:
        rc = msi_refresh.main()

    call_kwargs = mock_compute.call_args.kwargs
    assert call_kwargs["cached_fii"]["fii_net"] == -1200.0
    assert rc == 0

    after = json.loads(regime_file.read_text())
    assert after["msi_score"] == 48.2
    assert after["msi_regime"] == "MACRO_NEUTRAL"
    assert after["msi_updated_at"] == "2026-04-22T11:30:00+05:30"
    assert after["regime_stable"] is True
    assert after["consecutive_days"] == 2
    assert after["eligible_spreads"] == {"Defence vs IT": {"1d_win": 45}}


def test_missing_cached_fii_holds_morning(tmp_path, monkeypatch):
    """If msi_cached_inputs is None (morning MSI compute failed), do nothing."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file, msi_cached_inputs=None)
    monkeypatch.setattr(msi_refresh, "REGIME_FILE", regime_file)

    with patch.object(msi_refresh, "compute_msi") as mock_compute:
        rc = msi_refresh.main()

    mock_compute.assert_not_called()
    assert rc == 2
    assert json.loads(regime_file.read_text())["msi_score"] == 42.4


def test_compute_exception_holds_morning(tmp_path, monkeypatch):
    """If compute_msi raises, leave the file alone and exit 2."""
    regime_file = tmp_path / "today_regime.json"
    _write_morning_regime(regime_file)
    monkeypatch.setattr(msi_refresh, "REGIME_FILE", regime_file)

    before = regime_file.read_text()
    with patch.object(msi_refresh, "compute_msi", side_effect=RuntimeError("vix fetch 502")):
        rc = msi_refresh.main()

    assert rc == 2
    assert regime_file.read_text() == before  # byte-identical


def test_missing_regime_file_exits_quietly(tmp_path, monkeypatch):
    """No file -> exit 2, no exception to scheduler."""
    regime_file = tmp_path / "today_regime.json"  # does not exist
    monkeypatch.setattr(msi_refresh, "REGIME_FILE", regime_file)
    assert msi_refresh.main() == 2
