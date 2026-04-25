"""TDD for reconstruct.regime — deterministic regime regeneration.

The acid test in v2: if `regime_history.csv` is deleted from disk, this
module must reproduce its content from canonical ETF parquets + frozen
weights + frozen quintile cutpoints.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay.reconstruct import regime


def _synth_etf_bars(weights: dict[str, float], dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Build a small dict[etf -> daily bars DataFrame] for testing."""
    bars: dict[str, pd.DataFrame] = {}
    rng = np.random.default_rng(42)
    for sym in weights:
        # Random walk centred at 100; ensures finite returns.
        steps = rng.normal(0, 0.5, size=len(dates))
        closes = 100 * np.exp(np.cumsum(steps / 100))
        bars[sym] = pd.DataFrame({"date": dates, "close": closes})
    return bars


def test_regime_regen_signal_matches_phase_c_backtest_formula():
    """Our `compute_signal` must equal the canonical `_compute_signal`."""
    from pipeline.research.phase_c_backtest.regime import _compute_signal

    weights = {"brazil": 26.835, "natgas": -8.21, "silver": -3.26}
    dates = pd.date_range("2025-01-01", periods=10, freq="B")
    bars = _synth_etf_bars(weights, dates)

    target_date = dates[5].strftime("%Y-%m-%d")
    expected = _compute_signal(target_date, weights, bars)
    actual = regime.compute_signal(target_date, weights, bars)
    assert actual == pytest.approx(expected, abs=1e-9)


def test_regime_regen_zone_uses_quintile_cutpoints():
    """Zone mapping must match the frozen cutpoints, NOT the live engine's
    absolute thresholds."""
    cutpoints = {"q20": -45.73, "q40": -11.24, "q60": 17.31, "q80": 49.16}
    assert regime.signal_to_zone(-50.0, cutpoints) == "RISK-OFF"
    assert regime.signal_to_zone(-30.0, cutpoints) == "CAUTION"
    assert regime.signal_to_zone(0.0, cutpoints) == "NEUTRAL"
    assert regime.signal_to_zone(30.0, cutpoints) == "RISK-ON"
    assert regime.signal_to_zone(60.0, cutpoints) == "EUPHORIA"


def test_regime_regen_handles_boundary_inclusively_at_q80():
    cutpoints = {"q20": -45.73, "q40": -11.24, "q60": 17.31, "q80": 49.16}
    # Exact q80 → EUPHORIA per build_regime_history `_signal_to_zone_quantile`
    # ("else" branch when signal >= q80).
    assert regime.signal_to_zone(49.16, cutpoints) == "EUPHORIA"


def test_regime_regen_skips_etfs_with_no_bars_or_no_history():
    weights = {"brazil": 26.835, "natgas": -8.21}
    dates = pd.date_range("2025-01-01", periods=5, freq="B")
    # natgas has only 1 row → cannot compute return → skipped.
    bars = {
        "brazil": pd.DataFrame({"date": dates, "close": [100, 101, 102, 103, 104]}),
        "natgas": pd.DataFrame({"date": dates[:1], "close": [50.0]}),
    }
    target = dates[3].strftime("%Y-%m-%d")
    sig = regime.compute_signal(target, weights, bars)
    # Only brazil contributes: w * ((103 / 102) - 1) * 100
    expected = 26.835 * ((103.0 / 102.0) - 1) * 100
    assert sig == pytest.approx(expected, abs=1e-9)


