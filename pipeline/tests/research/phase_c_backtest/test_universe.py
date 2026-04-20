from __future__ import annotations

import json
import pytest
from unittest.mock import patch
from pipeline.research.phase_c_backtest import universe


SAMPLE_FO_MKTLOTS_CSV = """SYMBOL,UNDERLYING,2026-APR,2026-MAY,2026-JUN
RELIANCE,RELIANCE,250,250,250
HDFCBANK,HDFCBANK,550,550,550
TCS,TCS,150,150,150
"""


def test_universe_for_date_returns_set(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "_UNIVERSE_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.universe._download_mktlots_csv", return_value=SAMPLE_FO_MKTLOTS_CSV):
        u = universe.universe_for_date("2026-04-15")
    assert u == {"RELIANCE", "HDFCBANK", "TCS"}


def test_universe_caches_per_month(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "_UNIVERSE_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.universe._download_mktlots_csv", return_value=SAMPLE_FO_MKTLOTS_CSV) as m:
        universe.universe_for_date("2026-04-15")
        universe.universe_for_date("2026-04-20")  # same month
    assert m.call_count == 1
    cache_file = tmp_path / "2026-04.json"
    assert cache_file.is_file()


def test_universe_raises_with_clear_message_on_download_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "_UNIVERSE_DIR", tmp_path)
    with patch("pipeline.research.phase_c_backtest.universe._download_mktlots_csv", side_effect=ConnectionError("boom")):
        with pytest.raises(universe.UniverseUnavailable) as exc:
            universe.universe_for_date("2026-04-15")
        assert "2026-04" in str(exc.value)
