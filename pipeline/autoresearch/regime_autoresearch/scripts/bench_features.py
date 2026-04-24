"""Ad-hoc benchmark for build_feature_matrix.

Builds a 50-ticker x 500-day synthetic panel (matching the historical
130s baseline measurement) plus NIFTY/VIX/REGIME pseudo-tickers, then
times build_feature_matrix on a single eval_date. Prints before/after
numbers for the perf rework.

Run: python -m pipeline.autoresearch.regime_autoresearch.scripts.bench_features
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.features import build_feature_matrix


def _synthetic_panel(n_tickers: int = 50, n_days: int = 500, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-01", periods=n_days)
    tickers = [f"T{i:03d}" for i in range(n_tickers)] + ["NIFTY", "VIX", "REGIME"]
    sectors = ["IT", "FIN", "ENERGY", "PHARMA", "AUTO"]
    rows = []
    for t in tickers:
        close = 100 + np.cumsum(rng.standard_normal(n_days) * 0.5)
        vol = 1e6 + rng.standard_normal(n_days) * 1e4
        sector = sectors[hash(t) % len(sectors)]
        ts = float(rng.uniform(0.3, 0.9))
        for d, c, v in zip(dates, close, vol):
            rows.append({
                "date": d, "ticker": t, "close": float(c), "volume": float(v),
                "market_cap": 1e9, "trust_score": ts, "sector": sector,
            })
    return pd.DataFrame(rows)


def main() -> None:
    panel = _synthetic_panel()
    real_tickers = [t for t in panel["ticker"].unique() if t not in ("NIFTY", "VIX", "REGIME")]
    eval_date = panel["date"].iloc[-1]

    # Warm-up (imports, pandas caches).
    _ = build_feature_matrix(panel, eval_date, real_tickers[:3])

    t0 = time.perf_counter()
    fm = build_feature_matrix(panel, eval_date, real_tickers)
    elapsed = time.perf_counter() - t0

    print(f"panel: {len(real_tickers)} tickers x 500 days + NIFTY/VIX/REGIME")
    print(f"matrix shape: {fm.shape}")
    print(f"before: 130s (historical baseline)")
    print(f"now:    {elapsed:.2f}s")
    if elapsed > 0:
        print(f"speedup vs baseline: {130.0 / elapsed:.1f}x")


if __name__ == "__main__":
    main()
