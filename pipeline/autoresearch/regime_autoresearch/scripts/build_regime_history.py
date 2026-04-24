"""Produces pipeline/data/regime_history.csv via the existing backfill.

Reuses pipeline.research.phase_c_backtest:
- `regime._compute_signal` — the canonical composite-signal function used by
   the live engine (cannot drift).

The zone mapping itself is NOT the live engine's absolute-threshold function.
It is a quintile-based bucketing whose cutpoints are frozen from a
pre-train calibration window [CALIBRATION_START, CALIBRATION_END]. This
keeps labels causal (no look-ahead into train+val or holdout) while
ensuring the 5 zones are evenly populated in train+val — a prerequisite
for the autoresearch engine's per-regime rule search.

Weights live at pipeline/autoresearch/etf_optimal_weights.json (NOT
pipeline/data/…). ETF symbol keys are lowercase basket names
(brazil, natgas, silver, india_etf, …), each matching a parquet filename
under pipeline/data/research/phase_c/daily_bars/.

Self-healing ETF cache (yfinance backfill)
------------------------------------------
`_load_etf_bars` self-heals the parquet cache: when a parquet is empty
or its coverage starts after `BACKFILL_START` (2018-01-01), it refetches
via yfinance using the `GLOBAL_ETFS` alias map from etf_reoptimize and
writes the result back to the parquet cache. Every downstream consumer
of phase_c/daily_bars benefits.

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

import pandas as pd

from pipeline.autoresearch.etf_reoptimize import GLOBAL_ETFS, _signal_to_zone
from pipeline.autoresearch.regime_autoresearch._yfinance_util import download_ohlcv
from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR,
    FNO_DIR,
    HOLDOUT_END,
    HOLDOUT_START,
    PANEL_START,
    REPO_ROOT,
    TRAIN_VAL_END,
    TRAIN_VAL_START,
)
from pipeline.research.phase_c_backtest import paths as phase_c_paths
from pipeline.research.phase_c_backtest.regime import _compute_signal

WEIGHTS_PATH = REPO_ROOT / "pipeline/autoresearch/etf_optimal_weights.json"
OUT_CSV = REPO_ROOT / "pipeline/data/regime_history.csv"
CUTPOINTS_PATH = REPO_ROOT / "pipeline/data/regime_cutpoints.json"

# Pre-train calibration window. Cutpoints are frozen here; NEVER include
# train+val or holdout data when computing them — that would be look-ahead.
CALIBRATION_START = pd.Timestamp("2018-01-01")
CALIBRATION_END = pd.Timestamp("2021-04-22")

# Signal is emitted from START onwards; cutpoints applied from START onwards.
START = pd.Timestamp(TRAIN_VAL_START)          # 2021-04-23
BACKFILL_START = CALIBRATION_START              # fetch bars from 2018-01-01
MIN_COVERAGE_DATE = CALIBRATION_START           # trigger backfill if cache starts after this


# ---------------------------------------------------------------------------
# Absolute-threshold zone mapping (kept for reference / diagnostics).
# This is the OLD mapping. It is not used by this script anymore; the live
# engine still uses it (imported from etf_reoptimize._signal_to_zone), but
# our historical regime_history.csv uses quantile-based bucketing so every
# regime has enough events for per-regime rule search in autoresearch.
# ---------------------------------------------------------------------------
def _signal_to_zone_absolute(signal: float) -> str:
    """Absolute-threshold mapping from the live engine. Kept as a diagnostic.

    Delegates to the canonical function in etf_reoptimize so behaviour
    cannot drift. NOT used by the regime_history.csv builder — see
    `_signal_to_zone_quantile` for the builder's mapping.
    """
    return _signal_to_zone(signal)


# ---------------------------------------------------------------------------
# Quantile-based zone mapping (this script's actual mapping).
# ---------------------------------------------------------------------------
def _compute_quintile_cutpoints(signals: pd.Series) -> dict[str, float]:
    """Compute 20/40/60/80 quantile cutpoints from a signal series.

    NaNs are dropped before computing quantiles.
    """
    clean = pd.Series(signals).dropna()
    if clean.empty:
        raise ValueError("cannot compute cutpoints from empty signal series")
    q = clean.quantile([0.20, 0.40, 0.60, 0.80])
    return {
        "q20": float(q.loc[0.20]),
        "q40": float(q.loc[0.40]),
        "q60": float(q.loc[0.60]),
        "q80": float(q.loc[0.80]),
    }


def _signal_to_zone_quantile(signal: float, cutpoints: dict) -> str:
    """Bucket a signal into one of 5 zones using frozen quintile cutpoints.

    - signal < q20  → RISK-OFF
    - q20 ≤ signal < q40 → CAUTION
    - q40 ≤ signal < q60 → NEUTRAL
    - q60 ≤ signal < q80 → RISK-ON
    - signal ≥ q80 → EUPHORIA
    """
    if signal < cutpoints["q20"]:
        return "RISK-OFF"
    if signal < cutpoints["q40"]:
        return "CAUTION"
    if signal < cutpoints["q60"]:
        return "NEUTRAL"
    if signal < cutpoints["q80"]:
        return "RISK-ON"
    return "EUPHORIA"


# ---------------------------------------------------------------------------
# ETF cache loading + yfinance self-heal
# ---------------------------------------------------------------------------
def _yfinance_backfill_one(alias: str) -> pd.DataFrame | None:
    """Fetch daily OHLCV for one ETF alias via yfinance, return DataFrame or None.

    alias is a GLOBAL_ETFS key (brazil, natgas, silver, ...).

    Returns real OHLCV when yfinance provides it. No fabrication: any downstream
    consumer of high/low/open/volume either sees real data or the row is absent.
    """
    ticker_mapped = GLOBAL_ETFS.get(alias)
    if ticker_mapped is None:
        print(f"warn: alias {alias} not in GLOBAL_ETFS -- skipping", file=sys.stderr)
        return None
    yf_ticker = ticker_mapped.replace(".US", "")
    df = download_ohlcv(
        yf_ticker,
        start=BACKFILL_START.strftime("%Y-%m-%d"),
        end=pd.Timestamp.now().strftime("%Y-%m-%d"),
    )
    if df.empty:
        return None
    return df.sort_values("date").reset_index(drop=True)


def _load_etf_bars(weights: dict[str, float]) -> dict[str, pd.DataFrame]:
    """Load parquet cache; backfill via yfinance when empty or coverage-short.

    Side effect: writes backfilled bars to pipeline/data/research/phase_c/daily_bars/
    so every downstream consumer benefits. An ETF whose yfinance history starts
    after BACKFILL_START (e.g. younger issues that post-date 2018) is not retried
    in a loop; we log a warning and accept its shorter series. Calibration can
    tolerate a few ETFs with partial history as long as the majority contribute.
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
        # Determine whether we need to backfill. We need 2018-01-01 coverage
        # for the calibration window; if the cache starts after that, refetch.
        need_backfill = (
            df is None
            or df.empty
            or df["date"].min() > MIN_COVERAGE_DATE
        )
        if need_backfill:
            print(f"backfilling {sym} via yfinance (target start={BACKFILL_START.date()})...",
                  file=sys.stderr)
            fetched = _yfinance_backfill_one(sym)
            if fetched is not None and not fetched.empty:
                fetched.to_parquet(cache_path, index=False)
                df = fetched
                print(f"  -> wrote {len(fetched)} rows to {cache_path.name} "
                      f"(coverage {fetched['date'].min().date()}..{fetched['date'].max().date()})",
                      file=sys.stderr)
                if fetched["date"].min() > MIN_COVERAGE_DATE:
                    print(f"  warn: {sym} history begins "
                          f"{fetched['date'].min().date()} "
                          f"(after {MIN_COVERAGE_DATE.date()}); "
                          f"calibration will use its earliest available data",
                          file=sys.stderr)
            else:
                print(f"  -> yfinance fetch returned nothing for {sym}", file=sys.stderr)
        if df is not None and not df.empty:
            bars[sym] = df.sort_values("date").reset_index(drop=True)
    return bars


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------
def _print_distribution(df: pd.DataFrame, label: str, start: str, end: str) -> pd.Series:
    """Print per-regime count for a window and return the value_counts series."""
    mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    counts = df.loc[mask, "regime_zone"].value_counts().sort_index()
    print(f"\n{label} distribution ({start} -> {end}, n={int(mask.sum())}):")
    for zone in ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"):
        print(f"  {zone:<9} {int(counts.get(zone, 0))}")
    return counts


