"""Tests in_sample_panel.py — synthetic mini-cache + OI archive end-to-end.

Per ``feedback_no_hallucination_mandate.md``: every fixture writes real
parquets and real JSON archives to ``tmp_path``; the panel reads them like
production. NaN injection / missing-bar tests assert the row drops, not
imputation.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.research.intraday_v1 import in_sample_panel

IST = timezone(timedelta(hours=5, minutes=30))

# 21 prior trading days needed for volume_history(lookback=20) + 1 eval day.
DEFAULT_HISTORY_DAYS = 25


def _trading_dates(n: int, end: date) -> list[date]:
    """Return n consecutive weekday dates ending on ``end`` (inclusive)."""
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:  # Mon-Fri
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _make_session_bars(
    d: date, base_open: float, drift: float = 0.0, volume_seed: int = 0
) -> pd.DataFrame:
    """Build a full 09:15:00 → 15:29:00 minute bar set for one date.

    ``volume_seed`` perturbs per-minute volume so the cross-day
    cumulative-volume std is non-zero (volume_z otherwise returns NaN).
    """
    start = datetime.combine(d, datetime.min.time()).replace(
        hour=9, minute=15, tzinfo=IST
    )
    n = 375  # 09:15 .. 15:29 inclusive
    timestamps = [start + timedelta(minutes=i) for i in range(n)]
    closes = base_open + drift * np.arange(n)
    rng = np.random.default_rng(volume_seed)
    volumes = (np.arange(1, n + 1, dtype=float) * 100.0) * rng.uniform(0.5, 1.5, size=n)
    return pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        "open": closes - 0.05,
        "high": closes + 0.10,
        "low": closes - 0.10,
        "close": closes,
        "volume": volumes,
    })


def _write_cache(
    cache_dir: Path,
    sym: str,
    dates: list[date],
    base_open: float,
    drift: float = 0.0,
) -> None:
    """Concatenate per-day bars and persist to a parquet matching production schema.

    Each date receives a distinct ``volume_seed`` so the cross-day cumulative-volume
    std is non-zero — required for ``volume_z`` to be finite.
    """
    frames = [_make_session_bars(d, base_open, drift, volume_seed=i) for i, d in enumerate(dates)]
    df = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_dir / f"{sym}.parquet", index=False)


def _write_oi_archive(archive_dir: Path, dates: list[date], symbols: list[str]) -> None:
    """Write per-date OI archive JSONs in the production schema."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(dates):
        blob = {}
        for j, sym in enumerate(symbols):
            blob[sym] = {
                "symbol": sym,
                "near": {
                    "expiry": (d + timedelta(days=10)).isoformat(),
                    "call_oi": 100_000 + i * 1000 + j * 100,
                    "put_oi": 90_000 + i * 1500 + j * 50,
                },
                "next": {
                    "expiry": (d + timedelta(days=40)).isoformat(),
                    "call_oi": 80_000 + i * 800 + j * 200,
                    "put_oi": 95_000 + i * 1200 + j * 150,
                },
            }
        (archive_dir / f"{d.isoformat()}.json").write_text(
            json.dumps(blob), encoding="utf-8"
        )


@pytest.fixture
def synthetic_environment(tmp_path):
    """Build a 25-trading-day synthetic cache + OI archive for two stocks
    plus the NIFTY 50 sector reference, returning paths + last eval date."""
    end_d = date(2026, 4, 28)
    history = _trading_dates(DEFAULT_HISTORY_DAYS, end_d)

    cache_dir = tmp_path / "cache_1min"
    archive_dir = tmp_path / "oi_history_stocks"

    _write_cache(cache_dir, "RELIANCE", history, base_open=2500.0, drift=0.02)
    _write_cache(cache_dir, "TCS", history, base_open=3500.0, drift=-0.01)
    # RELIANCE -> NIFTY ENERGY; TCS -> NIFTY IT (per SECTOR_INDEX_MAP_KITE).
    _write_cache(cache_dir, "NIFTY 50", history, base_open=22500.0, drift=0.005)
    _write_cache(cache_dir, "NIFTY ENERGY", history, base_open=30000.0, drift=0.01)
    _write_cache(cache_dir, "NIFTY IT", history, base_open=35000.0, drift=-0.005)
    _write_oi_archive(archive_dir, history, ["RELIANCE", "TCS"])

    return {
        "cache_dir": cache_dir,
        "archive_dir": archive_dir,
        "history": history,
        "eval_dates": history[-3:],  # last 3 trading days
    }


def test_assemble_panel_returns_real_features(synthetic_environment):
    """Smoke test: synthetic environment yields a non-empty panel with all
    six features finite and the label populated.
    """
    env = synthetic_environment
    df = in_sample_panel.assemble_panel(
        eval_dates=env["eval_dates"],
        universe_symbols=["RELIANCE", "TCS"],
        pool="stocks",
        cache_dir=env["cache_dir"],
        archive_dir=env["archive_dir"],
    )
    assert not df.empty, "panel should have at least one row on synthetic data"
    expected_cols = {"date", "instrument", "f1", "f2", "f3", "f4", "f5", "f6", "next_return_pct"}
    assert expected_cols.issubset(set(df.columns))
    # All feature values finite — drop semantics confirmed.
    for col in ("f1", "f2", "f3", "f4", "f5", "f6", "next_return_pct"):
        assert df[col].notna().all(), f"col {col} has NaN — should have been dropped"
        assert np.isfinite(df[col]).all()


