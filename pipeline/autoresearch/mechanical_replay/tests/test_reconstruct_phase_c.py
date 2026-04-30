"""TDD for reconstruct.phase_c — deterministic Phase C roster regeneration.

The acid test: feed canonical bars + regenerated regime tags → emit a
roster of (date, ticker, classification, z_score, trade_rec, regime).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.autoresearch.mechanical_replay.reconstruct import phase_c


def _synth_bars(n_days: int, seed: int = 0, base_drift: float = 0.0) -> pd.DataFrame:
    """Synthetic OHLC daily bars centred at 100."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    rets = rng.normal(base_drift, 0.015, size=n_days)
    closes = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame({
        "date": dates, "open": closes, "high": closes * 1.005,
        "low": closes * 0.995, "close": closes, "volume": 1_000_000,
    })


def _synth_regime_map(dates: pd.DatetimeIndex, regime: str = "NEUTRAL") -> dict[str, str]:
    return {d.strftime("%Y-%m-%d"): regime for d in dates}


def test_phase_c_regen_returns_roster_dataframe():
    """The basic contract: regenerate emits a tidy roster frame."""
    universe_bars = {
        "RELI": _synth_bars(800, seed=1),
        "INFY": _synth_bars(800, seed=2),
    }
    all_dates = universe_bars["RELI"]["date"]
    regime_by_date = _synth_regime_map(all_dates, "NEUTRAL")
    window_start = all_dates.iloc[-30]
    window_end = all_dates.iloc[-2]

    out = phase_c.regenerate(
        window_start=window_start,
        window_end=window_end,
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
    )
    expected_cols = {"date", "ticker", "classification", "z_score", "trade_rec", "regime"}
    assert expected_cols.issubset(out.columns)
    if not out.empty:
        assert out["regime"].isin({"RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"}).all()
        assert out["classification"].isin({
            "OPPORTUNITY_LAG", "OPPORTUNITY_OVERSHOOT", "POSSIBLE_OPPORTUNITY",
            "WARNING", "CONFIRMED_WARNING", "UNCERTAIN",
        }).all()


def test_phase_c_regen_emits_lag_only_when_requested():
    universe_bars = {
        "RELI": _synth_bars(800, seed=1),
        "INFY": _synth_bars(800, seed=2),
        "TCS": _synth_bars(800, seed=3),
    }
    all_dates = universe_bars["RELI"]["date"]
    regime_by_date = _synth_regime_map(all_dates, "NEUTRAL")

    out = phase_c.regenerate(
        window_start=all_dates.iloc[-30],
        window_end=all_dates.iloc[-2],
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
        actionable_only=True,
    )
    if not out.empty:
        assert (out["classification"] == "OPPORTUNITY_LAG").all()
        # trade_rec must be LONG or SHORT for all actionable rows.
        assert out["trade_rec"].isin({"LONG", "SHORT"}).all()


def test_phase_c_regen_skips_dates_with_no_regime():
    """Dates missing from the regime map are silently skipped."""
    universe_bars = {"RELI": _synth_bars(800, seed=1)}
    all_dates = universe_bars["RELI"]["date"]
    # Regime map covers only the first half — the back half should be skipped.
    regime_by_date = _synth_regime_map(all_dates[:400], "NEUTRAL")
    out = phase_c.regenerate(
        window_start=all_dates.iloc[-30],
        window_end=all_dates.iloc[-2],
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
    )
    # All window dates fall in the unmapped half → empty output.
    assert out.empty


def test_trading_days_excludes_nse_holidays():
    """Regression for the 2026-04-29 phantom-holiday bug.

    `pd.bdate_range` filters weekends but not gazetted NSE holidays. The replay
    engine fired Phase C signals on 5 holidays, producing 248 FETCH_FAILED
    rows. The fix replaces `pd.bdate_range` with `_trading_days`, which
    additionally consults `pipeline.trading_calendar.is_trading_day`.

    Pinned date: Holi 2026-03-10 — NSE is closed, output must not include it.
    """
    holi = pd.Timestamp("2026-03-10")
    days = phase_c._trading_days(holi - pd.Timedelta(days=2), holi + pd.Timedelta(days=2))
    day_strs = {d.strftime("%Y-%m-%d") for d in days}
    assert "2026-03-10" not in day_strs, "Holi must be excluded — NSE closed"
    # Sanity check: surrounding weekdays that are NOT holidays should be present.
    assert "2026-03-09" in day_strs  # Monday before Holi
    assert "2026-03-11" in day_strs  # Wednesday after Holi


