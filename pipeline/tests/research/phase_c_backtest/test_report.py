"""Tests for Phase C validation markdown + chart emitter."""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.research.phase_c_backtest import report


@pytest.fixture
def fake_ledger() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"entry_date": "2026-01-15", "symbol": "A", "side": "LONG", "pnl_net_inr": 100.0},
            {"entry_date": "2026-01-16", "symbol": "B", "side": "SHORT", "pnl_net_inr": -50.0},
            {"entry_date": "2026-01-17", "symbol": "C", "side": "LONG", "pnl_net_inr": 200.0},
        ]
    )


def test_render_pnl_table_writes_markdown(tmp_path, fake_ledger):
    out_path = tmp_path / "pnl.md"
    report.render_pnl_table(fake_ledger, out_path, title="Test Ledger")
    text = out_path.read_text(encoding="utf-8")
    assert "## Test Ledger" in text
    assert "| symbol" in text
    # total = 100 - 50 + 200 = 250
    assert "\u20b9250.00" in text or "250.00" in text


def test_render_equity_curve_writes_png(tmp_path, fake_ledger):
    out_path = tmp_path / "equity.png"
    report.render_equity_curve(fake_ledger, out_path)
    assert out_path.is_file()
    # PNG magic bytes — catches corrupt files that st.st_size > 1000 would miss
    assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_verdict_section_includes_pass_fail(tmp_path):
    out_path = tmp_path / "verdict.md"
    verdicts = {
        "H1_OPPORTUNITY": {
            "passes": True, "reason": "all criteria met", "failed_criteria": [],
            "hit_rate": 0.58, "p_value": 0.002,
        },
        "H2_POSSIBLE_OPPORTUNITY": {
            "passes": False, "reason": "p=0.12 alpha=0.01",
            "failed_criteria": ["p > alpha", "hit_rate < 0.53"],
            "hit_rate": 0.51, "p_value": 0.12,
        },
    }
    report.render_verdict_section(verdicts, out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "H1_OPPORTUNITY" in text
    assert "H2_POSSIBLE_OPPORTUNITY" in text
    assert "PASS" in text
    assert "FAIL" in text
    # New assertions: p-value and hit-rate must appear
    assert "58.0%" in text or "58%" in text  # H1 hit rate
    assert "0.0020" in text or "0.002" in text  # H1 p-value
    # Failed criteria detail section for H2
    assert "p > alpha" in text


def test_render_regime_breakdown_groups_by_regime(tmp_path, fake_ledger):
    out_path = tmp_path / "regime.md"
    regime_by_date = {
        "2026-01-15": "NEUTRAL",
        "2026-01-16": "NEUTRAL",
        "2026-01-17": "EUPHORIA",
    }
    report.render_regime_breakdown(fake_ledger, regime_by_date, out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "NEUTRAL" in text
    assert "EUPHORIA" in text
    assert "Per-regime breakdown" in text


def test_render_pnl_table_handles_empty_ledger(tmp_path):
    empty = pd.DataFrame(columns=["entry_date", "symbol", "side", "pnl_net_inr"])
    out_path = tmp_path / "pnl_empty.md"
    report.render_pnl_table(empty, out_path, title="Empty")
    text = out_path.read_text(encoding="utf-8")
    assert "## Empty" in text
    assert "N trades" in text and "0" in text


def test_render_equity_curve_handles_empty_ledger(tmp_path):
    empty = pd.DataFrame(columns=["entry_date", "pnl_net_inr"])
    out_path = tmp_path / "equity_empty.png"
    report.render_equity_curve(empty, out_path)
    assert out_path.is_file()
    assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG magic


def test_render_regime_breakdown_handles_empty_ledger(tmp_path):
    empty = pd.DataFrame(columns=["entry_date", "pnl_net_inr"])
    out_path = tmp_path / "regime_empty.md"
    report.render_regime_breakdown(empty, {}, out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "Per-regime breakdown" in text
