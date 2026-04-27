"""Smoke tests for the pattern-scanner CLI driver. Functional behavior
(detect / rank / write JSON) is already covered by pattern_scanner unit
tests; here we just verify CLI plumbing — argparse + adapter shape."""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from pipeline.cli_pattern_scanner import _build_bars_loader, cmd_fit, cmd_scan


def test_bars_loader_adapter_sets_datetime_index():
    """CanonicalLoader returns df with `date` column; adapter must move it
    to the index (pattern_scanner.detect requires DatetimeIndex)."""
    fake_loader = MagicMock()
    fake_loader.daily_bars.return_value = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000, 1100, 1200],
    })
    loader = _build_bars_loader(fake_loader)
    out = loader("RELIANCE")
    assert isinstance(out.index, pd.DatetimeIndex)
    assert "date" not in out.columns
    assert out.index[0] == pd.Timestamp("2026-01-01")
    assert out.iloc[0]["close"] == 100.5


def test_bars_loader_returns_none_on_missing_csv():
    """Adapter swallows FileNotFoundError so fit_universe can skip the ticker."""
    fake_loader = MagicMock()
    fake_loader.daily_bars.side_effect = FileNotFoundError("bars CSV not found")
    loader = _build_bars_loader(fake_loader)
    assert loader("MISSING") is None


def test_bars_loader_returns_none_on_empty_df():
    fake_loader = MagicMock()
    fake_loader.daily_bars.return_value = pd.DataFrame()
    loader = _build_bars_loader(fake_loader)
    assert loader("EMPTY") is None


def test_cmd_scan_errors_when_stats_parquet_missing(tmp_path):
    """scan refuses to run before fit has produced pattern_stats.parquet."""
    canonical = tmp_path / "canonical.json"  # never read since we exit early
    stats = tmp_path / "missing.parquet"
    with pytest.raises(SystemExit) as exc:
        cmd_scan(canonical_path=canonical, stats_path=stats,
                  out_path=tmp_path / "out.json")
    assert exc.value.code == 1


def test_cmd_fit_writes_parquet(tmp_path, monkeypatch):
    """End-to-end: fit reads canonical, runs fit_universe, writes parquet.
    Mock fit_universe to keep this fast."""
    fake_universe = pd.DataFrame([
        {"ticker": "RELIANCE", "pattern_id": "BULLISH_HAMMER", "direction": "LONG",
         "n_occurrences": 50, "wins": 28, "losses": 22, "win_rate": 0.56,
         "mean_pnl_pct": 0.008, "stddev_pnl_pct": 0.02, "z_score": 0.85,
         "fold_win_rates": [0.55, 0.56, 0.58, 0.55], "fold_stability": 0.94,
         "first_seen": date(2021, 1, 1), "last_seen": date(2026, 4, 25)},
    ])
    fake_canonical_loader = MagicMock()
    fake_canonical_loader.universe = {"RELIANCE", "INFY"}
    monkeypatch.setattr(
        "pipeline.cli_pattern_scanner.CanonicalLoader",
        lambda canonical_path: fake_canonical_loader,
    )
    monkeypatch.setattr(
        "pipeline.cli_pattern_scanner.fit_universe",
        lambda **kw: fake_universe,
    )
    out = tmp_path / "pattern_stats.parquet"
    df = cmd_fit(canonical_path=tmp_path / "fake.json", stats_path=out)
    assert out.exists()
    reloaded = pd.read_parquet(out)
    assert len(reloaded) == 1
    assert reloaded.iloc[0]["ticker"] == "RELIANCE"