def main() -> int:
    cfg = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = cfg["optimal_weights"]
    etf_bars = _load_etf_bars(weights)
    if not etf_bars:
        print("error: no ETF bars loaded — check parquet cache", file=sys.stderr)
        return 1

    # Union of all ETF trading dates >= BACKFILL_START. Full range (calibration
    # + emitted regime series) so we can compute signal once.
    all_dates = sorted({d for df in etf_bars.values()
                        for d in df["date"][df["date"] >= BACKFILL_START]})
    print(f"computing composite signal over {len(all_dates)} dates "
          f"({all_dates[0].date()} -> {all_dates[-1].date()})", file=sys.stderr)

    rows = [
        {"date": d, "signal_score": round(_compute_signal(
            d.strftime("%Y-%m-%d"), weights, etf_bars), 4)}
        for d in all_dates
    ]
    signal_df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # Freeze quintile cutpoints from the calibration window.
    calib_mask = ((signal_df["date"] >= CALIBRATION_START)
                  & (signal_df["date"] <= CALIBRATION_END))
    calib_signals = signal_df.loc[calib_mask, "signal_score"]
    print(f"calibration window: {CALIBRATION_START.date()} -> {CALIBRATION_END.date()} "
          f"({int(calib_mask.sum())} days)", file=sys.stderr)
    cutpoints = _compute_quintile_cutpoints(calib_signals)

    cutpoints_out = {
        "calibration_start": CALIBRATION_START.strftime("%Y-%m-%d"),
        "calibration_end": CALIBRATION_END.strftime("%Y-%m-%d"),
        **cutpoints,
    }
    CUTPOINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUTPOINTS_PATH.write_text(json.dumps(cutpoints_out, indent=2), encoding="utf-8")
    print(f"wrote cutpoints to {CUTPOINTS_PATH}:", file=sys.stderr)
    for k, v in cutpoints_out.items():
        print(f"  {k}: {v}", file=sys.stderr)

    # Apply cutpoints to dates from START onwards; emit regime_history.csv.
    emit_mask = signal_df["date"] >= START
    out = signal_df.loc[emit_mask].copy()
    out["regime_zone"] = out["signal_score"].apply(
        lambda s: _signal_to_zone_quantile(s, cutpoints)
    )
    out = out[["date", "regime_zone", "signal_score"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {len(out)} rows to {OUT_CSV}")

    # Distribution audit.
    train_val_counts = _print_distribution(out, "train+val",
                                           TRAIN_VAL_START, TRAIN_VAL_END)
    _print_distribution(out, "holdout", HOLDOUT_START, HOLDOUT_END)

    min_events = int(train_val_counts.reindex(
        ["RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"], fill_value=0
    ).min())
    if min_events < 50:
        print(f"\nERROR: train+val min regime count = {min_events} (< 50). "
              f"Distribution is skewed; quantile bucketing failed to balance. "
              f"Investigate calibration window or composite signal.",
              file=sys.stderr)
        return 2

    # -------------------------------------------------------------------------
    # v2 panel coverage audit — build_regime_history emits this so the v2
    # in_sample_runner can load it at startup and know which tickers to
    # exclude. We load each FNO CSV, filter to [PANEL_START, TRAIN_VAL_END],
    # and flag tickers with >=100 missing days vs the NIFTY calendar.
    # -------------------------------------------------------------------------
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    MAX_MISSING_DAYS = 100
    panel_start_ts = pd.Timestamp(PANEL_START)
    train_val_end_ts = pd.Timestamp(TRAIN_VAL_END)

    print(f"\nBuilding FNO panel coverage audit "
          f"({PANEL_START} -> {TRAIN_VAL_END})...", file=sys.stderr)

    # Load FNO CSVs into a dict[ticker -> DataFrame] filtered to the v2 window.
    panel_by_ticker: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(FNO_DIR.glob("*.csv")):
        ticker = csv_path.stem
        try:
            df = pd.read_csv(csv_path)
            df.columns = [c.lower() for c in df.columns]
            if "date" not in df.columns or "close" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= panel_start_ts) & (df["date"] <= train_val_end_ts)]
            if not df.empty:
                panel_by_ticker[ticker] = df[["date", "close"]].reset_index(drop=True)
        except Exception as exc:
            print(f"  warn: could not load {csv_path.name}: {exc}", file=sys.stderr)

    print(f"  loaded {len(panel_by_ticker)} FNO tickers", file=sys.stderr)

    # Canonical business-day calendar from NIFTY. NIFTY.csv is not in FNO_DIR;
    # use the NIFTY_daily.csv from india_historical if available, otherwise
    # fall back to an empty set (all tickers retained, audit is informational).
    nifty_csv = REPO_ROOT / "pipeline/data/india_historical/indices/NIFTY_daily.csv"
    if nifty_csv.exists():
        nifty_df = pd.read_csv(nifty_csv, parse_dates=["date"], usecols=["date"])
        nifty_dates = set(nifty_df["date"].dt.date.tolist())
        lo = panel_start_ts.date()
        hi = train_val_end_ts.date()
        canon_in_window = {d for d in nifty_dates if lo <= d <= hi}
        print(f"  NIFTY calendar: {len(canon_in_window)} business days "
              f"in [{PANEL_START}, {TRAIN_VAL_END}]", file=sys.stderr)
    else:
        canon_in_window = set()
        print("  warn: NIFTY_daily.csv not found — skipping calendar check; "
              "all tickers retained", file=sys.stderr)

    retained: list[str] = []
    dropped: list[dict] = []
    for ticker, df in panel_by_ticker.items():
        have = set(pd.to_datetime(df["date"]).dt.date.tolist())
        missing = len(canon_in_window - have)
        if missing >= MAX_MISSING_DAYS:
            dropped.append({"ticker": ticker, "missing_days": missing})
        else:
            retained.append(ticker)

    audit = {
        "generated_at": _dt.now(_tz.utc).isoformat(),
        "panel_start": PANEL_START,
        "train_val_end": TRAIN_VAL_END,
        "holdout_end": HOLDOUT_END,
        "coverage_threshold": {"max_missing_days": MAX_MISSING_DAYS},
        "retained_tickers": sorted(retained),
        "dropped_tickers": sorted(dropped, key=lambda d: -d["missing_days"]),
    }
    audit_path = DATA_DIR / "panel_coverage_audit_2026-04-25.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(_json.dumps(audit, indent=2, sort_keys=False), encoding="utf-8")
    print(f"  retained={len(retained)} dropped={len(dropped)} "
          f"— wrote {audit_path.name}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
