"""Tests for v2 construction-matched null-basket hurdle (Task 2)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _synth_panel(n_tickers=30, n_days=500, seed=0):
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    dates = pd.bdate_range("2020-04-23", periods=n_days)
    rows = []
    for tk in tickers:
        price = 100.0
        for d in dates:
            price *= (1.0 + rng.normal(0, 0.012))
            rows.append({"date": d, "ticker": tk, "close": price,
                         "volume": 1_000_000.0, "sector": "X"})
    return pd.DataFrame(rows)


def test_hurdle_table_has_1200_rows_and_required_columns():
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table,
    )
    panel = _synth_panel()
    event_dates_by_regime = {
        r: pd.DatetimeIndex(panel["date"].unique()[50:200:3])
        for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")
    }
    holdout_event_dates_by_regime = {
        r: pd.DatetimeIndex(panel["date"].unique()[200:400:5])
        for r in event_dates_by_regime
    }
    table = compute_hurdle_table(
        panel=panel,
        event_dates_by_regime=event_dates_by_regime,
        holdout_event_dates_by_regime=holdout_event_dates_by_regime,
        n_trials=20,
    )
    assert len(table) == 1200, f"Expected 1200 rows, got {len(table)}"
    for col in (
        "construction", "k", "hold_horizon", "regime", "window",
        "hurdle_sharpe_median", "hurdle_sharpe_p95",
        "n_events", "n_trials", "seed", "generated_at_sha",
    ):
        assert col in table.columns, f"missing column {col!r}"
    assert set(table["window"].unique()) == {"train_val", "holdout"}


def test_hurdle_table_is_reproducible_from_seed():
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table,
    )
    panel = _synth_panel(seed=42)
    ev = {r: pd.DatetimeIndex(panel["date"].unique()[50:150:4])
          for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")}
    hv = {r: pd.DatetimeIndex(panel["date"].unique()[200:300:5])
          for r in ev}
    t1 = compute_hurdle_table(panel, ev, hv, n_trials=10)
    t2 = compute_hurdle_table(panel, ev, hv, n_trials=10)
    pd.testing.assert_frame_equal(
        t1.drop(columns=["generated_at_sha"]).reset_index(drop=True),
        t2.drop(columns=["generated_at_sha"]).reset_index(drop=True),
        check_exact=False, rtol=1e-10,
    )


def test_load_null_basket_hurdle_valid_tuple(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table, load_null_basket_hurdle,
    )
    panel = _synth_panel()
    ev = {r: pd.DatetimeIndex(panel["date"].unique()[50:100:5])
          for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")}
    hv = {r: pd.DatetimeIndex(panel["date"].unique()[150:200:5]) for r in ev}
    t = compute_hurdle_table(panel, ev, hv, n_trials=5)
    path = tmp_path / "hurdles.parquet"
    t.to_parquet(path)
    v = load_null_basket_hurdle(
        "top_k", 10, 5, "NEUTRAL", window="train_val", table_path=path,
    )
    assert isinstance(v, float)


def test_load_null_basket_hurdle_raises_on_unknown_tuple(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        compute_hurdle_table, load_null_basket_hurdle,
    )
    panel = _synth_panel()
    ev = {r: pd.DatetimeIndex(panel["date"].unique()[50:100:5])
          for r in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")}
    hv = {r: pd.DatetimeIndex(panel["date"].unique()[150:200:5]) for r in ev}
    t = compute_hurdle_table(panel, ev, hv, n_trials=5)
    path = tmp_path / "hurdles.parquet"
    t.to_parquet(path)
    with pytest.raises(KeyError):
        load_null_basket_hurdle(
            "top_k", 999, 5, "NEUTRAL",
            window="train_val", table_path=path,
        )


def test_load_null_basket_hurdle_raises_on_missing_file(tmp_path):
    from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
        load_null_basket_hurdle,
    )
    with pytest.raises(FileNotFoundError):
        load_null_basket_hurdle(
            "top_k", 10, 5, "NEUTRAL",
            window="train_val",
            table_path=tmp_path / "does_not_exist.parquet",
        )
