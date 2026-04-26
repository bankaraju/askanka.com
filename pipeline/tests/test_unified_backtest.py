"""Tests for pipeline.autoresearch.unified_backtest

Verifies that run_backtest() returns the expected structure and computes
correct statistics using synthetic data — no yfinance or real CSV access.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Use the canonical fully-qualified package path. The bare `autoresearch.*`
# form collides with pipeline/tests/autoresearch/__init__.py during multi-test
# collection (pytest treats the test subpackage as the canonical `autoresearch`
# namespace and shadows pipeline/autoresearch/).
from pipeline.autoresearch.unified_backtest import (
    SPREAD_DEFINITIONS,
    _avg_returns,
    _compute_daily_regimes,
    _compute_regime_accuracy,
    _compute_spread_returns,
    _confidence_interval_95,
    _max_drawdown,
    _sharpe,
    _signal_to_zone,
    run_backtest,
)


# ---------------------------------------------------------------------------
# Unit tests — pure math helpers
# ---------------------------------------------------------------------------

def test_signal_to_zone_boundaries():
    """_signal_to_zone correctly maps signal values to all 5 zones."""
    # Use the same center / band values as etf_reoptimize
    from pipeline.autoresearch.etf_reoptimize import _CALM_CENTER, _CALM_BAND
    c, b = _CALM_CENTER, _CALM_BAND

    assert _signal_to_zone(c + 2 * b + 1) == "EUPHORIA"
    assert _signal_to_zone(c + 1.5 * b) == "RISK-ON"
    assert _signal_to_zone(c) == "NEUTRAL"
    assert _signal_to_zone(c - 1.5 * b) == "CAUTION"
    assert _signal_to_zone(c - 2 * b - 1) == "RISK-OFF"


def test_sharpe_positive():
    rets = pd.Series([1.0, 2.0, 1.5, 2.5, 1.0])
    s = _sharpe(rets)
    assert s > 0


def test_sharpe_zero_std():
    rets = pd.Series([1.0, 1.0, 1.0])
    assert _sharpe(rets) == 0.0


def test_max_drawdown_negative():
    rets = pd.Series([-5.0, -3.0, 2.0, -4.0])
    dd = _max_drawdown(rets)
    assert dd < 0


def test_max_drawdown_all_positive():
    rets = pd.Series([1.0, 2.0, 3.0])
    dd = _max_drawdown(rets)
    # No drawdown from all-positive returns
    assert dd >= -0.01  # small numerical tolerance


def test_confidence_interval_95_ordering():
    # _confidence_interval_95 accepts a series in any unit and returns CI in same unit.
    # In run_backtest the series is already divided by 100 before being passed in.
    # Here we pass decimal-fraction values directly.
    rets = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
    lo, hi = _confidence_interval_95(rets)
    assert lo < hi
    # CI should straddle the mean
    mean_val = float(rets.mean())
    assert lo < mean_val < hi
    assert lo > 0  # all positive returns → CI lower bound still positive


def test_avg_returns_basic():
    """_avg_returns computes correct 1d forward returns."""
    prices = pd.Series(
        [100.0, 105.0, 110.0, 100.0, 90.0],
        index=pd.date_range("2025-01-01", periods=5, freq="D"),
    )
    dates = pd.DatetimeIndex(["2025-01-01", "2025-01-02"])
    result = _avg_returns(prices, dates, period=1)

    assert abs(result["2025-01-01"] - 5.0) < 0.01  # (105 - 100) / 100 * 100
    # (110 - 105) / 105 * 100 ≈ 4.76
    assert abs(float(result["2025-01-02"]) - 4.76) < 0.1


def test_avg_returns_returns_nan_at_end():
    """_avg_returns returns NaN when forward period goes past end of data."""
    prices = pd.Series(
        [100.0, 105.0],
        index=pd.date_range("2025-01-01", periods=2, freq="D"),
    )
    result = _avg_returns(prices, prices.index, period=3)
    assert all(np.isnan(v) for v in result.values)


# ---------------------------------------------------------------------------
# compute_daily_regimes
# ---------------------------------------------------------------------------

def test_compute_daily_regimes_returns_series():
    """_compute_daily_regimes returns a Series with zone strings."""
    dates = pd.date_range("2025-01-01", periods=10, freq="D")
    etf_returns = pd.DataFrame(
        {"ig_bond": np.random.randn(10) * 0.5, "sp500": np.random.randn(10) * 0.5},
        index=dates,
    )
    weights = {"ig_bond": 1.0, "sp500": 0.5}
    zones = _compute_daily_regimes(etf_returns, weights)

    assert isinstance(zones, pd.Series)
    assert len(zones) == 10
    valid = {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
    assert all(z in valid for z in zones)


# ---------------------------------------------------------------------------
# compute_spread_returns
# ---------------------------------------------------------------------------

def test_compute_spread_returns_basic():
    """_compute_spread_returns produces a non-empty Series for valid inputs."""
    dates = pd.date_range("2025-01-01", periods=10, freq="D")
    long_prices = pd.Series(
        np.linspace(100, 110, 10), index=dates
    )
    short_prices = pd.Series(
        np.linspace(100, 105, 10), index=dates
    )
    prices_cache = {"LONG_A": long_prices, "SHORT_A": short_prices}

    result = _compute_spread_returns(
        long_symbols=["LONG_A"],
        short_symbols=["SHORT_A"],
        prices_cache=prices_cache,
        dates=dates,
        period=1,
    )

    assert result is not None
    assert isinstance(result, pd.Series)
    assert result.dropna().shape[0] > 0


def test_compute_spread_returns_missing_long():
    """_compute_spread_returns returns None if long leg is missing."""
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    prices_cache = {"SHORT_A": pd.Series(np.ones(5), index=dates)}
    result = _compute_spread_returns(
        long_symbols=["MISSING_LONG"],
        short_symbols=["SHORT_A"],
        prices_cache=prices_cache,
        dates=dates,
        period=1,
    )
    assert result is None


def test_compute_spread_returns_missing_short():
    """_compute_spread_returns returns None if short leg is missing."""
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    prices_cache = {"LONG_A": pd.Series(np.ones(5), index=dates)}
    result = _compute_spread_returns(
        long_symbols=["LONG_A"],
        short_symbols=["MISSING_SHORT"],
        prices_cache=prices_cache,
        dates=dates,
        period=1,
    )
    assert result is None


# ---------------------------------------------------------------------------
# compute_regime_accuracy
# ---------------------------------------------------------------------------

def test_compute_regime_accuracy_structure():
    """_compute_regime_accuracy returns correct keys for all 5 zones."""
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    zones = pd.Series(
        ["RISK-ON"] * 5 + ["RISK-OFF"] * 5 + ["NEUTRAL"] * 5 + ["CAUTION"] * 3 + ["EUPHORIA"] * 2,
        index=dates,
        name="zone",
    )
    nifty_rets = pd.Series(
        [0.5, -0.2, 0.3, -0.1, 0.4,  # RISK-ON days
         -0.5, 0.2, -0.3, 0.1, -0.4,  # RISK-OFF days
         0.1, 0.0, -0.1, 0.2, -0.2,   # NEUTRAL days
         -0.3, -0.1, 0.1,              # CAUTION days
         0.8, 1.2],                    # EUPHORIA days
        index=dates,
    )
    per_regime = _compute_regime_accuracy(zones, nifty_rets)

    assert set(per_regime.keys()) == {"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}
    for zone, d in per_regime.items():
        assert "days" in d
        assert "accuracy" in d
        assert "avg_nifty_return" in d

    # NEUTRAL should have no accuracy score
    assert per_regime["NEUTRAL"]["accuracy"] is None

    # RISK-ON accuracy should be between 0 and 1
    assert 0.0 <= per_regime["RISK-ON"]["accuracy"] <= 1.0


# ---------------------------------------------------------------------------
# Integration test — run_backtest with synthetic data
# ---------------------------------------------------------------------------

def _make_synthetic_etf_returns(n_days: int = 100, seed: int = 42) -> pd.DataFrame:
    """Build a synthetic ETF returns DataFrame for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    cols = ["ig_bond", "sp500", "nifty", "defence", "energy"]
    data = rng.normal(0, 1, size=(n_days, len(cols)))
    return pd.DataFrame(data, index=dates, columns=cols)


