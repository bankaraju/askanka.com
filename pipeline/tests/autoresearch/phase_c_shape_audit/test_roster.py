"""Roster TDD — fixtures-only, no live data."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.autoresearch.phase_c_shape_audit import roster


def _write_history_fixture(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


def _write_closed_fixture(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


def _write_regime_fixture(path: Path, rows: list[tuple[str, str]]) -> None:
    df = pd.DataFrame(rows, columns=["date", "regime_zone"])
    df["signal_score"] = 0.0
    df.to_csv(path, index=False)


def test_build_roster_unions_actual_and_missed(tmp_path: Path) -> None:
    hist = [
        {
            "symbol": "TICKERA", "date": "2026-04-22", "time": "09:42:01",
            "classification": "OPPORTUNITY_LAG", "trade_rec": "SHORT",
            "z_score": -3.2, "expected_return": -0.4, "actual_return": 1.6,
            "regime": "RISK-OFF", "pcr": 0.85, "pcr_class": "MILD_BEAR",
            "oi_anomaly": False,
        },
        {
            "symbol": "TICKERB", "date": "2026-04-22", "time": "11:15:00",
            "classification": "OPPORTUNITY_LAG", "trade_rec": "LONG",
            "z_score": 2.8, "expected_return": 0.6, "actual_return": -0.8,
            "regime": "RISK-OFF", "pcr": 1.2, "pcr_class": "MILD_BULL",
            "oi_anomaly": False,
        },
    ]
    closed = [
        {
            "signal_id": "BRK-2026-04-22-TICKERA",
            "category": "phase_c",
            "open_timestamp": "2026-04-22 09:42:30",
            "close_timestamp": "2026-04-23T06:12:00",
            "long_legs": [],
            "short_legs": [{"ticker": "TICKERA", "weight": 1.0}],
            "final_pnl": {"spread_pnl_pct": 1.85, "long_pnl_pct": 0.0,
                          "short_pnl_pct": 1.85, "long_legs": [], "short_legs": []},
            "_break_metadata": {"symbol": "TICKERA", "regime": "RISK-OFF",
                                 "classification": "OPPORTUNITY_LAG", "z_score": -3.2,
                                 "oi_anomaly": False},
        },
    ]
    regime = [("2026-04-22", "RISK-OFF")]

    hist_path = tmp_path / "hist.json"
    closed_path = tmp_path / "closed.json"
    regime_path = tmp_path / "regime.csv"
    _write_history_fixture(hist_path, hist)
    _write_closed_fixture(closed_path, closed)
    _write_regime_fixture(regime_path, regime)

    df = roster.build_roster(
        history_path=hist_path,
        closed_path=closed_path,
        regime_path=regime_path,
        window_start=pd.Timestamp("2026-04-21"),
        window_end=pd.Timestamp("2026-04-25"),
    )

    assert len(df) == 2
    sources = sorted(df["source"].tolist())
    assert sources == ["actual", "missed"]

    actual_row = df[df["source"] == "actual"].iloc[0]
    assert actual_row["ticker"] == "TICKERA"
    assert actual_row["actual_pnl_pct"] == pytest.approx(1.85)
    assert actual_row["trade_rec"] == "SHORT"
    assert actual_row["regime"] == "RISK-OFF"

    missed_row = df[df["source"] == "missed"].iloc[0]
    assert missed_row["ticker"] == "TICKERB"
    assert pd.isna(missed_row["actual_pnl_pct"])
    assert missed_row["signal_id"].startswith("MISSED-")


def test_build_roster_dedupes_intra_day_by_max_abs_z(tmp_path: Path) -> None:
    """Multiple history rows for same (ticker, date, classification)
    collapse to the row with max |z_score|."""
    hist = [
        {
            "symbol": "TICKERX", "date": "2026-04-22", "time": "10:00",
            "classification": "OPPORTUNITY_LAG", "trade_rec": "SHORT",
            "z_score": -2.0, "expected_return": -0.3, "actual_return": 0.9,
            "regime": "NEUTRAL", "pcr": None, "pcr_class": "NEUTRAL",
            "oi_anomaly": False,
        },
        {
            "symbol": "TICKERX", "date": "2026-04-22", "time": "13:00",
            "classification": "OPPORTUNITY_LAG", "trade_rec": "SHORT",
            "z_score": -3.5, "expected_return": -0.3, "actual_return": 1.6,
            "regime": "NEUTRAL", "pcr": None, "pcr_class": "NEUTRAL",
            "oi_anomaly": False,
        },
    ]
    hist_path = tmp_path / "hist.json"
    closed_path = tmp_path / "closed.json"
    regime_path = tmp_path / "regime.csv"
    _write_history_fixture(hist_path, hist)
    _write_closed_fixture(closed_path, [])
    _write_regime_fixture(regime_path, [("2026-04-22", "NEUTRAL")])

    df = roster.build_roster(
        history_path=hist_path,
        closed_path=closed_path,
        regime_path=regime_path,
        window_start=pd.Timestamp("2026-04-21"),
        window_end=pd.Timestamp("2026-04-25"),
    )

    assert len(df) == 1
    assert df.iloc[0]["z_score"] == pytest.approx(-3.5)
