"""Tests for etf_reoptimize.load_indian_data() — Indian market data loader."""

import json
import sys
from pathlib import Path

# Ensure pipeline/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_indian_data_returns_dict(tmp_path):
    """load_indian_data() returns a dict with fii_net, india_vix, nifty_close
    populated from minimal daily + flows JSON fixtures."""
    from autoresearch.etf_reoptimize import load_indian_data

    # --- build daily fixture ---
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    daily_payload = {
        "date": "2026-04-17",
        "indices": {
            "Nifty 50": {"close": 24353.55},
            "INDIA VIX": {"close": 17.205},
        },
        "volatility": {},
        "stocks": {},
        "fx": {},
        "commodities": {},
        "sector_etfs": {},
    }
    (daily_dir / "2026-04-17.json").write_text(json.dumps(daily_payload))

    # --- build flows fixture ---
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    flows_payload = {
        "date": "17-Apr-2026",
        "fii_equity_net": 683.2,
        "dii_equity_net": -4721.48,
        "source": "nse_fiidiiTradeReact",
    }
    (flows_dir / "2026-04-17.json").write_text(json.dumps(flows_payload))

    result = load_indian_data(daily_dir=daily_dir, flows_dir=flows_dir)

    assert isinstance(result, dict), "load_indian_data() must return a dict"
    assert "fii_net" in result, "Result must contain 'fii_net'"
    assert "india_vix" in result, "Result must contain 'india_vix'"
    assert "nifty_close" in result, "Result must contain 'nifty_close'"

    assert result["fii_net"] == 683.2
    assert result["india_vix"] == 17.205
    assert result["nifty_close"] == 24353.55
    assert result["dii_net"] == -4721.48


def test_load_indian_data_handles_missing_files(tmp_path):
    """load_indian_data() returns a dict with None values when dirs are empty."""
    from autoresearch.etf_reoptimize import load_indian_data

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()
    positioning_path = tmp_path / "positioning.json"
    # positioning.json intentionally absent

    result = load_indian_data(
        daily_dir=daily_dir,
        flows_dir=flows_dir,
        positioning_path=positioning_path,
    )

    assert isinstance(result, dict), "load_indian_data() must return a dict"
    for key in ("fii_net", "india_vix", "nifty_close"):
        assert key in result, f"Result must contain '{key}'"
        assert result[key] is None, f"'{key}' should be None when files are missing"