def _make_synthetic_weights() -> dict:
    return {
        "optimal_weights": {"ig_bond": 5.0, "sp500": 2.0},
        "best_accuracy": 60.0,
        "best_sharpe": 2.0,
        "today_zone": "NEUTRAL",
        "today_signal": 1.5,
        "timestamp": "2026-04-18T00:00:00+00:00",
        "n_iterations": 100,
    }


def _make_synthetic_fno_csvs(tmp_path: Path, n_days: int = 200, seed: int = 7) -> None:
    """Write synthetic CSVs for all spread tickers to tmp_path."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n_days, freq="B")
    all_tickers: set[str] = set()
    for defn in SPREAD_DEFINITIONS.values():
        all_tickers.update(defn["long"])
        all_tickers.update(defn["short"])

    for sym in all_tickers:
        prices = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n_days))
        df = pd.DataFrame({"Date": dates, "Close": prices})
        df.to_csv(tmp_path / f"{sym}.csv", index=False)


def test_run_backtest_returns_expected_structure(tmp_path):
    """run_backtest() returns a dict with all required top-level keys."""
    # Build synthetic weights file
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(_make_synthetic_weights()), encoding="utf-8")

    # Build synthetic F&O CSVs
    fno_dir = tmp_path / "fno_historical"
    fno_dir.mkdir()
    _make_synthetic_fno_csvs(fno_dir)

    # Build synthetic ETF returns
    etf_ret = _make_synthetic_etf_returns(n_days=150)

    # Run backtest (dry_run=True — no file writes)
    result = run_backtest(
        weights_path=weights_path,
        fno_dir=fno_dir,
        etf_returns=etf_ret,
        dry_run=True,
    )

    # Verify top-level structure
    required_keys = [
        "period_start", "period_end", "trading_days", "weights_file",
        "weights_timestamp", "regime_distribution", "regime_accuracy",
        "total_trades", "win_rate", "avg_return_per_trade", "sharpe",
        "max_drawdown", "confidence_interval_95", "per_spread",
        "per_regime", "computed_at",
    ]
    for key in required_keys:
        assert key in result, f"Missing key in result: {key}"

    # Basic sanity checks
    assert result["trading_days"] == 150
    assert 0.0 <= result["win_rate"] <= 1.0
    assert isinstance(result["per_spread"], dict)
    assert isinstance(result["per_regime"], dict)
    assert isinstance(result["confidence_interval_95"], list)
    assert len(result["confidence_interval_95"]) == 2
    assert result["total_trades"] >= 0


def test_run_backtest_no_fno_data(tmp_path):
    """run_backtest() handles all-missing F&O CSVs gracefully (no crash)."""
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(_make_synthetic_weights()), encoding="utf-8")

    fno_dir = tmp_path / "fno_historical_empty"
    fno_dir.mkdir()  # empty — no CSVs

    etf_ret = _make_synthetic_etf_returns(n_days=30)

    result = run_backtest(
        weights_path=weights_path,
        fno_dir=fno_dir,
        etf_returns=etf_ret,
        dry_run=True,
    )

    assert result["total_trades"] == 0
    assert result["win_rate"] == 0.0
    assert result["per_spread"] == {}


def test_run_backtest_writes_files(tmp_path):
    """run_backtest() writes both output files when dry_run=False."""
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(_make_synthetic_weights()), encoding="utf-8")

    fno_dir = tmp_path / "fno_historical"
    fno_dir.mkdir()
    _make_synthetic_fno_csvs(fno_dir)

    results_path = tmp_path / "backtest_results.json"
    summary_path = tmp_path / "backtest_summary.json"

    etf_ret = _make_synthetic_etf_returns(n_days=80)

    run_backtest(
        weights_path=weights_path,
        fno_dir=fno_dir,
        etf_returns=etf_ret,
        results_path=results_path,
        summary_path=summary_path,
        dry_run=False,
    )

    assert results_path.is_file(), "backtest_results.json was not written"
    assert summary_path.is_file(), "backtest_summary.json was not written"

    results = json.loads(results_path.read_text())
    summary = json.loads(summary_path.read_text())

    assert "period" in summary
    assert "verdict" in summary
    assert summary["verdict"] in ("PASS", "FAIL")
    assert "win_rate_pct" in summary
    assert "sharpe" in summary


def test_run_backtest_verdict_logic(tmp_path):
    """PASS requires win_rate > 55% AND sharpe > 1.0."""
    weights_path = tmp_path / "etf_optimal_weights.json"
    weights_path.write_text(json.dumps(_make_synthetic_weights()), encoding="utf-8")

    fno_dir = tmp_path / "fno_historical"
    fno_dir.mkdir()
    _make_synthetic_fno_csvs(fno_dir)

    etf_ret = _make_synthetic_etf_returns(n_days=80)

    results_path = tmp_path / "backtest_results.json"
    summary_path = tmp_path / "backtest_summary.json"

    result = run_backtest(
        weights_path=weights_path,
        fno_dir=fno_dir,
        etf_returns=etf_ret,
        results_path=results_path,
        summary_path=summary_path,
        dry_run=False,
    )

    summary = json.loads(summary_path.read_text())
    win_rate = result["win_rate"]
    sharpe = result["sharpe"]

    expected_verdict = "PASS" if (win_rate > 0.55 and sharpe > 1.0) else "FAIL"
    assert summary["verdict"] == expected_verdict
