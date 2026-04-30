"""Tests for pipeline.research.h_2026_04_30_pdr_bnk_nbfc.

Spec: docs/superpowers/specs/2026-04-30-pdr-banks-nbfc-design.md
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline.research.h_2026_04_30_pdr_bnk_nbfc import divergence as dv
from pipeline.research.h_2026_04_30_pdr_bnk_nbfc import forward_shadow as fs
from pipeline.research.h_2026_04_30_pdr_bnk_nbfc import liquidity as lq


# ---- liquidity ranking ---------------------------------------------------

def _write_fno_csv(path: Path, days: int, vol: float, close: float) -> None:
    """Write a fake fno_historical CSV with constant Volume*Close."""
    base = pd.Timestamp("2026-04-01")
    rows = []
    for i in range(days):
        d = base + pd.Timedelta(days=i)
        rows.append({"Date": d.strftime("%Y-%m-%d"),
                     "Close": close, "High": close, "Low": close,
                     "Open": close, "Volume": vol})
    pd.DataFrame(rows).to_csv(path, index=False)


def test_liquidity_picks_top_n(tmp_path: Path):
    sector_map = {"AAA": "Banks", "BBB": "Banks", "CCC": "Banks", "DDD": "NBFC_HFC"}
    universe = ["AAA", "BBB", "CCC", "DDD"]
    _write_fno_csv(tmp_path / "AAA.csv", days=80, vol=1_000_000, close=100.0)
    _write_fno_csv(tmp_path / "BBB.csv", days=80, vol=2_000_000, close=200.0)  # highest tv
    _write_fno_csv(tmp_path / "CCC.csv", days=80, vol=500_000, close=50.0)
    _write_fno_csv(tmp_path / "DDD.csv", days=80, vol=1_000_000, close=300.0)

    picks = lq.top_n_by_traded_value(
        sector_target="Banks", sector_map=sector_map,
        fno_hist_dir=tmp_path, universe=universe, n=2,
    )
    assert picks == ["BBB", "AAA"]


def test_liquidity_skips_short_csv(tmp_path: Path):
    sector_map = {"AAA": "Banks", "BBB": "Banks"}
    universe = ["AAA", "BBB"]
    _write_fno_csv(tmp_path / "AAA.csv", days=80, vol=1_000_000, close=100.0)
    _write_fno_csv(tmp_path / "BBB.csv", days=10, vol=10_000_000, close=200.0)  # too short
    picks = lq.top_n_by_traded_value(
        sector_target="Banks", sector_map=sector_map,
        fno_hist_dir=tmp_path, universe=universe, n=2,
    )
    assert picks == ["AAA"]


# ---- divergence ----------------------------------------------------------

def test_sector_mean_intraday_return_returns_none_when_under_min():
    members = ["X", "Y"]
    mean, n = dv.sector_mean_intraday_return(members, {"X": 100, "Y": 200}, {"X": 101, "Y": 202})
    assert mean is None
    assert n == 2


def test_sector_mean_intraday_return_basic():
    members = ["A", "B", "C", "D"]
    opens = {"A": 100, "B": 100, "C": 100, "D": 100}
    nows = {"A": 101, "B": 102, "C": 103, "D": 104}  # +1, +2, +3, +4 % avg = +2.5%
    mean, n = dv.sector_mean_intraday_return(members, opens, nows)
    assert n == 4
    assert mean == pytest.approx(0.025, abs=1e-6)


def _make_panel_csv(path: Path, days: int, base_close: float, ret_seed: float) -> None:
    """Write a CSV with a stable close-to-close return distribution."""
    base = pd.Timestamp("2025-12-01")
    closes = [base_close]
    rng = list(range(1, days))
    for i in rng:
        closes.append(closes[-1] * (1.0 + ret_seed))
    rows = []
    for i in range(days):
        d = base + pd.Timedelta(days=i)
        rows.append({"Date": d.strftime("%Y-%m-%d"),
                     "Close": closes[i], "High": closes[i], "Low": closes[i],
                     "Open": closes[i], "Volume": 100_000})
    pd.DataFrame(rows).to_csv(path, index=False)


def test_compute_divergence_z_full_path(tmp_path: Path):
    a_members = ["BANK1", "BANK2", "BANK3", "BANK4"]
    b_members = ["NBFC1", "NBFC2", "NBFC3", "NBFC4"]
    for tkr in a_members:
        _make_panel_csv(tmp_path / f"{tkr}.csv", days=80, base_close=100, ret_seed=0.001)
    for tkr in b_members:
        _make_panel_csv(tmp_path / f"{tkr}.csv", days=80, base_close=100, ret_seed=0.0005)
    opens = {**{t: 100 for t in a_members}, **{t: 100 for t in b_members}}
    nows = {**{t: 102 for t in a_members}, **{t: 101 for t in b_members}}

    out = dv.compute_divergence_z(
        sector_a_members=a_members, sector_b_members=b_members,
        prices_open=opens, prices_at_signal=nows, fno_hist_dir=tmp_path,
    )
    assert out["divergence"] == pytest.approx(0.01, abs=1e-6)
    assert out["sigma_rows_used"] > 0
    assert out["rolling_std"] is not None and out["rolling_std"] >= 0


# ---- forward_shadow CLI surface ------------------------------------------

@pytest.fixture
def tmp_pdr_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    research = tmp_path / "research"
    opens = research / "opens"
    research.mkdir(parents=True)
    monkeypatch.setattr(fs, "_RESEARCH_DIR", research)
    monkeypatch.setattr(fs, "_OPENS_DIR", opens)
    monkeypatch.setattr(fs, "_RECS_PATH", research / "recommendations.csv")
    monkeypatch.setattr(fs, "_DIAG_PATH", research / "diagnostics.csv")
    return research


def test_basket_open_skips_outside_holdout(tmp_pdr_dirs, monkeypatch):
    monkeypatch.setattr(fs, "_today_iso", lambda: "2026-04-30")  # before HOLDOUT_START
    rc = fs.cmd_basket_open()
    assert rc == 0
    assert not (tmp_pdr_dirs / "recommendations.csv").exists()


def test_basket_open_idempotent_on_basket_id(tmp_pdr_dirs, monkeypatch):
    today = "2026-05-04"
    bid = fs._basket_id(today)
    fs._RECS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with fs._RECS_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fs._CSV_COLUMNS)
        w.writeheader()
        w.writerow({"basket_id": bid, "leg_id": "X", "ticker": "Y",
                    "side": "LONG", "status": "OPEN", "date": today,
                    "weight": "0.5", "entry_px": "100", "regime": "NEUTRAL"})
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    rc = fs.cmd_basket_open()
    assert rc == 0  # no-op


def test_basket_close_writes_pnl_and_status(tmp_pdr_dirs, monkeypatch):
    today = "2026-05-04"
    rows = [
        {"basket_id": fs._basket_id(today), "leg_id": "L1",
         "ticker": "BANKA", "date": today, "sector": "Banks",
         "side": "LONG", "weight": "0.25",
         "z_score": "1.4", "divergence_bps": "20.0",
         "rolling_std_bps": "14.3", "regime": "NEUTRAL",
         "entry_time": "T", "entry_px": "100.0", "atr_14": "",
         "stop_px": "", "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN",
         "regime_pit_corrected": "", "regime_correction_reason": ""},
        {"basket_id": fs._basket_id(today), "leg_id": "S1",
         "ticker": "NBFCA", "date": today, "sector": "NBFC_HFC",
         "side": "SHORT", "weight": "-0.25",
         "z_score": "1.4", "divergence_bps": "20.0",
         "rolling_std_bps": "14.3", "regime": "NEUTRAL",
         "entry_time": "T", "entry_px": "200.0", "atr_14": "",
         "stop_px": "", "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN",
         "regime_pit_corrected": "", "regime_correction_reason": ""},
    ]
    fs._write_recs(rows)

    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: {"BANKA": 102.0, "NBFCA": 198.0})
    rc = fs.cmd_basket_close(target_date_iso=today)
    assert rc == 0
    out = fs._read_recs()
    assert all(r["status"] == "CLOSED" for r in out)
    # LONG +2%, SHORT +1% (200 -> 198 is -1% raw, sign-flipped for SHORT = +1%)
    pnl_long = float([r["pnl_pct"] for r in out if r["side"] == "LONG"][0])
    pnl_short = float([r["pnl_pct"] for r in out if r["side"] == "SHORT"][0])
    assert pnl_long == pytest.approx(2.0, abs=1e-6)
    assert pnl_short == pytest.approx(1.0, abs=1e-6)
