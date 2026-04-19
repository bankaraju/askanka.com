"""
Tests for pipeline/atm_premium_capture.py — live ATM premium snapshots.

Run: pytest pipeline/tests/test_atm_premium_capture.py -v
"""
import pytest
import csv
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_INSTRUMENTS = [
    {"instrument_token": "1001", "exchange_token": "100", "tradingsymbol": "HAL26APR4300CE",
     "name": "HAL", "last_price": "0", "expiry": "2026-04-28", "strike": "4300",
     "tick_size": "0.05", "lot_size": "150", "instrument_type": "CE",
     "segment": "NFO-OPT", "exchange": "NFO"},
    {"instrument_token": "1002", "exchange_token": "101", "tradingsymbol": "HAL26APR4300PE",
     "name": "HAL", "last_price": "0", "expiry": "2026-04-28", "strike": "4300",
     "tick_size": "0.05", "lot_size": "150", "instrument_type": "PE",
     "segment": "NFO-OPT", "exchange": "NFO"},
    {"instrument_token": "1003", "exchange_token": "102", "tradingsymbol": "HAL26APR4200CE",
     "name": "HAL", "last_price": "0", "expiry": "2026-04-28", "strike": "4200",
     "tick_size": "0.05", "lot_size": "150", "instrument_type": "CE",
     "segment": "NFO-OPT", "exchange": "NFO"},
    {"instrument_token": "1004", "exchange_token": "103", "tradingsymbol": "HAL26APR4200PE",
     "name": "HAL", "last_price": "0", "expiry": "2026-04-28", "strike": "4200",
     "tick_size": "0.05", "lot_size": "150", "instrument_type": "PE",
     "segment": "NFO-OPT", "exchange": "NFO"},
]


