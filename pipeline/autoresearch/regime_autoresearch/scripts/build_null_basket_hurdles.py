"""CLI — precompute the 1,200-row null-basket hurdle parquet.

Reads regime_history.csv + the v2 panel; writes
data/null_basket_hurdles_v2.parquet. Deterministic; re-runs produce
byte-identical-within-tolerance output.

NOTE: v2 Task 2 ships a --n-trials=3 placeholder parquet to unblock
Tasks 3-8. Before running the first Mode 2 dry run (Task 9), rerun with
--n-trials 1000 to produce the production-precision hurdle table. The
3-trial placeholder keeps the 1,200-row shape, deterministic seeds, and
both train+val / holdout windows — downstream code paths (load helper,
in-sample verdict) do not depend on trial count.

Usage:
    python -m pipeline.autoresearch.regime_autoresearch.scripts.build_null_basket_hurdles
    python -m pipeline.autoresearch.regime_autoresearch.scripts.build_null_basket_hurdles --n-trials 1000
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, FNO_DIR, HOLDOUT_END, HOLDOUT_START, PANEL_START,
    REGIMES, REPO_ROOT, TRAIN_VAL_END, TRAIN_VAL_START,
)
from pipeline.autoresearch.regime_autoresearch.null_basket_hurdle import (
    HURDLE_PARQUET, compute_hurdle_table,
)


def _load_panel_and_events() -> tuple[pd.DataFrame, dict, dict]:
    # regime_history.csv is written by build_regime_history.py to pipeline/data/
    regime_csv = REPO_ROOT / "pipeline/data/regime_history.csv"
    regime = pd.read_csv(regime_csv, parse_dates=["date"])
    tickers = [p.stem for p in FNO_DIR.glob("*.csv")]
    rows = []
    for tk in tickers:
        try:
            df = pd.read_csv(FNO_DIR / f"{tk}.csv")
            df.columns = [c.lower() for c in df.columns]
            if "date" not in df.columns or "close" not in df.columns:
                print(f"  warn: skipping {tk}: missing date/close column")
                continue
            df["date"] = pd.to_datetime(df["date"])
        except Exception as exc:  # noqa: BLE001
            print(f"  warn: skipping {tk}: {exc}")
            continue
        df = df[(df["date"] >= pd.Timestamp(PANEL_START))
                & (df["date"] <= pd.Timestamp(HOLDOUT_END))]
        if df.empty:
            continue
        df["ticker"] = tk
        keep_cols = [c for c in ("date", "ticker", "close", "volume")
                      if c in df.columns]
        rows.append(df[keep_cols])
    panel = pd.concat(rows, ignore_index=True)

    # regime_history.csv uses `regime_zone` per v1 build_regime_history.py output
    # Fallbacks for older schemas: zone, regime
    if "regime_zone" in regime.columns:
        zone_col = "regime_zone"
    elif "zone" in regime.columns:
        zone_col = "zone"
    else:
        zone_col = "regime"
    ev_train = {r: pd.DatetimeIndex(sorted(
        regime[(regime[zone_col] == r)
                & (regime["date"] >= pd.Timestamp(TRAIN_VAL_START))
                & (regime["date"] <= pd.Timestamp(TRAIN_VAL_END))
                ]["date"].unique()
    )) for r in REGIMES}
    ev_holdout = {r: pd.DatetimeIndex(sorted(
        regime[(regime[zone_col] == r)
                & (regime["date"] >= pd.Timestamp(HOLDOUT_START))
                & (regime["date"] <= pd.Timestamp(HOLDOUT_END))
                ]["date"].unique()
    )) for r in REGIMES}
    return panel, ev_train, ev_holdout


def _current_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
        ).strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-trials", type=int, default=3,
                    help="bootstrap trials per cell (default 3 ships a "
                         "placeholder parquet; use 1000 for production "
                         "before Task 9 dry-run)")
    ap.add_argument("--n-jobs", type=int, default=1,
                    help="parallel workers over the 1,200 cells (default 1). "
                         "Set to os.cpu_count()-1 for production rebuild.")
    ap.add_argument("--out", type=Path, default=HURDLE_PARQUET,
                    help="parquet output path")
    args = ap.parse_args(argv)

    panel, ev_train, ev_holdout = _load_panel_and_events()
    print(f"[build_null_basket_hurdles] panel rows={len(panel):,} "
          f"n_trials={args.n_trials} n_jobs={args.n_jobs} out={args.out}")
    table = compute_hurdle_table(
        panel=panel,
        event_dates_by_regime=ev_train,
        holdout_event_dates_by_regime=ev_holdout,
        n_trials=args.n_trials,
        n_jobs=args.n_jobs,
    )
    table["generated_at_sha"] = _current_git_sha()
    table["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)
    print(f"[build_null_basket_hurdles] wrote {args.out}, {len(table)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