def test_drops_rows_with_any_nan_feature(synthetic_environment, monkeypatch):
    """Inject NaN into one feature and confirm that row is dropped."""
    env = synthetic_environment

    real_compute_all = in_sample_panel.features.compute_all

    def nan_one_feature(*args, **kwargs):
        out = real_compute_all(*args, **kwargs)
        out["volume_z"] = float("nan")
        return out

    monkeypatch.setattr(in_sample_panel.features, "compute_all", nan_one_feature)
    df = in_sample_panel.assemble_panel(
        eval_dates=env["eval_dates"],
        universe_symbols=["RELIANCE", "TCS"],
        pool="stocks",
        cache_dir=env["cache_dir"],
        archive_dir=env["archive_dir"],
    )
    # Every row would have had volume_z = NaN, so panel must be empty.
    assert df.empty, "rows with any NaN feature must be dropped, not imputed"


def test_drops_rows_with_missing_label(synthetic_environment, monkeypatch):
    """If the 14:30 bar is missing for a (date, instrument), row must be dropped."""
    env = synthetic_environment
    # Surgically remove every 14:30 bar from the RELIANCE cache.
    cache_path = env["cache_dir"] / "RELIANCE.parquet"
    df_bars = pd.read_parquet(cache_path)
    mask_keep = ~(
        (df_bars["timestamp"].dt.hour == 14) & (df_bars["timestamp"].dt.minute == 30)
    )
    df_bars[mask_keep].to_parquet(cache_path, index=False)

    df = in_sample_panel.assemble_panel(
        eval_dates=env["eval_dates"],
        universe_symbols=["RELIANCE", "TCS"],
        pool="stocks",
        cache_dir=env["cache_dir"],
        archive_dir=env["archive_dir"],
    )
    # RELIANCE rows must all be gone; TCS rows survive.
    assert (df["instrument"] != "RELIANCE").all()
    assert (df["instrument"] == "TCS").any()


def test_drops_rows_with_missing_pcr(tmp_path):
    """If only 1 OI archive exists before eval_date, PCR is unresolvable and
    the date contributes ZERO rows (anchors require >= 2 prior archives).
    """
    end_d = date(2026, 4, 28)
    history = _trading_dates(DEFAULT_HISTORY_DAYS, end_d)
    cache_dir = tmp_path / "cache_1min"
    archive_dir = tmp_path / "oi_history_stocks"

    _write_cache(cache_dir, "RELIANCE", history, base_open=2500.0, drift=0.02)
    _write_cache(cache_dir, "NIFTY 50", history, base_open=22500.0, drift=0.005)
    _write_cache(cache_dir, "NIFTY ENERGY", history, base_open=30000.0, drift=0.01)
    # Only ONE OI archive — too early for the PCR producer.
    _write_oi_archive(archive_dir, history[:1], ["RELIANCE"])

    df = in_sample_panel.assemble_panel(
        eval_dates=[history[1]],  # second day, only 1 prior archive available
        universe_symbols=["RELIANCE"],
        pool="stocks",
        cache_dir=cache_dir,
        archive_dir=archive_dir,
    )
    assert df.empty


def test_label_is_signed_pct_change_from_0930_to_1430(tmp_path):
    """Synthetic bars with 09:30 close = 100, 14:30 close = 102 -> label = +2%.

    Builds a per-day session with varied volumes (so volume_z is finite) and
    plants 09:30=100 / 14:30=102 on the eval date. Sector reference NIFTY 50
    is a generic walk so rs_vs_sector resolves.
    """
    end_d = date(2026, 4, 28)
    history = _trading_dates(DEFAULT_HISTORY_DAYS, end_d)
    cache_dir = tmp_path / "cache_1min"
    archive_dir = tmp_path / "oi_history_stocks"

    _write_oi_archive(archive_dir, history, ["FOO"])

    eval_d = history[-1]
    rows = []
    for di, d in enumerate(history):
        # Use varied volumes per-day so volume_z's std > 0.
        rng = np.random.default_rng(di)
        for i in range(375):
            t = datetime.combine(d, datetime.min.time()).replace(
                hour=9, minute=15, tzinfo=IST
            ) + timedelta(minutes=i)
            if d == eval_d:
                if t.time() == datetime.strptime("09:30", "%H:%M").time():
                    close = 100.0
                elif t.time() == datetime.strptime("14:30", "%H:%M").time():
                    close = 102.0
                else:
                    close = 100.0 + (i - 15) * 0.001
            else:
                close = 100.0 + i * 0.0001
            volume = (100.0 + i) * float(rng.uniform(0.5, 1.5))
            rows.append({
                "timestamp": t, "open": close, "high": close + 0.05,
                "low": close - 0.05, "close": close, "volume": volume,
            })
    df_bars = pd.DataFrame(rows)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df_bars.to_parquet(cache_dir / "FOO.parquet", index=False)

    # Sector reference (NIFTY 50) — needed by rs_vs_sector. Per the SECTOR_INDEX_MAP_KITE
    # default, an unmapped symbol like FOO falls back to "NIFTY 50".
    _write_cache(cache_dir, "NIFTY 50", history, base_open=22500.0, drift=0.005)

    df = in_sample_panel.assemble_panel(
        eval_dates=[eval_d],
        universe_symbols=["FOO"],
        pool="stocks",
        cache_dir=cache_dir,
        archive_dir=archive_dir,
    )
    assert not df.empty, "synthetic row should survive — volume_z and PCR are finite"
    assert df.iloc[0]["next_return_pct"] == pytest.approx(2.0, abs=1e-6)
