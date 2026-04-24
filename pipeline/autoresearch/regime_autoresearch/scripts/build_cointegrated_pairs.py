"""Engle-Granger cointegration within broad sectors on the train window only.

Uses `load_sector_map()` from overshoot_reversion_backtest to build the full
ticker->sector mapping (~211 tickers across ~17 clean sectors). The plan
originally pointed at BROAD_SECTOR (industry->sector dict, 42 entries) which
yielded only 11 small buckets; the proper load_sector_map reads per-ticker
indianapi_stock.json and produces the full panel.

Train window is the autoresearch TRAIN_VAL window (2021-04-23 -> 2024-04-22).
We never test on holdout data, so this artifact is causal by construction.

Path note: FNO_DIR is pipeline/data/fno_historical/ (213 CSVs), not
pipeline/data/india_historical/fno_stocks/ which does not exist. Matches
pipeline.autoresearch.overshoot_reversion_backtest._FNO_DIR.

CSV schema note: the F&O CSVs use capitalized columns (Date, Close, ...);
we lowercase on read.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from pipeline.autoresearch.overshoot_reversion_backtest import load_sector_map
from pipeline.autoresearch.regime_autoresearch.constants import (
    TRAIN_VAL_START, TRAIN_VAL_END,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FNO_DIR = REPO_ROOT / "pipeline/data/fno_historical"
OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json"


def _close_series(ticker: str) -> pd.Series | None:
    p = FNO_DIR / f"{ticker}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns or "close" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df[(df["date"] >= TRAIN_VAL_START) & (df["date"] <= TRAIN_VAL_END)]
    if df.empty or df["close"].isna().mean() > 0.1:
        return None
    return df.set_index("date")["close"]


def _sector_buckets() -> dict[str, list[str]]:
    """ticker->sector buckets. Drops Unmapped and fine "Other:..." leaves."""
    mapping = load_sector_map()
    buckets: dict[str, list[str]] = {}
    for t, s in mapping.items():
        if s == "Unmapped" or s.startswith("Other:"):
            continue
        buckets.setdefault(s, []).append(t)
    return {s: sorted(tickers) for s, tickers in buckets.items() if len(tickers) >= 2}


def main() -> int:
    buckets = _sector_buckets()
    results = []
    for sector, tickers in buckets.items():
        n_pairs = len(tickers) * (len(tickers) - 1) // 2
        print(f"{sector}: {len(tickers)} tickers, {n_pairs} pairs")
        for a, b in itertools.combinations(tickers, 2):
            s_a, s_b = _close_series(a), _close_series(b)
            if s_a is None or s_b is None:
                continue
            joined = pd.concat([s_a, s_b], axis=1).dropna()
            if len(joined) < 120:
                continue
            try:
                t_stat, p_val, _ = coint(joined.iloc[:, 0], joined.iloc[:, 1])
            except Exception:
                continue
            if p_val < 0.05:
                results.append({
                    "pair_id": f"{a}_{b}",
                    "leg_a": a,
                    "leg_b": b,
                    "sector": sector,
                    "coint_t": round(float(t_stat), 4),
                    "coint_p": round(float(p_val), 6),
                    "n_obs_train": int(len(joined)),
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pairs": results, "train_window": [TRAIN_VAL_START, TRAIN_VAL_END]},
                              indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(results)} cointegrated pairs to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
