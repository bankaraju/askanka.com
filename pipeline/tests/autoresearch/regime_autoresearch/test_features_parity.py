"""Parity test: `build_feature_matrix` (fast path) must match the per-feature
slow-path functions bit-for-bit on every (ticker, feature) cell.

This guard exists because the fast path in `features.py` is a vectorised
alternate implementation of the same 20 feature semantics. If anyone edits
one side without the other, this test catches the drift before a live run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.features import (
    FEATURE_FUNCS, build_feature_matrix,
)


def _panel(n_tickers: int = 30, n_days: int = 200, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    base_tickers = [f"T{i:02d}" for i in range(n_tickers)]
    all_tickers = base_tickers + ["NIFTY", "VIX", "REGIME"]
    sectors = ["IT", "FIN", "ENERGY", "PHARMA", "AUTO"]
    rows = []
    for i, t in enumerate(all_tickers):
        close = 100 + np.cumsum(rng.standard_normal(n_days) * 0.5)
        vol = 1e6 + rng.standard_normal(n_days) * 1e4
        sector = sectors[i % len(sectors)]
        trust = float(rng.uniform(0.3, 0.9))
        for d, c, v in zip(dates, close, vol):
            rows.append({
                "date": d, "ticker": t, "close": float(c), "volume": float(v),
                "market_cap": 1e9 + (i * 1e7), "trust_score": trust, "sector": sector,
            })
    return pd.DataFrame(rows)


def _assert_equal_or_both_nan(a: float, b: float, feature: str, ticker: str) -> None:
    if pd.isna(a) and pd.isna(b):
        return
    assert pd.notna(a) and pd.notna(b), (
        f"NaN mismatch for {feature}/{ticker}: fast={a!r}, slow={b!r}"
    )
    # abs tolerance is strict: both paths should be doing the same float ops.
    assert abs(a - b) < 1e-10, (
        f"Value mismatch for {feature}/{ticker}: fast={a!r}, slow={b!r}, "
        f"diff={a - b!r}"
    )


def test_fast_path_matches_slow_path_every_cell():
    panel = _panel()
    eval_date = panel["date"].iloc[170]
    base_tickers = [t for t in panel["ticker"].unique() if t not in ("NIFTY", "VIX", "REGIME")]

    fast = build_feature_matrix(panel, eval_date, base_tickers)

    for ticker in base_tickers:
        for feature, fn in FEATURE_FUNCS.items():
            slow_val = float(fn(panel, ticker, eval_date))
            fast_val = float(fast.loc[ticker, feature])
            _assert_equal_or_both_nan(fast_val, slow_val, feature, ticker)


def test_fast_path_matches_slow_path_on_empty_panel():
    empty = pd.DataFrame(columns=["date", "ticker", "close", "volume",
                                    "market_cap", "trust_score", "sector"])
    fast = build_feature_matrix(empty, pd.Timestamp("2024-01-01"), ["T0", "T1"])
    assert list(fast.index) == ["T0", "T1"]
    for ticker in ["T0", "T1"]:
        for feature in FEATURE_FUNCS:
            v = fast.loc[ticker, feature]
            assert isinstance(v, float) and np.isnan(v), (
                f"{feature}/{ticker} expected NaN on empty panel, got {v!r}"
            )
