"""Tests for pipeline.research.h_2026_04_30_defence_momentum.

Spec: docs/superpowers/specs/2026-04-30-defence-momentum-design.md
Covers: ATR-scaled sizing math, basket lifecycle, regime gate, holdout window.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.research.h_2026_04_30_defence_momentum import forward_shadow as fs
from pipeline.research.h_2026_04_30_defence_momentum.config import get_config
from pipeline.research.h_2026_04_30_defence_momentum.sizing import atr_scaled_weights


# ---- sizing math --------------------------------------------------------

def test_sizing_falls_back_equal_weight_on_missing_atr():
    legs = ["A", "B", "C"]
    w = atr_scaled_weights(legs, atr_pcts={"A": 0.0}, cap_x_baseline=None)
    # any leg with non-positive ATR → equal-weight fallback for the whole side
    for tkr in legs:
        assert w[tkr] == pytest.approx(1.0 / 3, abs=1e-9)


def test_sizing_inverse_to_atr():
    # high-vol leg → smaller weight; low-vol leg → larger weight
    legs = ["HAL", "BEL", "BDL"]
    atrs = {"HAL": 0.030, "BEL": 0.025, "BDL": 0.020}
    w = atr_scaled_weights(legs, atrs, cap_x_baseline=None)
    assert w["BDL"] > w["BEL"] > w["HAL"]
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)


def test_sizing_cap_redistributes_excess():
    # If one leg's natural inverse weight is > 2x baseline, cap and redistribute.
    legs = ["X", "Y"]
    # Y's ATR is 10x X → unbounded weight on X = 10/(10+1) ≈ 0.909, beyond 2x baseline (1.0)
    atrs = {"X": 0.001, "Y": 0.010}
    w_uncapped = atr_scaled_weights(legs, atrs, cap_x_baseline=None)
    assert w_uncapped["X"] > 0.5

    w_capped = atr_scaled_weights(legs, atrs, cap_x_baseline=2.0)
    # baseline=0.5, cap=1.0, so uncapped already <= cap; no change for n=2
    assert w_capped["X"] == pytest.approx(w_uncapped["X"], abs=1e-6)


def test_sizing_cap_binds_with_3_legs():
    legs = ["X", "Y", "Z"]
    # X has 100x lower ATR than Y/Z → natural weight ~ 100/102 ≈ 0.98 (>> 2x baseline=0.667)
    atrs = {"X": 0.0001, "Y": 0.010, "Z": 0.010}
    w = atr_scaled_weights(legs, atrs, cap_x_baseline=2.0)
    baseline = 1 / 3
    cap = 2.0 * baseline  # ≈ 0.667
    assert w["X"] <= cap + 1e-6
    # And total sums to 1
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)


# ---- basket lifecycle ---------------------------------------------------

@pytest.fixture
def tmp_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(fs, "_RESEARCH_BASE", tmp_path)
    return tmp_path


@pytest.fixture
def regime_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "today_regime.json"
    monkeypatch.setattr(fs, "_TODAY_REGIME_PATH", p)
    return p


def _set_regime(path: Path, zone: str) -> None:
    path.write_text(json.dumps({"zone": zone}), encoding="utf-8")


def _today_in_holdout(cfg) -> str:
    """First trading day in the holdout window."""
    from pipeline.trading_calendar import is_trading_day
    from datetime import datetime, timedelta, timezone
    IST = timezone(timedelta(hours=5, minutes=30))
    d = cfg.holdout_start
    while not is_trading_day(datetime.combine(d, datetime.min.time(), tzinfo=IST)):
        d = d + timedelta(days=1)
    return d.isoformat()


def test_basket_open_skips_when_regime_mismatch(tmp_ledger, regime_path, monkeypatch):
    cfg = get_config("DEFIT")
    _set_regime(regime_path, "RISK-ON")  # config wants NEUTRAL
    today = _today_in_holdout(cfg)
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    rc = fs.cmd_basket_open(cfg)
    assert rc == 0
    assert not fs._ledger_path(cfg).exists()


def test_basket_open_skips_outside_holdout(tmp_ledger, regime_path, monkeypatch):
    cfg = get_config("DEFIT")
    _set_regime(regime_path, "NEUTRAL")
    monkeypatch.setattr(fs, "_today_iso", lambda: "2026-04-30")
    rc = fs.cmd_basket_open(cfg)
    assert rc == 0
    assert not fs._ledger_path(cfg).exists()


def test_basket_open_writes_6_legs_for_defit(tmp_ledger, regime_path, monkeypatch):
    cfg = get_config("DEFIT")
    _set_regime(regime_path, "NEUTRAL")
    today = _today_in_holdout(cfg)
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda syms: {"HAL": 4500, "BEL": 290, "BDL": 1450,
                      "TCS": 3800, "INFY": 1700, "WIPRO": 320},
    )
    # ATR percent — high for defence, low for IT
    monkeypatch.setattr(
        fs, "_atr_pct_from_csv",
        lambda t, **kw: {"HAL": 0.030, "BEL": 0.028, "BDL": 0.034,
                         "TCS": 0.012, "INFY": 0.013, "WIPRO": 0.015}.get(t),
    )
    rc = fs.cmd_basket_open(cfg)
    assert rc == 0

    rows = list(csv.DictReader(open(fs._ledger_path(cfg), encoding="utf-8")))
    assert len(rows) == 6
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["HAL"]["side"] == "LONG"
    assert by_ticker["TCS"]["side"] == "SHORT"
    # ATR-scaled: BDL has highest ATR → smallest LONG weight
    long_weights = {t: float(by_ticker[t]["weight"]) for t in ["HAL", "BEL", "BDL"]}
    assert long_weights["BDL"] < long_weights["HAL"]
    # SHORT weights are negative
    short_weights = {t: float(by_ticker[t]["weight"]) for t in ["TCS", "INFY", "WIPRO"]}
    assert all(w < 0 for w in short_weights.values())
    # |LONG weights| sum to 1, |SHORT weights| sum to 1 (per side)
    assert sum(long_weights.values()) == pytest.approx(1.0, abs=1e-3)
    assert sum(abs(w) for w in short_weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_basket_open_idempotent(tmp_ledger, regime_path, monkeypatch):
    cfg = get_config("DEFIT")
    _set_regime(regime_path, "NEUTRAL")
    today = _today_in_holdout(cfg)
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    monkeypatch.setattr(
        fs, "_fetch_ltp",
        lambda syms: {"HAL": 4500, "BEL": 290, "BDL": 1450,
                      "TCS": 3800, "INFY": 1700, "WIPRO": 320},
    )
    monkeypatch.setattr(fs, "_atr_pct_from_csv", lambda t, **kw: 0.020)
    fs.cmd_basket_open(cfg)
    fs.cmd_basket_open(cfg)
    rows = list(csv.DictReader(open(fs._ledger_path(cfg), encoding="utf-8")))
    assert len(rows) == 6


def test_basket_close_fires_at_target_date(tmp_ledger, monkeypatch):
    cfg = get_config("DEFIT")
    rows = [
        {"hypothesis_id": cfg.hypothesis_id, "basket_id": "DEFIT-2026-05-04",
         "leg_id": "DEFIT-2026-05-04-HAL-LONG", "ticker": "HAL", "side": "LONG",
         "weight": "0.4", "entry_date": "2026-05-04", "entry_time": "T",
         "entry_px": "4500.0", "atr_pct": "0.030", "regime_at_entry": "NEUTRAL",
         "target_close_date": "2026-05-11",
         "exit_date": "", "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN",
         "regime_pit_corrected": "", "regime_correction_reason": ""},
    ]
    fs._write_recs(cfg, rows)
    monkeypatch.setattr(fs, "_fetch_ltp", lambda syms: {"HAL": 4600.0})
    rc = fs.cmd_basket_close(cfg, target_date_iso="2026-05-11")
    assert rc == 0
    out = fs._read_recs(cfg)
    assert out[0]["status"] == "CLOSED"
    assert out[0]["exit_reason"] == "TIME_STOP"
    # +100/4500 = ~2.222%
    assert float(out[0]["pnl_pct"]) == pytest.approx(2.222, abs=0.01)


def test_basket_monitor_fires_basket_stop(tmp_ledger, monkeypatch):
    cfg = get_config("DEFIT")
    today = _today_in_holdout(cfg)
    rows = [
        {"hypothesis_id": cfg.hypothesis_id, "basket_id": f"DEFIT-{today}",
         "leg_id": "L1", "ticker": "HAL", "side": "LONG", "weight": "0.4",
         "entry_date": today, "entry_time": "T", "entry_px": "4500.0",
         "atr_pct": "0.030", "regime_at_entry": "NEUTRAL",
         "target_close_date": "2099-01-01",
         "exit_date": "", "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN",
         "regime_pit_corrected": "", "regime_correction_reason": ""},
        {"hypothesis_id": cfg.hypothesis_id, "basket_id": f"DEFIT-{today}",
         "leg_id": "S1", "ticker": "TCS", "side": "SHORT", "weight": "-0.4",
         "entry_date": today, "entry_time": "T", "entry_px": "3800.0",
         "atr_pct": "0.012", "regime_at_entry": "NEUTRAL",
         "target_close_date": "2099-01-01",
         "exit_date": "", "exit_time": "", "exit_px": "", "exit_reason": "",
         "pnl_pct": "", "status": "OPEN",
         "regime_pit_corrected": "", "regime_correction_reason": ""},
    ]
    fs._write_recs(cfg, rows)
    # HAL down 5% (LONG bad), TCS up 5% (SHORT bad) → basket pnl ≈ -500 bps
    monkeypatch.setattr(fs, "_fetch_ltp",
                        lambda syms: {"HAL": 4275.0, "TCS": 3990.0})
    monkeypatch.setattr(fs, "_today_iso", lambda: today)
    rc = fs.cmd_basket_monitor(cfg)
    assert rc == 0
    out = fs._read_recs(cfg)
    assert all(r["status"] == "CLOSED" for r in out)
    assert all(r["exit_reason"] == "BASKET_STOP" for r in out)
