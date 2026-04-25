"""TDD for report — engine attribution + sanity checks + trader one-pager."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import report


def _synth_trades(n_per_engine: int = 5) -> pd.DataFrame:
    rows = []
    for engine in ["phase_c", "phase_b", "spread"]:
        for i in range(n_per_engine):
            rows.append({
                "signal_id": f"{engine}-{i}",
                "ticker": f"TKR{i}",
                "date": pd.Timestamp("2026-03-10") + pd.Timedelta(days=i),
                "source": "actual" if i == 0 else "missed",
                "regime": ["NEUTRAL", "RISK-ON", "RISK-OFF"][i % 3],
                "engine": engine,
                "side": "LONG" if i % 2 == 0 else "SHORT",
                "exit_reason": ["TIME_STOP", "ATR_STOP", "TRAIL", "Z_CROSS", "TIME_STOP"][i % 5],
                "pnl_pct": [+1.5, -3.2, +2.0, -0.5, +0.8][i % 5],
                "mfe_pct": [+1.5, +0.5, +3.0, +1.2, +1.0][i % 5],
                "actual_pnl_pct": 1.0 if i == 0 else None,
            })
    return pd.DataFrame(rows)


def test_per_engine_summary_has_required_keys():
    trades = _synth_trades()
    summary = report.build_engine_summary(trades)
    for engine in ["phase_c", "phase_b", "spread"]:
        assert engine in summary
        e = summary[engine]
        assert {"n", "hit_rate", "mean_pnl_pct", "total_pnl_pct", "exit_reasons"}.issubset(e.keys())
        assert e["n"] == 5
        assert isinstance(e["exit_reasons"], dict)


def test_per_engine_summary_math():
    trades = _synth_trades(n_per_engine=5)
    summary = report.build_engine_summary(trades)
    pc = summary["phase_c"]
    # Hit-rate = fraction of pnl_pct > 0 → 3 winners (1.5, 2.0, 0.8) of 5 = 0.6
    assert pc["hit_rate"] == pytest.approx(0.6, abs=0.001)
    # Mean ≈ (1.5 - 3.2 + 2.0 - 0.5 + 0.8)/5 = 0.12
    assert pc["mean_pnl_pct"] == pytest.approx(0.12, abs=0.001)
    # Total = sum
    assert pc["total_pnl_pct"] == pytest.approx(0.6, abs=0.001)


def test_regime_cube():
    trades = _synth_trades(n_per_engine=5)
    cube = report.build_regime_cube(trades)
    # MultiIndex (engine, regime); each cell has at least n + total_pnl_pct
    assert cube.index.nlevels == 2
    assert "n" in cube.columns
    assert "total_pnl_pct" in cube.columns
    # 3 engines × 3 regimes = 9 rows max (assuming each combo present)
    assert len(cube) == 9


def test_sanity_checks_coverage_pass():
    trades = _synth_trades()
    universe_signal_count = len(trades)  # 100% covered
    checks = report.run_sanity_checks(
        trades=trades,
        total_signals_in_window=universe_signal_count,
        coverage_threshold_pct=95.0,
    )
    assert checks["coverage"]["pass"] is True
    assert checks["coverage"]["coverage_pct"] == pytest.approx(100.0)


def test_sanity_checks_coverage_fail():
    trades = _synth_trades()
    # Pretend 100 signals but we only processed len(trades) → coverage well below 95%
    checks = report.run_sanity_checks(
        trades=trades,
        total_signals_in_window=100,
        coverage_threshold_pct=95.0,
    )
    assert checks["coverage"]["pass"] is False


def test_sanity_checks_live_cross_check_within_tolerance():
    """Replay vs live: agreement within ±2pp on ≥80% of overlap rows."""
    rows = []
    # 10 actual rows, 9 within 2pp → 90% agreement, passes
    for i in range(10):
        replay_pnl = 1.0
        live_pnl = 1.0 if i < 9 else 5.0  # last row off by 4pp
        rows.append({
            "signal_id": f"sig-{i}",
            "ticker": f"T{i}",
            "date": pd.Timestamp("2026-03-10"),
            "source": "actual",
            "regime": "NEUTRAL",
            "engine": "phase_c",
            "side": "LONG",
            "exit_reason": "TIME_STOP",
            "pnl_pct": replay_pnl,
            "mfe_pct": replay_pnl,
            "actual_pnl_pct": live_pnl,
        })
    trades = pd.DataFrame(rows)
    checks = report.run_sanity_checks(
        trades=trades,
        total_signals_in_window=len(trades),
        coverage_threshold_pct=95.0,
    )
    assert checks["live_cross_check"]["agree_pct"] == pytest.approx(90.0, abs=0.01)
    assert checks["live_cross_check"]["pass"] is True


def test_write_engine_summary_json(tmp_path: Path):
    trades = _synth_trades()
    summary = report.build_engine_summary(trades)
    out = tmp_path / "engine_summary.json"
    report.write_engine_summary(summary, out)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "phase_c" in loaded
    assert "phase_b" in loaded
    assert "spread" in loaded


def test_write_one_pager_markdown(tmp_path: Path):
    trades = _synth_trades()
    summary = report.build_engine_summary(trades)
    cube = report.build_regime_cube(trades)
    checks = report.run_sanity_checks(
        trades=trades,
        total_signals_in_window=len(trades),
        coverage_threshold_pct=95.0,
    )
    out = tmp_path / "replay.md"
    report.write_one_pager(
        summary=summary,
        cube=cube,
        checks=checks,
        trades=trades,
        window_start=pd.Timestamp("2026-02-21"),
        window_end=pd.Timestamp("2026-04-22"),
        out_path=out,
    )
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Mechanical 60-Day Replay" in text
    # Required sections
    for section in ["Per-Engine", "Regime", "Sanity"]:
        assert section in text
