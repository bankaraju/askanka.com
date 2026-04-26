# pipeline/tests/test_etf_v3_eval/test_universe_sensitivity_report.py
import pytest

from pipeline.autoresearch.etf_v3_eval.phase_2.universe_sensitivity_report import (
    write_universe_sensitivity_md,
)


def test_write_universe_sensitivity_md(tmp_path):
    rows = [
        {"marker": "zone_gate", "u126_mean_pnl": 0.0030, "u273_mean_pnl": 0.0045,
         "u126_n": 80, "u273_n": 143, "delta_pp": +0.15, "verdict_changed": False},
        {"marker": "sector_overlay", "u126_mean_pnl": 0.0058, "u273_mean_pnl": 0.0061,
         "u126_n": 40, "u273_n": 80, "delta_pp": +0.03, "verdict_changed": False},
    ]
    out = tmp_path / "u.md"
    write_universe_sensitivity_md(rows, out)
    text = out.read_text(encoding="utf-8")
    assert "zone_gate" in text and "Δ pp" in text


def test_write_universe_sensitivity_raises_on_missing_keys(tmp_path):
    rows = [{"marker": "zone_gate"}]  # missing required keys
    with pytest.raises(ValueError, match="missing"):
        write_universe_sensitivity_md(rows, tmp_path / "x.md")


def test_write_universe_sensitivity_handles_empty_rows(tmp_path):
    out = tmp_path / "empty.md"
    write_universe_sensitivity_md([], out)
    text = out.read_text(encoding="utf-8")
    assert "No marker rows supplied" in text