def test_trading_days_excludes_weekends_and_holidays_together():
    """Multiple consecutive non-trading days collapse cleanly."""
    # 2026-03-30 (Mon, Eid), 2026-03-31 (Tue, Mahavir Jayanti) are both holidays.
    days = phase_c._trading_days(
        pd.Timestamp("2026-03-27"), pd.Timestamp("2026-04-01")
    )
    day_strs = {d.strftime("%Y-%m-%d") for d in days}
    assert "2026-03-30" not in day_strs
    assert "2026-03-31" not in day_strs
    # 2026-03-28/29 are weekend (already filtered by bdate_range).
    assert "2026-03-27" in day_strs  # Friday
    assert "2026-04-01" in day_strs  # Wednesday after long weekend


def test_phase_c_regen_signal_id_matches_live_format():
    """Roster row should carry a signal_id of the form BRK-<date>-<symbol>."""
    universe_bars = {
        "RELI": _synth_bars(800, seed=11),
        "INFY": _synth_bars(800, seed=12),
    }
    all_dates = universe_bars["RELI"]["date"]
    regime_by_date = _synth_regime_map(all_dates, "NEUTRAL")
    out = phase_c.regenerate(
        window_start=all_dates.iloc[-30],
        window_end=all_dates.iloc[-2],
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
    )
    if not out.empty:
        sample_row = out.iloc[0]
        date_str = pd.Timestamp(sample_row["date"]).strftime("%Y-%m-%d")
        expected_id = f"BRK-{date_str}-{sample_row['ticker']}"
        assert sample_row["signal_id"] == expected_id


def test_phase_c_regen_z_score_finite_and_signed():
    """z_score must be a real-valued float (no NaN, no inf) for kept rows."""
    universe_bars = {
        "RELI": _synth_bars(800, seed=21),
        "INFY": _synth_bars(800, seed=22),
        "TCS": _synth_bars(800, seed=23),
    }
    all_dates = universe_bars["RELI"]["date"]
    regime_by_date = _synth_regime_map(all_dates, "NEUTRAL")
    out = phase_c.regenerate(
        window_start=all_dates.iloc[-30],
        window_end=all_dates.iloc[-2],
        universe_bars=universe_bars,
        regime_by_date=regime_by_date,
    )
    if not out.empty:
        assert out["z_score"].apply(np.isfinite).all()


def test_load_pcr_history_returns_per_day_per_ticker_map(tmp_path):
    """Reads {date}.parquet files into a {date_str: {ticker: pcr}} map."""
    df = pd.DataFrame({
        "symbol": ["RELI", "INFY", "TCS"],
        "pcr": [1.45, 0.62, 1.05],
    })
    df.to_parquet(tmp_path / "2026-04-15.parquet")
    out = phase_c.load_pcr_history(
        pd.Timestamp("2026-04-13"),
        pd.Timestamp("2026-04-17"),
        pcr_dir=tmp_path,
    )
    assert "2026-04-15" in out
    assert out["2026-04-15"]["RELI"] == pytest.approx(1.45)
    assert out["2026-04-15"]["INFY"] == pytest.approx(0.62)


def test_load_pcr_history_returns_empty_when_dir_missing(tmp_path):
    """Missing directory returns empty map (caller treats absent → NEUTRAL)."""
    out = phase_c.load_pcr_history(
        pd.Timestamp("2026-04-13"),
        pd.Timestamp("2026-04-17"),
        pcr_dir=tmp_path / "does_not_exist",
    )
    assert out == {}
