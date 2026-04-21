from __future__ import annotations
from unittest.mock import patch
from pipeline.research.phase_c_v5.data_prep import tradeable_indices as ti


def test_check_tradeable_yes_when_derivatives_listed():
    """Simulates a NSE quote response with a non-empty 'info' block for
    BANKNIFTY which implies F&O exists."""
    fake_json = {"info": {"symbol": "BANKNIFTY"},
                 "marketDeptOrderBook": {"carryOfCost": {"price": {}}}}
    with patch.object(ti, "_nse_get", return_value=fake_json):
        assert ti.is_tradeable_index("BANKNIFTY") is True


def test_check_tradeable_no_when_empty_response():
    with patch.object(ti, "_nse_get", return_value={}):
        assert ti.is_tradeable_index("NIFTY_NONSENSE") is False


def test_classify_universe_returns_lists():
    with patch.object(ti, "is_tradeable_index", side_effect=lambda s: s in {"BANKNIFTY", "NIFTY"}):
        tradeable, non_tradeable = ti.classify_universe(
            ["BANKNIFTY", "NIFTY", "NIFTY_MADEUP"])
    assert tradeable == ["BANKNIFTY", "NIFTY"]
    assert non_tradeable == ["NIFTY_MADEUP"]
