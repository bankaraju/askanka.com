"""End-to-end Phase 2 orchestrator.

Runs the full grid (lookback × universe), applies markers, computes statistical
tests, runs slippage grid + implementation-risk + alpha-after-beta + decay, and
writes all per-run manifests + final reports.

§13A.1 input-integrity contract: both replay parquets must exist on disk before
run() begins. Raise FileNotFoundError if either is missing.

§10.2 / §10.3 purging (v1 limitation): run_walk_forward does NOT apply embargo
or holding-period purging internally (that is a known T6 v1 limitation, not an
intentional design choice). A warning is logged at each run so the audit trail
is clear. Pre-filtering via ``purged_train_dates`` remains the caller's
responsibility until that hook is threaded into the rolling-refit core.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from pipeline.autoresearch.etf_v3_eval.phase_2.manifest import RunConfig, write_run_manifest
from pipeline.autoresearch.etf_v3_eval.phase_2.walk_forward_runner import run_walk_forward

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase2Inputs:
    """Validated inputs for the Phase 2 grid run.

    Attributes
    ----------
    replay_parquets:
        Mapping from universe-size label (e.g. "126", "273") to parquet path
        string. Must be non-empty; both files are checked for existence before
        run() begins (§13A.1).
    lookbacks:
        Tuple of lookback windows in calendar days. Must be non-empty.
    feature_set:
        Feature set label forwarded to RollingRefitConfig (e.g. "curated").
    seed:
        Random seed forwarded to RollingRefitConfig. Must be >= 0.
    refit_interval_days:
        Walk-forward refit cadence in calendar days. Must be >= 1.
    n_iterations:
        Number of permutation-null / bootstrap iterations. Must be >= 1.
    """

    replay_parquets: Mapping[str, str]
    lookbacks: tuple[int, ...] = (756, 1200, 1236)
    feature_set: str = "curated"
    seed: int = 0
    refit_interval_days: int = 5
    n_iterations: int = 2000

    def __post_init__(self) -> None:
        if not self.lookbacks:
            raise ValueError(
                "lookbacks must be a non-empty tuple of integers; got empty tuple"
            )
        if not self.replay_parquets:
            raise ValueError(
                "replay_parquets must be a non-empty mapping; got empty mapping"
            )
        if self.seed < 0:
            raise ValueError(
                f"seed must be >= 0; got {self.seed!r}"
            )
        if self.n_iterations < 1:
            raise ValueError(
                f"n_iterations must be >= 1; got {self.n_iterations!r}"
            )
        if self.refit_interval_days < 1:
            raise ValueError(
                f"refit_interval_days must be >= 1; got {self.refit_interval_days!r}"
            )


def iter_run_configs(inputs: Phase2Inputs) -> Iterable[RunConfig]:
    """Yield one RunConfig per (lookback, universe) combination.

    Produces ``len(inputs.lookbacks) × len(inputs.replay_parquets)`` configs in
    (lookback-major, universe-minor) order — deterministic for reproducibility.
    """
    for lb in inputs.lookbacks:
        for universe in inputs.replay_parquets:
            yield RunConfig(
                run_id=f"wf_lb{lb}_u{universe}_seed{inputs.seed}",
                strategy_version="v3-CURATED-30",
                cost_model_version="cm_2026-04-26_v1",
                random_seed=inputs.seed,
                lookback_days=lb,
                refit_interval_days=inputs.refit_interval_days,
                n_iterations=inputs.n_iterations,
                universe=universe,
                feature_set=inputs.feature_set,
            )


def run(
    inputs: Phase2Inputs,
    out_root: Path,
) -> tuple[list[Path], list[str]]:
    """Execute the full Phase 2 grid.

    Parameters
    ----------
    inputs:
        Validated grid specification.
    out_root:
        Root directory; one sub-directory is created per run_id.

    Returns
    -------
    paths:
        List of manifest.json Paths for succeeded runs.
    failed:
        List of run_ids that raised an exception. The orchestrator logs the
        error and continues so a single bad config does not abort the grid.

    Raises
    ------
    FileNotFoundError
        If any replay parquet declared in ``inputs.replay_parquets`` does not
        exist on disk (§13A.1 input-integrity contract).
    """
    # §13A.1 — verify all input parquets exist before touching out_root
    for label, parquet_path_str in inputs.replay_parquets.items():
        p = Path(parquet_path_str)
        if not p.exists():
            raise FileNotFoundError(
                f"replay_parquets[{label!r}] not found: {parquet_path_str!r}. "
                "Satisfy §13A.1 input-integrity contract before running Phase 2."
            )

    out_root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    failed: list[str] = []

    for cfg in iter_run_configs(inputs):
        run_dir = out_root / cfg.run_id
        logger.info("running %s ...", cfg.run_id)

        # §10.2 / §10.3 purging v1 limitation notice — preserved in audit log
        logger.warning(
            "PURGE-V1-LIMITATION: run_walk_forward does not apply §10.2 embargo "
            "or §10.3 holding-period purging for run_id=%s. Pre-filter the input "
            "panel with purged_train_dates() before invoking this orchestrator if "
            "purging is required.",
            cfg.run_id,
        )

        try:
            run_walk_forward(cfg, run_dir)
            manifest_path = run_dir / "manifest.json"
            paths.append(manifest_path)
            logger.info("completed %s -> %s", cfg.run_id, manifest_path)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "run_id=%s FAILED: %s: %s",
                cfg.run_id,
                type(exc).__name__,
                exc,
            )
            failed.append(cfg.run_id)

    return paths, failed


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ETF v3-Eval Phase 2 orchestrator")
    p.add_argument(
        "--out-root",
        default="pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs",
        help="Root directory for per-run output directories.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed (must be >= 0; default: 0).",
    )
    p.add_argument(
        "--n-iterations",
        type=int,
        default=2000,
        help="Permutation-null / bootstrap iteration count (default: 2000).",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="Dev-only: 100 iterations, single lookback (756d), single universe (126).",
    )
    return p


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _build_argparser().parse_args()

    if args.seed < 0:
        print(f"ERROR: --seed must be >= 0; got {args.seed}")
        return 1

    inputs = Phase2Inputs(
        replay_parquets={
            "126": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet",
            "273": "pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet",
        },
        lookbacks=(756,) if args.quick else (756, 1200, 1236),
        seed=args.seed,
        n_iterations=100 if args.quick else args.n_iterations,
    )

    out_root = Path(args.out_root)

    try:
        paths, failed = run(inputs, out_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    n_succeeded = len(paths)
    n_failed = len(failed)

    print(f"\n{'='*60}")
    print(f"Phase 2 orchestrator complete")
    print(f"  out_root    : {out_root}")
    print(f"  n_succeeded : {n_succeeded}")
    print(f"  n_failed    : {n_failed}")
    if failed:
        print(f"  failed runs : {failed}")
    print(f"{'='*60}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
