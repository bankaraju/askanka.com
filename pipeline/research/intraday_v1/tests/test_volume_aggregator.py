"""Tests for volume_aggregator — the real per-(instrument, minute) cumulative
volume mean/std producer. Replaces the synthetic stub previously fed to feature 3.

Hard contract: real persisted parquet input, strict PIT, no defaults, no
extrapolation. Insufficient history must RAISE (not return zeros)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import volume_aggregator
from pipeline.research.intraday_v1.volume_aggregator import (
    SESSION_MINUTES,
    VolumeAggregatorError,
    build_volume_history,
    produce_all,
)


def _make_session(trading_date: date, volumes_per_minute: List[float]) -> pd.DataFrame:
    """Build a synthetic 375-row session for ``trading_date`` with the given
    per-minute volumes. Timestamps are 09:15:00 ... 15:29:00 IST."""
    n = len(volumes_per_minute)
    base = pd.Timestamp(trading_date).tz_localize("Asia/Kolkata") + pd.Timedelta("9h15m")
    timestamps = [base + pd.Timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": volumes_per_minute,
    })


def _write_synthetic_cache(
    cache_dir: Path,
    symbol: str,
    n_days: int,
    eval_date: date,
    per_day_volumes: List[List[float]] = None,
    minutes_per_day: int = SESSION_MINUTES,
) -> None:
    """Write a synthetic <symbol>.parquet covering ``n_days`` consecutive
    trading days ending the day before ``eval_date``.

    ``per_day_volumes[d][m]`` is the volume for day ``d`` minute ``m``.
    If ``None``, a deterministic pattern ``volume = (d+1) * (m+1) * 10`` is used,
    which makes hand-computation of moments simple."""
    sessions = []
    # Walk back from eval_date - 1 by n_days; pretend every weekday is a trading day.
    # Use plain calendar days (Mon-Fri) to keep the synthetic deterministic.
    days_collected = 0
    cursor = eval_date - timedelta(days=1)
    cal_dates: List[date] = []
    while days_collected < n_days:
        if cursor.weekday() < 5:  # Mon-Fri
            cal_dates.append(cursor)
            days_collected += 1
        cursor -= timedelta(days=1)
    cal_dates.reverse()  # chronological

    for d_idx, td in enumerate(cal_dates):
        if per_day_volumes is None:
            vols = [(d_idx + 1) * (m + 1) * 10.0 for m in range(minutes_per_day)]
        else:
            vols = per_day_volumes[d_idx]
        sessions.append(_make_session(td, vols))

    df = pd.concat(sessions, ignore_index=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_dir / f"{symbol}.parquet", index=False)


def test_build_volume_history_returns_per_minute_moments(tmp_path):
    """Synthetic 20-day cache: confirm output has 375 rows, all idx 0..374,
    and the mean/std at minute 0 match hand-computed values."""
    cache_dir = tmp_path / "cache_1min"
    eval_date = date(2026, 5, 15)
    # 20 weekday sessions ending the weekday before eval_date.
    _write_synthetic_cache(cache_dir, "TESTSYM", n_days=20, eval_date=eval_date)

    hist = build_volume_history("TESTSYM", cache_dir, eval_date, lookback_days=20)

    # Shape contract.
    assert len(hist) == SESSION_MINUTES == 375
    assert list(hist["minute_of_day_idx"]) == list(range(375))
    assert set(hist.columns) == {
        "minute_of_day_idx", "mean_cum_volume_20d", "std_cum_volume_20d"
    }

    # Hand-compute minute 0: cum_volume on day d at minute 0 = (d+1)*1*10 = 10*(d+1).
    # Across d=0..19 the mean is 10 * mean(1..20) = 10 * 10.5 = 105.0.
    # Population std ddof=0: 10 * std(1..20, ddof=0) = 10 * sqrt(((1-10.5)^2+...+(20-10.5)^2)/20).
    expected_day_values = np.arange(1, 21, dtype=float)  # multipliers (d+1)
    expected_mean_min0 = 10.0 * expected_day_values.mean()
    expected_std_min0 = 10.0 * expected_day_values.std(ddof=0)

    row0 = hist[hist["minute_of_day_idx"] == 0].iloc[0]
    assert row0["mean_cum_volume_20d"] == pytest.approx(expected_mean_min0)
    assert row0["std_cum_volume_20d"] == pytest.approx(expected_std_min0)

    # Minute 1: cum_volume on day d = (d+1)*1*10 + (d+1)*2*10 = 30*(d+1).
    # Mean across days = 30 * mean(1..20) = 30 * 10.5 = 315.
    row1 = hist[hist["minute_of_day_idx"] == 1].iloc[0]
    assert row1["mean_cum_volume_20d"] == pytest.approx(30.0 * 10.5)

    # All means and stds must be strictly positive (no NaN, no zero) on this
    # fully-populated synthetic input.
    assert (hist["mean_cum_volume_20d"] > 0).all()
    assert (hist["std_cum_volume_20d"] > 0).all()


def test_excludes_eval_date_itself_pit_correct(tmp_path):
    """If the cache contains rows for eval_date, those rows must be excluded
    from the aggregation. PIT correctness — cannot peek at today."""
    cache_dir = tmp_path / "cache_1min"
    eval_date = date(2026, 5, 15)  # a Friday

    # Write 20 prior weekdays plus eval_date itself with VERY large volumes
    # that would distort the result if peeked.
    _write_synthetic_cache(cache_dir, "TESTSYM", n_days=20, eval_date=eval_date)

    # Append eval_date rows with absurd volumes.
    df_existing = pd.read_parquet(cache_dir / "TESTSYM.parquet")
    eval_session = _make_session(eval_date, [1_000_000_000.0] * SESSION_MINUTES)
    df_combined = pd.concat([df_existing, eval_session], ignore_index=True)
    df_combined.to_parquet(cache_dir / "TESTSYM.parquet", index=False)

    hist = build_volume_history("TESTSYM", cache_dir, eval_date, lookback_days=20)

    # If eval_date had been included, mean at minute 0 would explode toward
    # ~50M+; with strict PIT exclusion it stays at the original 105.0.
    expected_mean_min0 = 10.0 * np.arange(1, 21, dtype=float).mean()
    row0 = hist[hist["minute_of_day_idx"] == 0].iloc[0]
    assert row0["mean_cum_volume_20d"] == pytest.approx(expected_mean_min0)
    # eval_date had per-minute volume = 1e9. If it had been included, the
    # mean at minute 0 would be at least (1e9)/21 ≈ 4.76e7. Strict PIT keeps
    # the minute-0 mean at 105.0 — well below any peek-leak threshold.
    assert row0["mean_cum_volume_20d"] < 1e6
    # Last-minute mean across pure synthetic days (no peek) caps at
    # 10 * 374*375/2 * 21/2 / 20 ≈ 7.4M. With eval_date peeked it would
    # be at least (1e9 * 375)/21 ≈ 1.78e10 — orders of magnitude larger.
    assert hist["mean_cum_volume_20d"].max() < 1e8


def test_raises_when_insufficient_history(tmp_path):
    """5 trading days < lookback=20 → VolumeAggregatorError, no defaults."""
    cache_dir = tmp_path / "cache_1min"
    eval_date = date(2026, 5, 15)
    _write_synthetic_cache(cache_dir, "TESTSYM", n_days=5, eval_date=eval_date)

    with pytest.raises(VolumeAggregatorError, match=r"insufficient history.*5/20"):
        build_volume_history("TESTSYM", cache_dir, eval_date, lookback_days=20)


def test_raises_when_cache_missing(tmp_path):
    """Non-existent symbol cache → VolumeAggregatorError('no cache for ...')."""
    cache_dir = tmp_path / "cache_1min"
    cache_dir.mkdir()
    with pytest.raises(VolumeAggregatorError, match=r"no cache for NOPE"):
        build_volume_history("NOPE", cache_dir, date(2026, 5, 15), lookback_days=20)


def test_no_synthetic_fallback_on_empty_history(tmp_path):
    """File exists but is empty (0 rows) → VolumeAggregatorError, no defaulting."""
    cache_dir = tmp_path / "cache_1min"
    cache_dir.mkdir()
    empty = pd.DataFrame({
        "timestamp": pd.to_datetime([], utc=True).tz_convert("Asia/Kolkata"),
        "open": pd.Series([], dtype=float),
        "high": pd.Series([], dtype=float),
        "low": pd.Series([], dtype=float),
        "close": pd.Series([], dtype=float),
        "volume": pd.Series([], dtype=float),
    })
    empty.to_parquet(cache_dir / "EMPTYSYM.parquet", index=False)

    with pytest.raises(VolumeAggregatorError, match=r"empty cache"):
        build_volume_history("EMPTYSYM", cache_dir, date(2026, 5, 15), lookback_days=20)


def test_produce_all_skips_failures_continues(tmp_path):
    """3 symbols where one has insufficient history: 2 written, 1 skipped,
    summary lists the skip with reason."""
    cache_dir = tmp_path / "cache_1min"
    out_dir = tmp_path / "volume_history"
    eval_date = date(2026, 5, 15)

    _write_synthetic_cache(cache_dir, "GOOD1", n_days=20, eval_date=eval_date)
    _write_synthetic_cache(cache_dir, "GOOD2", n_days=22, eval_date=eval_date)
    _write_synthetic_cache(cache_dir, "SHORTSYM", n_days=5, eval_date=eval_date)

    summary = produce_all(cache_dir, out_dir, eval_date, lookback_days=20)

    assert summary["written"] == 2
    assert summary["lookback_days"] == 20
    assert summary["date"] == eval_date.isoformat()
    skipped = summary["skipped"]
    assert len(skipped) == 1
    skipped_sym, skipped_reason = skipped[0]
    assert skipped_sym == "SHORTSYM"
    assert "insufficient history" in skipped_reason
    assert "5/20" in skipped_reason

    # Real files exist for the two qualifying symbols.
    assert (out_dir / "volume_history_GOOD1.parquet").exists()
    assert (out_dir / "volume_history_GOOD2.parquet").exists()
    assert not (out_dir / "volume_history_SHORTSYM.parquet").exists()
    # And the GOOD1 file has real, non-stub numbers.
    g1 = pd.read_parquet(out_dir / "volume_history_GOOD1.parquet")
    assert len(g1) == SESSION_MINUTES
    assert (g1["mean_cum_volume_20d"] > 0).all()
