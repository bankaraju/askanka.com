"""Produces pipeline/data/regime_history.csv via the existing backfill.

Reuses pipeline.research.phase_c_backtest:
- `regime._signal_to_zone` and `regime._compute_signal` — the canonical
   zone-mapping functions used by the live engine (cannot drift).

Weights live at pipeline/autoresearch/etf_optimal_weights.json (NOT
pipeline/data/…). ETF symbol keys are lowercase basket names
(brazil, natgas, silver, india_etf, …), each matching a parquet filename
under pipeline/data/research/phase_c/daily_bars/.

Self-healing ETF cache (yfinance backfill)
------------------------------------------
Before this builder runs, many of the 20 ETF parquets in
pipeline/data/research/phase_c/daily_bars/ were empty — Phase C work
populated Indian-equity parquets ad-hoc but most global ETFs were
untouched. `_load_etf_bars` now self-heals the cache: when a parquet is
empty or its coverage starts after 2021-04-23, it refetches via yfinance
using the `GLOBAL_ETFS` alias map from etf_reoptimize and writes the
result back to the parquet cache. Every downstream consumer of
phase_c/daily_bars benefits.

Non-yfinance aliases (india_vix_daily, dii_net_daily, fii_net_daily) are
NOT in GLOBAL_ETFS; their backfill is out of scope for this script and
_compute_signal skips them gracefully. Their weights are <0.03, so their
absence from historical signal has negligible impact.

KNOWN CAVEAT: this applies current optimal weights to historical returns.
The zone mapping function is causal, but the weights themselves were
selected using data that includes the historical window. A v2 improvement
would be rolling-weights-recomputed-quarterly. For v1 we accept this and
document it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS
from pipeline.research.phase_c_backtest import paths as phase_c_paths
from pipeline.research.phase_c_backtest.regime import _signal_to_zone, _compute_signal

REPO_ROOT = Path(__file__).resolve().parents[4]
WEIGHTS_PATH = REPO_ROOT / "pipeline/autoresearch/etf_optimal_weights.json"
OUT_CSV = REPO_ROOT / "pipeline/data/regime_history.csv"
START = "2021-04-23"
BACKFILL_START = pd.Timestamp("2020-04-23")  # 1yr buffer before START for rolling features
MIN_COVERAGE_DATE = pd.Timestamp("2021-04-23")


def _yfinance_backfill_one(alias: str) -> pd.DataFrame | None:
    """Fetch daily OHLCV for one ETF alias via yfinance, return DataFrame or None.

    alias is a GLOBAL_ETFS key (brazil, natgas, silver, …).
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        print("error: yfinance not installed — `pip install yfinance`", file=sys.stderr)
        return None
    ticker_mapped = GLOBAL_ETFS.get(alias)
    if ticker_mapped is None:
        print(f"warn: alias {alias} not in GLOBAL_ETFS — skipping", file=sys.stderr)
        return None
    yf_ticker = ticker_mapped.replace(".US", "")
    try:
        raw = yf.download(
            yf_ticker,
            start=BACKFILL_START.strftime("%Y-%m-%d"),
            end=pd.Timestamp.now().strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        print(f"warn: yfinance download failed for {alias} ({yf_ticker}): {exc}", file=sys.stderr)
        return None
    if raw is None or raw.empty:
        return None
    # yfinance single-ticker returns a flat DataFrame; multi-ticker returns MultiIndex
    if isinstance(raw.columns, pd.MultiIndex):
        try:
            close = raw["Close"]
        except KeyError:
            return None
        if hasattr(close, "columns"):
            # still a DataFrame — pick first column
            close = close.iloc[:, 0]
    else:
        close = raw["Close"]
    df = pd.DataFrame({"date": close.index, "close": close.values})
    df["date"] = pd.to_datetime(df["date"])
    # Add dummy OHLCV columns to match phase_c_backtest.fetcher's schema
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df["volume"] = 0
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    return df.sort_values("date").reset_index(drop=True)


def _load_etf_bars(weights: dict[str, float]) -> dict[str, pd.DataFrame]:
    """Load parquet cache; backfill via yfinance when empty or coverage-short.

    Side effect: writes backfilled bars to pipeline/data/research/phase_c/daily_bars/
    so every downstream consumer benefits.
    """
    cache_dir = phase_c_paths.DAILY_BARS_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    bars: dict[str, pd.DataFrame] = {}
    for sym in weights:
        cache_path = cache_dir / f"{sym}.parquet"
        df = None
        if cache_path.exists():
            try:
                df = pd.read_parquet(cache_path)
            except Exception as exc:
                print(f"warn: corrupt parquet for {sym}: {exc}", file=sys.stderr)
                df = None
        # Determine whether we need to backfill
        need_backfill = (
            df is None
            or df.empty
            or df["date"].min() > MIN_COVERAGE_DATE
        )
        if need_backfill:
            print(f"backfilling {sym} via yfinance...", file=sys.stderr)
            fetched = _yfinance_backfill_one(sym)
            if fetched is not None and not fetched.empty:
                fetched.to_parquet(cache_path, index=False)
                df = fetched
                print(f"  -> wrote {len(fetched)} rows to {cache_path.name}", file=sys.stderr)
            else:
                print(f"  -> yfinance fetch returned nothing for {sym}", file=sys.stderr)
        if df is not None and not df.empty:
            bars[sym] = df.sort_values("date").reset_index(drop=True)
    return bars


def main() -> int:
    cfg = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = cfg["optimal_weights"]
    etf_bars = _load_etf_bars(weights)
    if not etf_bars:
        print("error: no ETF bars loaded — check parquet cache", file=sys.stderr)
        return 1

    # Union of all ETF trading dates >= START
    all_dates = sorted({d for df in etf_bars.values()
                        for d in df["date"][df["date"] >= pd.Timestamp(START)]})
    rows = []
    for d in all_dates:
        signal = _compute_signal(d.strftime("%Y-%m-%d"), weights, etf_bars)
        rows.append({"date": d, "regime_zone": _signal_to_zone(signal),
                     "signal_score": round(signal, 4)})
    out = pd.DataFrame(rows).sort_values("date")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(out)} rows to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
