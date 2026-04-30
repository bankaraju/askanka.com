"""Tests for pipeline.research.auto_spread_discovery.liquidity."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from pipeline.research.auto_spread_discovery import liquidity


def _write_csv(path: Path, rows: list[tuple[str, float, float]]) -> None:
    """rows = list of (date, close, volume)."""
    with path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["Date", "Close", "High", "Low", "Open", "Volume"])
        for d, c, v in rows:
            w.writerow([d, c, c, c, c, v])


def test_rank_top_k_by_explicit_adv_map():
    adv = {"AAA": 100.0, "BBB": 500.0, "CCC": 200.0, "DDD": 50.0}
    assert liquidity.rank_top_k_by_adv(["AAA", "BBB", "CCC", "DDD"], 3,
                                        adv_map=adv) == ["BBB", "CCC", "AAA"]


def test_rank_handles_missing_adv():
    adv = {"AAA": 100.0}
    # BBB and CCC missing -> ADV=0; tie-break alphabetical
    out = liquidity.rank_top_k_by_adv(["AAA", "BBB", "CCC"], 3, adv_map=adv)
    assert out[0] == "AAA"  # highest ADV
    assert set(out[1:3]) == {"BBB", "CCC"}  # both ADV=0
    assert out[1:3] == ["BBB", "CCC"]  # alphabetical secondary sort


def test_rank_empty_input_returns_empty():
    assert liquidity.rank_top_k_by_adv([], 3) == []


def test_rank_caps_at_k():
    adv = {"AAA": 1.0, "BBB": 2.0, "CCC": 3.0, "DDD": 4.0, "EEE": 5.0}
    out = liquidity.rank_top_k_by_adv(list(adv.keys()), 2, adv_map=adv)
    assert len(out) == 2
    assert out == ["EEE", "DDD"]


def test_rank_case_insensitive():
    adv = {"AAA": 100.0, "BBB": 200.0}
    out = liquidity.rank_top_k_by_adv(["aaa", "bbb"], 2, adv_map=adv)
    assert out == ["BBB", "AAA"]


def test_adv_for_ticker_reads_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(liquidity, "FNO_HIST_DIR", tmp_path)
    liquidity.clear_cache()
    csv_path = tmp_path / "TESTSTOCK.csv"
    rows = [(f"2026-{m:02d}-01", 100.0, 1_000_000.0) for m in range(1, 13)]
    _write_csv(csv_path, rows)
    adv = liquidity.adv_for_ticker("TESTSTOCK")
    # 12 rows, all 100*1M = 1e8; mean = 1e8
    assert adv == pytest.approx(1e8)


def test_adv_for_ticker_zero_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(liquidity, "FNO_HIST_DIR", tmp_path)
    liquidity.clear_cache()
    assert liquidity.adv_for_ticker("NONEXISTENT") == 0.0


def test_adv_filters_zero_close_or_volume(tmp_path, monkeypatch):
    monkeypatch.setattr(liquidity, "FNO_HIST_DIR", tmp_path)
    liquidity.clear_cache()
    csv_path = tmp_path / "MIXED.csv"
    rows = [
        ("2026-01-01", 0.0, 1_000_000.0),  # zero close → filtered
        ("2026-01-02", 100.0, 0.0),         # zero volume → filtered
        ("2026-01-03", 100.0, 1_000_000.0), # valid
        ("2026-01-04", 200.0, 500_000.0),   # valid
    ]
    _write_csv(csv_path, rows)
    adv = liquidity.adv_for_ticker("MIXED")
    # Only last 2 valid: (100*1M + 200*500K) / 2 = (100M + 100M) / 2 = 1e8
    assert adv == pytest.approx(1e8)


def test_lookback_window_truncates_history(tmp_path, monkeypatch):
    monkeypatch.setattr(liquidity, "FNO_HIST_DIR", tmp_path)
    liquidity.clear_cache()
    csv_path = tmp_path / "LONG.csv"
    # 100 days; first 60 = 1e6 ADV, last 40 = 1e9 ADV
    rows = [(f"2026-{((i - 1) // 30) + 1:02d}-{((i - 1) % 30) + 1:02d}",
             100.0, 10_000.0 if i <= 60 else 10_000_000.0)
            for i in range(1, 101)]
    _write_csv(csv_path, rows)
    # Default lookback=60 means we use the last 60 -> mostly the high-ADV regime
    adv_60 = liquidity.adv_for_ticker("LONG", lookback=60)
    adv_100 = liquidity.adv_for_ticker("LONG", lookback=100)
    assert adv_60 > adv_100, "lookback=60 should weight recent high-ADV days more"
