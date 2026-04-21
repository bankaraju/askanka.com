from __future__ import annotations
import json
from pipeline.research.phase_c_v5.data_prep import concentration as c


def test_load_concentration_returns_all_known_indices(tmp_path):
    stub = {
        "BANKNIFTY": {
            "constituents": [{"symbol": "HDFCBANK", "weight": 0.28}],
            "top_n_threshold": 0.70,
        }
    }
    f = tmp_path / "sector_concentration.json"
    f.write_text(json.dumps(stub))
    loaded = c.load_concentration(f)
    assert "BANKNIFTY" in loaded
    assert loaded["BANKNIFTY"]["constituents"][0]["symbol"] == "HDFCBANK"


def test_top_n_constituents_returns_sorted_by_weight():
    data = {
        "BANKNIFTY": {
            "constituents": [
                {"symbol": "SBIN", "weight": 0.10},
                {"symbol": "HDFCBANK", "weight": 0.28},
                {"symbol": "ICICIBANK", "weight": 0.24},
            ],
            "top_n_threshold": 0.70,
        }
    }
    top = c.top_n_constituents(data, "BANKNIFTY", n=2)
    assert [t["symbol"] for t in top] == ["HDFCBANK", "ICICIBANK"]


def test_stock_in_top_weight_bucket():
    data = {
        "BANKNIFTY": {
            "constituents": [
                {"symbol": "HDFCBANK", "weight": 0.28},
                {"symbol": "ICICIBANK", "weight": 0.24},
                {"symbol": "SBIN", "weight": 0.10},
                {"symbol": "AXISBANK", "weight": 0.08},
            ],
            "top_n_threshold": 0.70,
        }
    }
    # Cumulative weight to reach 70%: HDFCBANK (28) + ICICIBANK (52) + SBIN (62) + AXISBANK (70) = 4 symbols
    assert c.is_in_top_bucket(data, "BANKNIFTY", "HDFCBANK") is True
    assert c.is_in_top_bucket(data, "BANKNIFTY", "AXISBANK") is True
    assert c.is_in_top_bucket(data, "BANKNIFTY", "KOTAKBANK") is False  # not in the list
