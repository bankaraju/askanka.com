"""Tests for the NIFTY-500 weight loaders (TD-D1 canonical).

Two sister loaders:
- load_nifty500_weights: NSE equity-stockIndices source (ffmc -> weight_pct)
- load_trendlyne_nifty500_weights: Trendlyne nifty 500.xlsx parsed source

Both are PIT-aware and pick the latest snapshot at-or-before cutoff_date.
"""
from __future__ import annotations

from datetime import date

import pytest

from pipeline.research.theme_detector import data_loaders as dl


@pytest.fixture
def nse_weights_dir(tmp_path, monkeypatch):
    d = tmp_path / "nifty500_weights"
    d.mkdir()
    monkeypatch.setattr(dl, "_NIFTY500_WEIGHTS_DIR", d)
    return d


def _write_nse_csv(d, slug, snapshot, rows):
    p = d / f"{slug}_weights_{snapshot}.csv"
    header = (
        "snapshot_date,index_name,nse_symbol,ffmc_inr,weight_pct,last_price,"
        "p_change_1d,p_change_30d,p_change_365d,year_high,year_low,"
        "total_traded_value_inr"
    )
    lines = [header]
    for r in rows:
        lines.append(",".join(str(x) for x in r))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _write_trendlyne_csv(d, snapshot, rows):
    p = d / f"trendlyne_nifty500_parsed_{snapshot}.csv"
    lines = ["snapshot_date,source,Company,nse_symbol,weight_pct"]
    for r in rows:
        lines.append(",".join(str(x) for x in r))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# --- NSE loader ---


def test_nse_returns_none_when_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "_NIFTY500_WEIGHTS_DIR", tmp_path / "missing")
    assert dl.load_nifty500_weights(date(2026, 5, 2)) is None


def test_nse_returns_none_when_no_files(nse_weights_dir):
    assert dl.load_nifty500_weights(date(2026, 5, 2)) is None


def test_nse_picks_latest_at_or_before_cutoff(nse_weights_dir):
    _write_nse_csv(
        nse_weights_dir, "nifty_500", "2026-04-01",
        [("2026-04-01", "NIFTY 500", "RELIANCE", 1e12, 4.5,
          1400, 0.5, 1, 2, 1500, 1200, 1e10)],
    )
    _write_nse_csv(
        nse_weights_dir, "nifty_500", "2026-05-02",
        [("2026-05-02", "NIFTY 500", "RELIANCE", 1.1e12, 4.9,
          1436, 0.74, 4.88, 2.21, 1611.8, 1290, 4.38e10)],
    )
    df = dl.load_nifty500_weights(date(2026, 5, 2))
    assert df is not None
    assert "RELIANCE" in df.index
    assert df.loc["RELIANCE", "weight_pct"] == 4.9
    assert df.loc["RELIANCE", "snapshot_date"] == "2026-05-02"


def test_nse_skips_future_snapshots(nse_weights_dir):
    _write_nse_csv(
        nse_weights_dir, "nifty_500", "2026-04-01",
        [("2026-04-01", "NIFTY 500", "RELIANCE", 1e12, 4.5,
          1400, 0.5, 1, 2, 1500, 1200, 1e10)],
    )
    _write_nse_csv(
        nse_weights_dir, "nifty_500", "2026-05-02",
        [("2026-05-02", "NIFTY 500", "RELIANCE", 1.1e12, 4.9,
          1436, 0.74, 4.88, 2.21, 1611.8, 1290, 4.38e10)],
    )
    df = dl.load_nifty500_weights(date(2026, 4, 15))
    assert df is not None
    assert df.loc["RELIANCE", "weight_pct"] == 4.5


def test_nse_alternate_index_slug(nse_weights_dir):
    _write_nse_csv(
        nse_weights_dir, "nifty_50", "2026-05-02",
        [("2026-05-02", "NIFTY 50", "RELIANCE", 1e12, 9.8,
          1436, 0.74, 4.88, 2.21, 1611.8, 1290, 4.38e10)],
    )
    df = dl.load_nifty500_weights(date(2026, 5, 2), index_name="NIFTY 50")
    assert df is not None
    assert df.loc["RELIANCE", "weight_pct"] == 9.8


def test_nse_returns_none_for_missing_index(nse_weights_dir):
    _write_nse_csv(
        nse_weights_dir, "nifty_500", "2026-05-02",
        [("2026-05-02", "NIFTY 500", "RELIANCE", 1e12, 4.9,
          1436, 0.74, 4.88, 2.21, 1611.8, 1290, 4.38e10)],
    )
    assert dl.load_nifty500_weights(date(2026, 5, 2), index_name="NIFTY BANK") is None


# --- Trendlyne loader ---


def test_trendlyne_returns_none_when_no_files(nse_weights_dir):
    assert dl.load_trendlyne_nifty500_weights(date(2026, 5, 2)) is None


def test_trendlyne_picks_latest_at_or_before_cutoff(nse_weights_dir):
    _write_trendlyne_csv(
        nse_weights_dir, "2026-04-15",
        [("2026-04-15", "trendlyne", "RELIANCE INDUSTRIES LTD", "RELIANCE", 4.85)],
    )
    _write_trendlyne_csv(
        nse_weights_dir, "2026-05-02",
        [("2026-05-02", "trendlyne", "RELIANCE INDUSTRIES LTD", "RELIANCE", 4.89),
         ("2026-05-02", "trendlyne", "HDFC BANK LTD", "HDFCBANK", 3.0)],
    )
    df = dl.load_trendlyne_nifty500_weights(date(2026, 5, 2))
    assert df is not None
    assert df.loc["RELIANCE", "weight_pct"] == 4.89
    assert df.loc["HDFCBANK", "weight_pct"] == 3.0
    df_old = dl.load_trendlyne_nifty500_weights(date(2026, 4, 20))
    assert df_old is not None
    assert df_old.loc["RELIANCE", "weight_pct"] == 4.85
    assert "HDFCBANK" not in df_old.index
