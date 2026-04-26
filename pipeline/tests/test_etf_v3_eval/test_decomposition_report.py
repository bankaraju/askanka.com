# pipeline/tests/test_etf_v3_eval/test_decomposition_report.py
from pathlib import Path

import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.decomposition_report import (
    write_markers_decomposition_md,
)


def test_write_markers_decomposition_md_emits_table_per_marker(tmp_path):
    rows = [
        {"marker": "zone_gate", "n_trades": 120, "mean_pnl": 0.0042,
         "se": 0.0008, "p_perm": 0.012, "fragility": "stable",
         "incremental_pnl": 0.0042, "naive_random_p": 0.005},
        {"marker": "sector_overlay", "n_trades": 80, "mean_pnl": 0.0061,
         "se": 0.0011, "p_perm": 0.034, "fragility": "stable",
         "incremental_pnl": 0.0019, "naive_random_p": 0.014},
    ]
    out = tmp_path / "m.md"
    write_markers_decomposition_md(rows, out)
    text = out.read_text(encoding="utf-8")
    assert "zone_gate" in text and "sector_overlay" in text
    assert "Mean P&L" in text
    assert "Fragility" in text


def test_write_markers_decomposition_raises_on_missing_keys(tmp_path):
    rows = [{"marker": "zone_gate"}]  # missing required keys
    with pytest.raises(ValueError, match="missing"):
        write_markers_decomposition_md(rows, tmp_path / "x.md")


def test_write_markers_decomposition_handles_empty_rows(tmp_path):
    out = tmp_path / "empty.md"
    write_markers_decomposition_md([], out)
    text = out.read_text(encoding="utf-8")
    assert "No marker rows supplied" in text
