"""Integration: runner._compute_signals_at composes loader+features+score
end-to-end on a synthetic universe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import runner

IST = timezone(timedelta(hours=5, minutes=30))


def test_compute_signals_at_returns_per_instrument_scores(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    weights_dir = tmp_path / "weights"
    weights_dir.mkdir()
    (weights_dir / "latest_stocks.json").write_text(
        '{"weights": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4], "long_threshold": 1.0, "short_threshold": -1.0}',
        encoding="utf-8",
    )
    # Synthetic minute bars cached on disk for ONE instrument
    cache_dir = tmp_path / "cache_1min"
    cache_dir.mkdir()
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-04-29 09:15", periods=20, freq="1min", tz="Asia/Kolkata"),
        "open":   np.linspace(2500, 2510, 20),
        "high":   np.linspace(2502, 2512, 20),
        "low":    np.linspace(2498, 2508, 20),
        "close":  np.linspace(2501, 2511, 20),
        "volume": np.linspace(1000, 5000, 20),
    })
    bars.to_parquet(cache_dir / "RELIANCE.parquet", index=False)
    # Sector index cache (RELIANCE -> NIFTYENERGY) — required after Fix #4:
    # missing sector cache now skips the instrument rather than silently
    # using the stock's own bars as the sector proxy.
    sector_bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-04-29 09:15", periods=20, freq="1min", tz="Asia/Kolkata"),
        "open":   np.linspace(20000, 20050, 20),
        "high":   np.linspace(20010, 20060, 20),
        "low":    np.linspace(19990, 20040, 20),
        "close":  np.linspace(20005, 20055, 20),
        "volume": np.linspace(100000, 500000, 20),
    })
    sector_bars.to_parquet(cache_dir / "NIFTYENERGY.parquet", index=False)
    # PCR snapshot (simplified)
    pcr_dir = tmp_path / "pcr"
    pcr_dir.mkdir()
    (pcr_dir / "RELIANCE_today.json").write_text(
        '{"put_oi_total_next_month": 12000, "call_oi_total_next_month": 10000}', encoding="utf-8")
    (pcr_dir / "RELIANCE_2d_ago.json").write_text(
        '{"put_oi_total_next_month": 10000, "call_oi_total_next_month": 11000}', encoding="utf-8")

    monkeypatch.setattr(runner, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(runner, "PCR_DIR", pcr_dir)

    out = runner._compute_signals_at(
        eval_t=datetime(2026, 4, 29, 9, 30, tzinfo=IST),
        univ={"stocks": ["RELIANCE"], "indices": []},
    )
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["instrument"] == "RELIANCE"
    assert "score" in out[0]
    assert "decision" in out[0]
    assert out[0]["decision"] in ("LONG", "SHORT", "SKIP")


def test_compute_signals_at_skips_when_sector_cache_missing(monkeypatch, tmp_path):
    """Fix #4: when sector index cache is missing, the instrument MUST be
    skipped (not silently zeroed via stock-as-its-own-sector). No synthetic
    fallback per feedback_no_hallucination_mandate.md.
    """
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    weights_dir = tmp_path / "weights"
    weights_dir.mkdir()
    (weights_dir / "latest_stocks.json").write_text(
        '{"weights": [0.5, -0.3, 0.2, 0.1, 0.0, 0.4], "long_threshold": 1.0, "short_threshold": -1.0}',
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache_1min"
    cache_dir.mkdir()
    # ONLY the stock bars — NO sector cache. Pre-fix, this silently used
    # stock-bars as sector_df, yielding rs_vs_sector = 0 and a bogus signal.
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-04-29 09:15", periods=20, freq="1min", tz="Asia/Kolkata"),
        "open":   np.linspace(2500, 2510, 20),
        "high":   np.linspace(2502, 2512, 20),
        "low":    np.linspace(2498, 2508, 20),
        "close":  np.linspace(2501, 2511, 20),
        "volume": np.linspace(1000, 5000, 20),
    })
    bars.to_parquet(cache_dir / "RELIANCE.parquet", index=False)
    pcr_dir = tmp_path / "pcr"
    pcr_dir.mkdir()
    (pcr_dir / "RELIANCE_today.json").write_text(
        '{"put_oi_total_next_month": 12000, "call_oi_total_next_month": 10000}', encoding="utf-8")
    (pcr_dir / "RELIANCE_2d_ago.json").write_text(
        '{"put_oi_total_next_month": 10000, "call_oi_total_next_month": 11000}', encoding="utf-8")
    monkeypatch.setattr(runner, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(runner, "PCR_DIR", pcr_dir)

    out = runner._compute_signals_at(
        eval_t=datetime(2026, 4, 29, 9, 30, tzinfo=IST),
        univ={"stocks": ["RELIANCE"], "indices": []},
    )
    # Instrument is skipped — no row emitted, no fake-zero signal.
    assert out == []
