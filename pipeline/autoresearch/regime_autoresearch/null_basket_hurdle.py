"""v2 construction-matched random-basket hurdle.

Replaces v1's `regime_buy_and_hold_sharpe` (long-only NIFTY) with a
bootstrap null: for a proposed rule with construction C, cardinality k,
hold horizon h, and regime R, sample N trials where each trial picks k
random tickers per event date and applies C's sign semantics. Median
trial Sharpe is the hurdle; p95 is a diagnostic upper band.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from pipeline.autoresearch.regime_autoresearch.constants import (
    DATA_DIR, REGIMES,
)
from pipeline.autoresearch.regime_autoresearch.in_sample_runner import (
    _net_sharpe, _per_ticker_close_map, _per_ticker_dates,
    _nth_trading_day_after, _trade_return,
)

CONSTRUCTIONS: tuple[str, ...] = (
    "single_long", "single_short", "top_k", "bottom_k", "long_short_basket",
)
K_VALUES: tuple[int, ...] = (1, 5, 10, 15, 20, 25, 30, 40)
HOLD_HORIZONS: tuple[int, ...] = (1, 5, 10)
WINDOWS: tuple[str, ...] = ("train_val", "holdout")

HURDLE_PARQUET = DATA_DIR / "null_basket_hurdles_v2.parquet"
N_TRIALS_PROD = 1000


def _seed_for(construction: str, k: int, h: int, regime: str,
              window: str) -> int:
    tag = f"{construction}|{k}|{h}|{regime}|{window}"
    return int(hashlib.sha256(tag.encode()).hexdigest()[:8], 16) & 0xFFFFFFFF


def _direction_for(construction: str, leg: str) -> int:
    if construction in ("single_long", "top_k"):
        return +1
    if construction in ("single_short", "bottom_k"):
        return -1
    if construction == "long_short_basket":
        return +1 if leg == "long" else -1
    raise ValueError(f"unknown construction {construction!r}")


def _trial_event_return(close_map, date_arrs, tickers_pool, event_date,
                         construction, k, h, rng):
    if construction == "long_short_basket":
        if len(tickers_pool) < 2 * k:
            return None
        picks = rng.choice(tickers_pool, size=2 * k, replace=False)
        longs, shorts = picks[:k].tolist(), picks[k:].tolist()
        long_rets, short_rets = [], []
        for tk in longs:
            exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
            if exit_d is None:
                continue
            r = _trade_return(close_map, tk, event_date, exit_d, +1)
            if r is not None:
                long_rets.append(r)
        for tk in shorts:
            exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
            if exit_d is None:
                continue
            r = _trade_return(close_map, tk, event_date, exit_d, -1)
            if r is not None:
                short_rets.append(r)
        if not long_rets or not short_rets:
            return None
        return 0.5 * float(np.mean(long_rets)) + 0.5 * float(np.mean(short_rets))
    effective_k = 1 if construction in ("single_long", "single_short") else k
    if len(tickers_pool) < effective_k:
        return None
    picks = rng.choice(tickers_pool, size=effective_k, replace=False).tolist()
    direction = _direction_for(construction, leg="long")
    rets = []
    for tk in picks:
        exit_d = _nth_trading_day_after(date_arrs, tk, event_date, h)
        if exit_d is None:
            continue
        r = _trade_return(close_map, tk, event_date, exit_d, direction)
        if r is not None:
            rets.append(r)
    if not rets:
        return None
    return float(np.mean(rets))


def _compute_one_cell(close_map, date_arrs, tickers_pool,
                      event_dates, construction, k, h, regime,
                      window, n_trials):
    seed = _seed_for(construction, k, h, regime, window)
    rng = np.random.default_rng(seed)
    trial_sharpes = np.full(n_trials, np.nan)
    for trial_i in range(n_trials):
        event_rets = []
        for d in event_dates:
            r = _trial_event_return(close_map, date_arrs, tickers_pool,
                                     d, construction, k, h, rng)
            if r is not None:
                event_rets.append(r * 100.0)  # percent for _net_sharpe
        if not event_rets:
            continue
        trial_sharpes[trial_i] = _net_sharpe(
            pd.Series(event_rets, dtype=float),
            level="S1", hold_horizon=h,
        )
    finite = trial_sharpes[np.isfinite(trial_sharpes)]
    if finite.size == 0:
        hmedian, hp95 = 0.0, 0.0
    else:
        hmedian = float(np.median(finite))
        hp95 = float(np.percentile(finite, 95))
    return {
        "construction": construction, "k": k, "hold_horizon": h,
        "regime": regime, "window": window,
        "hurdle_sharpe_median": hmedian,
        "hurdle_sharpe_p95": hp95,
        "n_events": int(len(event_dates)),
        "n_trials": int(n_trials),
        "seed": int(seed),
        "generated_at_sha": "",
    }


# Worker-state slot used by the parallel build path. The ProcessPoolExecutor
# initializer populates this once per subprocess so the 250k-row panel
# pickling cost is paid once, not 1,200 times.
_WORKER_STATE: dict = {}


def _init_worker(close_map, date_arrs, tickers_pool, ev_map_train,
                 ev_map_holdout):
    _WORKER_STATE["close_map"] = close_map
    _WORKER_STATE["date_arrs"] = date_arrs
    _WORKER_STATE["tickers_pool"] = tickers_pool
    _WORKER_STATE["ev_map_train"] = ev_map_train
    _WORKER_STATE["ev_map_holdout"] = ev_map_holdout


def _compute_cell_task(args_tuple):
    construction, k, h, regime, window, n_trials = args_tuple
    ev_map = (_WORKER_STATE["ev_map_train"] if window == "train_val"
              else _WORKER_STATE["ev_map_holdout"])
    ev = ev_map.get(regime, pd.DatetimeIndex([]))
    return _compute_one_cell(
        _WORKER_STATE["close_map"], _WORKER_STATE["date_arrs"],
        _WORKER_STATE["tickers_pool"],
        ev, construction, k, h, regime, window, n_trials,
    )


def _row_sort_key(row: dict) -> tuple:
    window_rank = 0 if row["window"] == "train_val" else 1
    regime_rank = REGIMES.index(row["regime"])
    c_rank = CONSTRUCTIONS.index(row["construction"])
    return (window_rank, regime_rank, c_rank, row["k"], row["hold_horizon"])


def compute_hurdle_table(panel, event_dates_by_regime,
                          holdout_event_dates_by_regime,
                          n_trials=N_TRIALS_PROD, n_jobs=1):
    # Hoist panel precomputes out of the per-cell loop (otherwise rebuilt
    # 1,200 times on a ~266k-row real panel — tens of minutes of overhead).
    date_arrs = _per_ticker_dates(panel)
    close_map = _per_ticker_close_map(panel)
    tickers_pool = np.array(sorted(
        set(panel["ticker"].unique()) - {"NIFTY", "VIX", "REGIME"}
    ))
    # Build the full cell-task list up front so the parallel and serial
    # paths share the same iteration.
    cell_tasks: list[tuple] = []
    for window in ("train_val", "holdout"):
        for regime in REGIMES:
            for C in CONSTRUCTIONS:
                for k in K_VALUES:
                    for h in HOLD_HORIZONS:
                        cell_tasks.append((C, k, h, regime, window, n_trials))

    if n_jobs and n_jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        rows: list[dict] = []
        with ProcessPoolExecutor(
            max_workers=n_jobs,
            initializer=_init_worker,
            initargs=(close_map, date_arrs, tickers_pool,
                      event_dates_by_regime, holdout_event_dates_by_regime),
        ) as pool:
            for row in pool.map(_compute_cell_task, cell_tasks, chunksize=8):
                rows.append(row)
        # as_completed ordering can differ across runs — sort for
        # byte-reproducible parquet output across n_jobs settings.
        rows.sort(key=_row_sort_key)
        return pd.DataFrame(rows)

    # Serial path (default — tests rely on this for deterministic speed).
    rows = []
    for window, dates_map in (
        ("train_val", event_dates_by_regime),
        ("holdout", holdout_event_dates_by_regime),
    ):
        for regime in REGIMES:
            ev = dates_map.get(regime, pd.DatetimeIndex([]))
            for C in CONSTRUCTIONS:
                for k in K_VALUES:
                    for h in HOLD_HORIZONS:
                        rows.append(_compute_one_cell(
                            close_map, date_arrs, tickers_pool,
                            ev, C, k, h, regime, window, n_trials,
                        ))
    return pd.DataFrame(rows)


def load_null_basket_hurdle(construction, k, hold_horizon, regime,
                              window="train_val", table_path=None):
    path = table_path or HURDLE_PARQUET
    if not path.exists():
        raise FileNotFoundError(
            f"Hurdle table not built: {path}. "
            f"Run build_null_basket_hurdles.py."
        )
    tbl = pd.read_parquet(path)
    mask = (
        (tbl["construction"] == construction)
        & (tbl["k"] == k)
        & (tbl["hold_horizon"] == hold_horizon)
        & (tbl["regime"] == regime)
        & (tbl["window"] == window)
    )
    hit = tbl[mask]
    if hit.empty:
        raise KeyError(
            f"No hurdle row for construction={construction!r} k={k} "
            f"h={hold_horizon} regime={regime!r} window={window!r}"
        )
    return float(hit["hurdle_sharpe_median"].iloc[0])
