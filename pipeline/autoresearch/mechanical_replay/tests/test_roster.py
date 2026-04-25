"""TDD for roster — Phase C signal universe joined to closed_signals over a window."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay import roster, canonical_loader, constants as C


@pytest.fixture(scope="module")
def loader():
    return canonical_loader.CanonicalLoader()


@pytest.fixture
def synth_break_history(tmp_path: Path) -> Path:
    rows = [
        # In window, in canonical, LAG → actionable
        {"date": "2026-03-10", "symbol": "ABB", "classification": "OPPORTUNITY_LAG",
         "regime": "RISK-OFF", "z_score": -3.2, "trade_rec": "LONG",
         "event_geometry": "LAG", "direction_tested": "FOLLOW"},
        # In window, legacy OPPORTUNITY → actionable
        {"date": "2026-03-15", "symbol": "RELIANCE", "classification": "OPPORTUNITY",
         "regime": "NEUTRAL", "z_score": 3.5, "trade_rec": "SHORT",
         "event_geometry": "OVERSHOOT", "direction_tested": "FADE"},
        # POSSIBLE_OPPORTUNITY (no rec)
        {"date": "2026-03-20", "symbol": "TCS", "classification": "POSSIBLE_OPPORTUNITY",
         "regime": "EUPHORIA", "z_score": -2.8, "trade_rec": None,
         "event_geometry": "OVERSHOOT", "direction_tested": None},
        # Out of window
        {"date": "2025-12-01", "symbol": "ABB", "classification": "OPPORTUNITY_LAG",
         "regime": "RISK-OFF", "z_score": -3.0, "trade_rec": "LONG"},
        # Not in canonical
        {"date": "2026-03-12", "symbol": "NOTATICKER", "classification": "OPPORTUNITY_LAG",
         "regime": "RISK-OFF", "z_score": -3.0, "trade_rec": "LONG"},
        # WARNING — not actionable
        {"date": "2026-03-13", "symbol": "ABB", "classification": "WARNING",
         "regime": "RISK-OFF", "z_score": -2.0, "trade_rec": None},
    ]
    p = tmp_path / "break_history.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


@pytest.fixture
def synth_closed_signals(tmp_path: Path) -> Path:
    rows = [
        # ABB 2026-03-10 — actually closed Phase C trade
        {
            "signal_id": "BRK-2026-03-10-ABB",
            "category": "phase_c",
            "open_timestamp": "2026-03-10 09:42:00",
            "close_timestamp": "2026-03-10 14:30:00",
            "_break_metadata": {"symbol": "ABB", "classification": "OPPORTUNITY_LAG"},
            "final_pnl": {"spread_pnl_pct": 2.5, "long_legs": [{"ticker": "ABB"}]},
        },
        # RELIANCE 2026-03-15 — actually closed
        {
            "signal_id": "BRK-2026-03-15-RELIANCE",
            "category": "phase_c",
            "open_timestamp": "2026-03-15 10:15:00",
            "close_timestamp": "2026-03-15 14:30:00",
            "_break_metadata": {"symbol": "RELIANCE", "classification": "OPPORTUNITY"},
            "final_pnl": {"spread_pnl_pct": -1.2, "short_legs": [{"ticker": "RELIANCE"}]},
        },
        # Different category — not Phase C
        {
            "signal_id": "SPRD-2026-03-12",
            "category": "spread",
            "open_timestamp": "2026-03-12 09:30:00",
            "close_timestamp": "2026-03-13 10:00:00",
            "final_pnl": {"spread_pnl_pct": 1.0},
        },
    ]
    p = tmp_path / "closed_signals.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def test_roster_filters_window_canonical_actionable(loader, synth_break_history, synth_closed_signals):
    df = roster.build_phase_c_roster(
        loader=loader,
        break_history_path=synth_break_history,
        closed_path=synth_closed_signals,
        window_start=pd.Timestamp("2026-02-21"),
        window_end=pd.Timestamp("2026-04-22"),
    )
    # Out-of-window dropped, NOTATICKER dropped, WARNING dropped → 3 rows
    assert len(df) == 3
    tickers = set(df["ticker"].tolist())
    assert tickers == {"ABB", "RELIANCE", "TCS"}


def test_roster_marks_actual_vs_missed(loader, synth_break_history, synth_closed_signals):
    df = roster.build_phase_c_roster(
        loader=loader,
        break_history_path=synth_break_history,
        closed_path=synth_closed_signals,
        window_start=pd.Timestamp("2026-02-21"),
        window_end=pd.Timestamp("2026-04-22"),
    )
    by_t = df.set_index("ticker")
    assert by_t.loc["ABB", "source"] == "actual"
    assert by_t.loc["RELIANCE", "source"] == "actual"
    assert by_t.loc["TCS", "source"] == "missed"
    # Actual closed trades carry the live realized P&L for cross-check
    assert by_t.loc["ABB", "actual_pnl_pct"] == 2.5
    assert by_t.loc["RELIANCE", "actual_pnl_pct"] == -1.2
    assert pd.isna(by_t.loc["TCS", "actual_pnl_pct"])


def test_roster_derives_side(loader, synth_break_history, synth_closed_signals):
    df = roster.build_phase_c_roster(
        loader=loader,
        break_history_path=synth_break_history,
        closed_path=synth_closed_signals,
        window_start=pd.Timestamp("2026-02-21"),
        window_end=pd.Timestamp("2026-04-22"),
    )
    by_t = df.set_index("ticker")
    assert by_t.loc["ABB", "side"] == "LONG"
    assert by_t.loc["RELIANCE", "side"] == "SHORT"
    # POSSIBLE_OPPORTUNITY without rec → side is None
    assert pd.isna(by_t.loc["TCS", "side"]) or by_t.loc["TCS", "side"] is None


def test_roster_real_data_window(loader):
    """Smoke test against real correlation_break_history.json + closed_signals.json.

    Data reality (verified 2026-04-25): all 36 phase_c closed trades in
    closed_signals.json fall in 2026-04-20..2026-04-24 — the live Phase C
    engine has only been firing actionable trades for ~5 days, not 60.
    Of those 36, the canonical 154-ticker universe excludes a few names
    (e.g., PATANJALI, YESBANK), leaving ~5 actuals + ~19 missed = ~24 rows
    surviving filters. The window below intentionally reaches forward to
    2026-04-24 to cover them.
    """
    df = roster.build_phase_c_roster(
        loader=loader,
        window_start=pd.Timestamp("2026-02-24"),
        window_end=pd.Timestamp("2026-04-24"),
    )
    assert not df.empty
    n_actual = (df["source"] == "actual").sum()
    assert n_actual >= 3, f"expected ≥3 canonical actual phase_c trades in window, got {n_actual}"
    # All tickers must be in canonical 154
    assert set(df["ticker"]).issubset(loader.universe)
