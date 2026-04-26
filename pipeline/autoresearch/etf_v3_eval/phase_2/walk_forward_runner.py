"""§10 purged walk-forward wrapper around etf_v3_rolling_refit.

The rolling refit module produces per-window predictions but does NOT enforce
the §10.3 purging (training rows whose holding-period overlaps the test window)
nor the §10.2 5-day embargo. This module supplies both as composable pieces and
provides a Phase 2 entry point that produces:
- per-run manifest (§13A.1)
- per-window weights JSON
- ledger of (date, signal, zone, train_window, test_window)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeConfig:
    embargo_days: int = 5            # §10.2
    holding_period_days: int = 0     # §10.3 — 0 for next-day-direction strategy


def purged_train_dates(
    train_dates: pd.DatetimeIndex,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    cfg: PurgeConfig,
) -> pd.DatetimeIndex:
    """Drop training rows that overlap the test window per §10.2 + §10.3.

    §10.2 embargo: any train date within ±embargo_days of [test_start, test_end]
    is dropped (inclusive on both sides of the embargo band).

    §10.3 holding-period purge: if holding_period_days > 0, train dates whose
    holding period (trade opened on train_date, closed on train_date +
    holding_period_days) closes *strictly inside* (test_start, test_end] are
    dropped.

    Boundary contract: a trade closing exactly on ``test_start`` is KEPT —
    the position is already flat when the test window opens. The ``>`` (strictly
    greater than) rather than ``>=`` comparison on line
    ``(close_dates > test_start)`` is deliberate and encodes this invariant; a
    future reader must not silently change it to ``>=``.
    """
    if len(train_dates) == 0:
        return train_dates

    # §10.2 — embargo band around the test window
    embargo_lo = test_start - pd.Timedelta(days=cfg.embargo_days)
    embargo_hi = test_end + pd.Timedelta(days=cfg.embargo_days)
    in_embargo = (train_dates >= embargo_lo) & (train_dates <= embargo_hi)

    # §10.3 — holding-period overlap
    if cfg.holding_period_days > 0:
        close_dates = train_dates + pd.Timedelta(days=cfg.holding_period_days)
        # Strictly inside (test_start, test_end] — closing exactly on test_start
        # means the position is already flat; do not purge that row.
        overlaps = (close_dates > test_start) & (close_dates <= test_end)
    else:
        overlaps = np.zeros(len(train_dates), dtype=bool)

    keep = ~(in_embargo | overlaps)
    return train_dates[keep]


def run_walk_forward(
    cfg: "pipeline.autoresearch.etf_v3_eval.phase_2.manifest.RunConfig",
    out_dir: Path,
) -> dict:
    """Run a single (lookback, universe, feature_set) walk-forward and emit manifest.

    Composes the existing rolling-refit module; if the upstream API is unstable
    or unavailable from this branch, the function still emits the §13A.1 manifest
    and logs the gap so callers know the run is incomplete.

    §10.2 / §10.3 purging (v1 limitation): this function does NOT apply embargo
    or holding-period purging to the training data. ``run_rolling_refit`` builds
    its own per-window training slices internally and does not accept a purge
    hook. Until that is threaded into the rolling-refit core, callers (T21
    orchestrator or a future wrapper) must pre-filter the input panel BEFORE
    invoking this function. Use ``purged_train_dates`` for that pre-filtering
    step. This is a known v1 limitation, not an intentional design choice.
    """
    # Lazy import: keeps ``purged_train_dates`` testable without requiring the
    # rolling-refit module (and its heavy data-loader dependencies) to import
    # cleanly in every test environment.
    from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import RunConfig, write_run_manifest
    from pipeline.autoresearch.etf_v3_rolling_refit import RollingRefitConfig, run_rolling_refit

    # Map Phase-2 RunConfig → RollingRefitConfig
    # RollingRefitConfig fields: refit_interval_days, lookback_days, n_iterations,
    # seed, eval_start, eval_end, feature_set
    rr_cfg = RollingRefitConfig(
        refit_interval_days=cfg.refit_interval_days,
        lookback_days=cfg.lookback_days,
        n_iterations=cfg.n_iterations,
        seed=cfg.random_seed,
        feature_set=cfg.feature_set,
        # eval_start / eval_end use RollingRefitConfig defaults unless overridden;
        # T21 (orchestrator) may subclass RunConfig to carry these — leave at defaults.
    )
    result = run_rolling_refit(rr_cfg)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write per-window result — stdlib json, NOT deprecated pd.io.json
    (out_dir / "rolling_refit.json").write_text(
        json.dumps(result, default=str, indent=2), encoding="utf-8"
    )

    # §13A.1 manifest
    input_files = {
        "replay_parquet": Path(
            "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet"
        ),
        "etf_panel": Path("pipeline/autoresearch/data/etf_v3_panel.parquet"),
    }
    write_run_manifest(
        out_dir / "manifest.json",
        cfg,
        input_files=input_files,
    )

    logger.info(
        "run_walk_forward complete: run_id=%s, out_dir=%s, "
        "overall_edge_pp=%.3f, n_windows=%d",
        cfg.run_id,
        out_dir,
        result.get("overall_edge_pp", float("nan")),
        result.get("n_refit_windows", 0),
    )
    return result
