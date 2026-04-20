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
    assert out_path.stat().st_size > 1000  # non-empty PNG


def test_render_verdict_section_includes_pass_fail(tmp_path):
    out_path = tmp_path / "verdict.md"
    verdicts = {
        "H1_OPPORTUNITY": {
            "passes": True,
            "reason": "all criteria met",
            "failed_criteria": [],
        },
        "H2_POSSIBLE_OPPORTUNITY": {
            "passes": False,
            "reason": "p=0.12 alpha=0.01",
            "hit_rate": 0.51,
            "p_value": 0.12,
        },
    }
    report.render_verdict_section(verdicts, out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "H1_OPPORTUNITY" in text
    assert "PASS" in text or "Pass" in text
    assert "H2_POSSIBLE_OPPORTUNITY" in text
    assert "FAIL" in text or "Fail" in text


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