def test_regenerate_emits_dataframe_per_window():
    """`regenerate` returns a tidy frame with one row per requested date."""
    weights = {"brazil": 26.835, "natgas": -8.21, "silver": -3.26}
    dates = pd.date_range("2025-01-01", periods=15, freq="B")
    bars = _synth_etf_bars(weights, dates)
    cutpoints = {"q20": -45.73, "q40": -11.24, "q60": 17.31, "q80": 49.16}

    window_start = dates[5]
    window_end = dates[12]
    out = regime.regenerate(
        window_start=window_start,
        window_end=window_end,
        weights=weights,
        cutpoints=cutpoints,
        etf_bars=bars,
    )
    assert set(out.columns) == {"date", "regime_zone", "signal_score"}
    # Inclusive on both ends — every business day in [start, end] that has bars.
    bar_dates = set(dates[(dates >= window_start) & (dates <= window_end)])
    assert set(pd.to_datetime(out["date"])) == bar_dates
    assert out["regime_zone"].isin(["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]).all()


def test_load_canonical_inputs_returns_weights_and_cutpoints(tmp_path: Path):
    """`load_canonical_inputs` parses the on-disk weights + cutpoints files."""
    import json
    weights_payload = {"optimal_weights": {"brazil": 26.83, "natgas": -8.21}}
    cutpoints_payload = {"q20": -45.0, "q40": -10.0, "q60": 15.0, "q80": 50.0}
    wp = tmp_path / "weights.json"
    cp = tmp_path / "cutpoints.json"
    wp.write_text(json.dumps(weights_payload))
    cp.write_text(json.dumps(cutpoints_payload))

    weights, cutpoints = regime.load_canonical_inputs(weights_path=wp, cutpoints_path=cp)
    assert weights == {"brazil": 26.83, "natgas": -8.21}
    assert cutpoints == cutpoints_payload


def test_cross_check_against_live_history_disk():
    """End-to-end: regenerate the last 30 trading days of regime_history.csv
    using on-disk weights + cutpoints + canonical parquets, and require ≥98%
    zone agreement and ≥95% signal-score agreement within 0.5 points (per
    spec §10 acceptance gate).

    This is the deterministic-reconstruction acid test.
    """
    import json
    from pipeline.autoresearch.mechanical_replay import constants as C

    weights_path = C._REPO / "pipeline" / "autoresearch" / "etf_optimal_weights.json"
    cutpoints_path = C._REPO / "pipeline" / "data" / "regime_cutpoints.json"
    if not (weights_path.exists() and cutpoints_path.exists() and C.REGIME_HISTORY_CSV.exists()):
        pytest.skip("canonical inputs missing — skipping cross-check")

    live = pd.read_csv(C.REGIME_HISTORY_CSV, parse_dates=["date"])
    if len(live) < 30:
        pytest.skip("regime_history.csv has fewer than 30 rows")
    live_window = live.tail(30).copy()
    window_start = live_window["date"].min()
    window_end = live_window["date"].max()

    weights, cutpoints = regime.load_canonical_inputs(
        weights_path=weights_path, cutpoints_path=cutpoints_path
    )
    bars = regime.load_canonical_etf_bars(weights=weights)

    out = regime.regenerate(
        window_start=window_start,
        window_end=window_end,
        weights=weights,
        cutpoints=cutpoints,
        etf_bars=bars,
    )
    out = out.rename(columns={"signal_score": "signal_regen", "regime_zone": "regime_regen"})
    merged = live_window.merge(
        out, on="date", how="inner",
        suffixes=("", "_regen"),
    )
    if len(merged) < 20:
        pytest.skip(f"only {len(merged)} overlap rows — canonical bars too thin to cross-check")

    zone_agree = (merged["regime_zone"] == merged["regime_regen"]).mean() * 100
    signal_diff = (merged["signal_score"] - merged["signal_regen"]).abs()
    signal_within_05 = (signal_diff <= 0.5).mean() * 100

    assert zone_agree >= 98.0, (
        f"Regime cross-check failed: {zone_agree:.1f}% zone agreement (threshold 98%). "
        f"Mismatches:\n{merged.loc[merged['regime_zone'] != merged['regime_regen']]}"
    )
    assert signal_within_05 >= 95.0, (
        f"Signal cross-check failed: {signal_within_05:.1f}% within 0.5 (threshold 95%). "
        f"Median |diff|: {signal_diff.median():.3f}"
    )