def _write_nfo_csv(path: Path, rows: list[dict]):
    fields = ["instrument_token", "exchange_token", "tradingsymbol", "name",
              "last_price", "expiry", "strike", "tick_size", "lot_size",
              "instrument_type", "segment", "exchange"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


class TestFindNearestATM:
    def test_picks_closest_strike(self):
        from pipeline.atm_premium_capture import find_nearest_atm
        strikes = [4100, 4200, 4300, 4400]
        assert find_nearest_atm(4285.0, strikes) == 4300
        assert find_nearest_atm(4240.0, strikes) == 4200
        assert find_nearest_atm(4250.0, strikes) == 4200

    def test_empty_strikes(self):
        from pipeline.atm_premium_capture import find_nearest_atm
        assert find_nearest_atm(4285.0, []) is None


class TestLoadInstruments:
    def test_groups_by_stock_and_expiry(self):
        from pipeline.atm_premium_capture import load_nfo_instruments
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "instruments_nfo.csv"
            _write_nfo_csv(csv_path, SAMPLE_INSTRUMENTS)
            result = load_nfo_instruments(csv_path)
            assert "HAL" in result
            hal = result["HAL"]
            assert hal["expiry"] == "2026-04-28"
            assert 4300 in hal["strikes"]
            assert 4200 in hal["strikes"]

    def test_skips_non_nfo_opt_rows(self):
        """Rows with segment != NFO-OPT must be excluded."""
        from pipeline.atm_premium_capture import load_nfo_instruments
        extra = [
            {"instrument_token": "9001", "exchange_token": "900",
             "tradingsymbol": "HAL26APRFUT", "name": "HAL", "last_price": "0",
             "expiry": "2026-04-28", "strike": "0", "tick_size": "0.05",
             "lot_size": "150", "instrument_type": "FUT",
             "segment": "NFO-FUT", "exchange": "NFO"},
        ]
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "instruments_nfo.csv"
            _write_nfo_csv(csv_path, SAMPLE_INSTRUMENTS + extra)
            result = load_nfo_instruments(csv_path)
            # 9001 (FUT) should not appear as a strike
            hal = result.get("HAL", {})
            for strike_data in hal.get("strikes", {}).values():
                assert "FUT" not in strike_data

    def test_nearest_expiry_selected(self):
        """When multiple expiries exist, only the nearest future one is kept."""
        from pipeline.atm_premium_capture import load_nfo_instruments
        near = [
            {"instrument_token": "2001", "exchange_token": "200",
             "tradingsymbol": "HAL26APR4300CE", "name": "HAL", "last_price": "0",
             "expiry": "2026-04-28", "strike": "4300", "tick_size": "0.05",
             "lot_size": "150", "instrument_type": "CE",
             "segment": "NFO-OPT", "exchange": "NFO"},
            {"instrument_token": "2002", "exchange_token": "201",
             "tradingsymbol": "HAL26APR4300PE", "name": "HAL", "last_price": "0",
             "expiry": "2026-04-28", "strike": "4300", "tick_size": "0.05",
             "lot_size": "150", "instrument_type": "PE",
             "segment": "NFO-OPT", "exchange": "NFO"},
        ]
        far = [
            {"instrument_token": "3001", "exchange_token": "300",
             "tradingsymbol": "HAL26MAY4300CE", "name": "HAL", "last_price": "0",
             "expiry": "2026-05-28", "strike": "4300", "tick_size": "0.05",
             "lot_size": "150", "instrument_type": "CE",
             "segment": "NFO-OPT", "exchange": "NFO"},
            {"instrument_token": "3002", "exchange_token": "301",
             "tradingsymbol": "HAL26MAY4300PE", "name": "HAL", "last_price": "0",
             "expiry": "2026-05-28", "strike": "4300", "tick_size": "0.05",
             "lot_size": "150", "instrument_type": "PE",
             "segment": "NFO-OPT", "exchange": "NFO"},
        ]
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "instruments_nfo.csv"
            _write_nfo_csv(csv_path, near + far)
            result = load_nfo_instruments(csv_path)
            assert result["HAL"]["expiry"] == "2026-04-28"

    def test_ce_and_pe_tokens_stored(self):
        from pipeline.atm_premium_capture import load_nfo_instruments
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "instruments_nfo.csv"
            _write_nfo_csv(csv_path, SAMPLE_INSTRUMENTS)
            result = load_nfo_instruments(csv_path)
            strike_4300 = result["HAL"]["strikes"][4300]
            assert "CE" in strike_4300
            assert "PE" in strike_4300
            assert strike_4300["CE"]["token"] == 1001
            assert strike_4300["PE"]["token"] == 1002
            assert strike_4300["CE"]["symbol"] == "HAL26APR4300CE"


class TestComputeComparison:
    def test_error_pct_calculation(self):
        from pipeline.atm_premium_capture import compute_comparison
        result = compute_comparison(
            spot=4285.0, atm_strike=4300, real_call=89.5, real_put=104.2,
            ewma_vol=0.312, days_to_expiry=9, vol_scalar=1.0,
        )
        assert "synthetic_straddle" in result
        assert "real_straddle" in result
        assert "error_pct" in result
        assert abs(result["real_straddle"] - 193.7) < 0.01

    def test_vol_scalar_applied(self):
        from pipeline.atm_premium_capture import compute_comparison
        no_scalar = compute_comparison(
            spot=4285.0, atm_strike=4300, real_call=89.5, real_put=104.2,
            ewma_vol=0.312, days_to_expiry=9, vol_scalar=1.0,
        )
        with_scalar = compute_comparison(
            spot=4285.0, atm_strike=4300, real_call=89.5, real_put=104.2,
            ewma_vol=0.312, days_to_expiry=9, vol_scalar=0.88,
        )
        assert with_scalar["synthetic_straddle"] < no_scalar["synthetic_straddle"]

    def test_all_keys_present(self):
        from pipeline.atm_premium_capture import compute_comparison
        result = compute_comparison(
            spot=4285.0, atm_strike=4300, real_call=89.5, real_put=104.2,
            ewma_vol=0.312, days_to_expiry=9, vol_scalar=1.0,
        )
        for key in ("real_call", "real_put", "real_straddle",
                    "synthetic_call", "synthetic_put", "synthetic_straddle", "error_pct"):
            assert key in result, f"Missing key: {key}"

    def test_zero_days_uses_intrinsic(self):
        """days_to_expiry=0 should not crash (clamped to 1)."""
        from pipeline.atm_premium_capture import compute_comparison
        result = compute_comparison(
            spot=100.0, atm_strike=100.0, real_call=2.0, real_put=2.0,
            ewma_vol=0.25, days_to_expiry=0, vol_scalar=1.0,
        )
        assert result["real_straddle"] == 4.0
        assert isinstance(result["error_pct"], float)

    def test_real_straddle_equals_sum_of_legs(self):
        from pipeline.atm_premium_capture import compute_comparison
        result = compute_comparison(
            spot=500.0, atm_strike=500.0, real_call=12.0, real_put=11.5,
            ewma_vol=0.20, days_to_expiry=5, vol_scalar=1.0,
        )
        assert abs(result["real_straddle"] - 23.5) < 1e-6

    def test_error_pct_sign(self):
        """When real premium > synthetic, error_pct should be positive."""
        from pipeline.atm_premium_capture import compute_comparison
        result = compute_comparison(
            spot=4285.0, atm_strike=4300, real_call=200.0, real_put=200.0,
            ewma_vol=0.312, days_to_expiry=9, vol_scalar=1.0,
        )
        assert result["error_pct"] > 0
