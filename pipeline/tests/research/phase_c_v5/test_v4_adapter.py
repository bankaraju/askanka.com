"""Tests for v4_adapter: V4 in-sample ledger → V5 signal schema."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.research.phase_c_v5.v4_adapter import (
    V5_SCHEMA_COLS,
    build_v5_signals_from_v4,
    _sector_index,
    _SECTOR_INDEX_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_v4_ledger(tmp_path, rows: list[dict]) -> str:
    p = tmp_path / "in_sample_ledger.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return str(p)


_V4_COLS = [
    "entry_date", "exit_date", "symbol", "side",
    "entry_px", "exit_px", "notional_inr",
    "pnl_gross_inr", "pnl_net_inr", "label",
    "z_score", "expected_return",
]


def _row(symbol="HDFCBANK", side="SHORT", z_score=-2.1, expected_return=-0.001,
         label="OPPORTUNITY"):
    return {
        "entry_date": "2024-10-04",
        "exit_date": "2024-10-07",
        "symbol": symbol,
        "side": side,
        "entry_px": 826.1,
        "exit_px": 808.9,
        "notional_inr": 50_000.0,
        "pnl_gross_inr": 1041.0,
        "pnl_net_inr": 962.0,
        "label": label,
        "z_score": z_score,
        "expected_return": expected_return,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

V5_REQUIRED_COLS = {
    "date", "symbol", "sector", "sector_index",
    "classification", "direction", "expected_return", "confidence",
}


class TestBuildV5SignalsFromV4:
    def test_output_has_v5_schema_columns(self, tmp_path):
        """Single well-known F&O symbol: output must contain all V5 schema cols."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK")])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert V5_REQUIRED_COLS <= set(result.columns), (
            f"Missing columns: {V5_REQUIRED_COLS - set(result.columns)}"
        )

    def test_sector_populated_for_known_symbol(self, tmp_path):
        """HDFCBANK must resolve to sector 'Banks'."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK")])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert result.iloc[0]["sector"] == "Banks"

    def test_sector_index_correct_for_bank(self, tmp_path):
        """HDFCBANK (Banks) should map sector_index=BANKNIFTY."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK")])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert result.iloc[0]["sector_index"] == "BANKNIFTY"

    def test_confidence_scaled_from_z_score(self, tmp_path):
        """confidence = min(|z|/3, 1.0). z=-2.1 → 2.1/3=0.7."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK", z_score=-2.1)])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert abs(result.iloc[0]["confidence"] - 2.1 / 3.0) < 1e-6

    def test_confidence_capped_at_one(self, tmp_path):
        """z=-9.0 → confidence=1.0 (capped)."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK", z_score=-9.0)])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert result.iloc[0]["confidence"] == 1.0

    def test_only_opportunity_rows_kept(self, tmp_path):
        """Non-OPPORTUNITY rows must be filtered out."""
        rows = [_row("HDFCBANK", label="OPPORTUNITY_LAG"), _row("HDFCBANK", label="SETUP")]
        v4_path = _make_v4_ledger(tmp_path, rows)
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert len(result) == 1
        assert result.iloc[0]["classification"] == "OPPORTUNITY_LAG"

    def test_date_is_entry_date_as_timestamp(self, tmp_path):
        """date column must be Timestamp equal to entry_date."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK")])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert result.iloc[0]["date"] == pd.Timestamp("2024-10-04")

    def test_direction_matches_side(self, tmp_path):
        """direction == side from V4 row."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK", side="SHORT")])
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert result.iloc[0]["direction"] == "SHORT"

    def test_unknown_symbol_dropped(self, tmp_path):
        """Symbol not in SectorMapper → dropped. Good symbol kept."""
        rows = [
            _row("HDFCBANK"),
            _row("FAKESYMXYZ"),   # not in F&O universe
        ]
        v4_path = _make_v4_ledger(tmp_path, rows)
        out_path = str(tmp_path / "out.parquet")

        result = build_v5_signals_from_v4(v4_path=v4_path, out_path=out_path)

        assert len(result) == 1
        assert result.iloc[0]["symbol"] == "HDFCBANK"

    def test_missing_v4_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_v5_signals_from_v4(
                v4_path=str(tmp_path / "nonexistent.parquet"),
                out_path=str(tmp_path / "out.parquet"),
            )

    def test_output_file_written(self, tmp_path):
        """build_v5_signals_from_v4 must create the output parquet file."""
        v4_path = _make_v4_ledger(tmp_path, [_row("HDFCBANK")])
        out_path = tmp_path / "out.parquet"

        build_v5_signals_from_v4(v4_path=str(v4_path), out_path=str(out_path))

        assert out_path.is_file()
        reloaded = pd.read_parquet(out_path)
        assert len(reloaded) == 1


class TestSectorIndexMap:
    @pytest.mark.parametrize("sector,expected_index", [
        ("Banks", "BANKNIFTY"),
        ("IT_Services", "NIFTYIT"),
        ("NBFC_HFC", "FINNIFTY"),
        ("Capital_Markets", "FINNIFTY"),
        ("Insurance", "FINNIFTY"),
        ("FMCG", "NIFTY"),           # default
        ("Autos", "NIFTY"),          # default
        ("Power_Utilities", "NIFTY"),  # default
    ])
    def test_sector_to_index(self, sector, expected_index):
        assert _sector_index(sector) == expected_index
