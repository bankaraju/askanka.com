"""Slice-restricted compliance runner for Phase C LAG/OVERSHOOT audit.

Exports:

  filter_events_by_geometry(events, slice_name) -> pd.DataFrame
      Per-row geometry classification via classify_event_geometry
      (pipeline.autoresearch.reverse_regime_breaks); returns only rows whose
      geometry matches the requested slice.

  SliceSpec
      Dataclass holding slice_name + hypothesis_id; builds the output Path.

  run_slice_compliance(parent_events_path, slice_spec, ...) -> Path
      Reads the parent run's events.json, filters to the requested slice
      (+ optional ticker filter + min-events-per-cell floor), writes
      filtered_events.json, computes the family size, and invokes
      runner.main() with --events-override / --hypothesis-id / --family-size.

  main(argv) -> int
      CLI entrypoint wired through argparse.

Task 10 completes the orchestration deferred from Task 9.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from pipeline.autoresearch.reverse_regime_breaks import classify_event_geometry

_VALID_SLICES = {"LAG", "OVERSHOOT"}

_REPO = Path(__file__).resolve().parents[3]
_RESULTS_ROOT = _REPO / "pipeline" / "autoresearch" / "results"


def filter_events_by_geometry(events: pd.DataFrame, slice_name: str) -> pd.DataFrame:
    """Return a copy of *events* containing only rows whose geometry matches *slice_name*.

    Parameters
    ----------
    events:
        DataFrame with columns ``expected_return_pct`` and ``actual_return_pct``
        (both in percent, e.g. 2.0 means 2%).
    slice_name:
        One of ``"LAG"`` or ``"OVERSHOOT"``.  Rows classified as ``"DEGENERATE"``
        are dropped from both slices.

    Returns
    -------
    pd.DataFrame
        Filtered, index-reset copy of *events*.

    Raises
    ------
    ValueError
        If *slice_name* is not ``"LAG"`` or ``"OVERSHOOT"``.
    """
    if slice_name not in _VALID_SLICES:
        raise ValueError(
            f"slice_name must be one of {sorted(_VALID_SLICES)!r}, got {slice_name!r}"
        )

    mask = events.apply(
        lambda row: classify_event_geometry(
            row["expected_return_pct"],
            row["actual_return_pct"],
        ) == slice_name,
        axis=1,
    )
    return events.loc[mask].reset_index(drop=True)


@dataclass
class SliceSpec:
    """Specification for a single LAG or OVERSHOOT compliance run.

    Attributes
    ----------
    slice_name:
        ``"LAG"`` or ``"OVERSHOOT"``.
    hypothesis_id:
        Pre-registered hypothesis identifier, e.g. ``"H-2026-04-23-002"``.
    results_root:
        Base directory for output.  Defaults to
        ``pipeline/autoresearch/results/`` inside the repo.
    """

    slice_name: str
    hypothesis_id: str
    results_root: Path = field(default_factory=lambda: _RESULTS_ROOT)

    def output_path(self, run_timestamp: str) -> Path:
        """Build the output directory path for this slice run.

        The directory name is
        ``compliance_phase_c_<slice_lower>_<hypothesis_id>_<run_timestamp>``
        (spaces/colons in *run_timestamp* are replaced with underscores).

        Parameters
        ----------
        run_timestamp:
            ISO-format timestamp string, e.g. ``"2026-04-23T12:00:00"``.

        Returns
        -------
        Path
            Fully-qualified output directory (not yet created).
        """
        safe_ts = run_timestamp.replace(":", "-").replace(" ", "_")
        dir_name = (
            f"compliance_phase_c_{self.slice_name.lower()}"
            f"_{self.hypothesis_id}_{safe_ts}"
        )
        return self.results_root / dir_name


def run_slice_compliance(
    parent_events_path: Path,
    slice_spec: SliceSpec,
    run_timestamp: str,
    *,
    n_permutations: int = 100_000,
    min_events_per_cell: int = 10,
    ticker_filter: Optional[str] = None,
) -> Path:
    """Orchestrate a LAG- or OVERSHOOT-restricted compliance run.

    1. Read events from *parent_events_path*.
    2. Apply geometry filter via :func:`filter_events_by_geometry`.
    3. Optionally restrict to a single *ticker_filter*.
    4. Drop (ticker, direction) cells with fewer than *min_events_per_cell* events.
    5. Write the filtered events to ``output_dir / "filtered_events.json"``.
       (The inner runner will write its own ``events.json`` from the override.)
    6. Invoke :func:`pipeline.autoresearch.overshoot_compliance.runner.main`
       with ``--out-dir``, ``--events-override``, ``--hypothesis-id``, and
       ``--family-size`` (= number of surviving cells).

    Returns the output directory path.
    """
    events = pd.read_json(Path(parent_events_path), orient="records")
    filtered = filter_events_by_geometry(events, slice_spec.slice_name)

    if ticker_filter is not None:
        filtered = filtered.loc[filtered["ticker"] == ticker_filter].reset_index(drop=True)

    if not filtered.empty and min_events_per_cell > 1:
        counts = filtered.groupby(["ticker", "direction"]).size()
        keep_keys = set(counts[counts >= min_events_per_cell].index.tolist())
        mask = filtered.apply(
            lambda r: (r["ticker"], r["direction"]) in keep_keys, axis=1,
        )
        filtered = filtered.loc[mask].reset_index(drop=True)

    family_size = int(filtered.groupby(["ticker", "direction"]).ngroups) if not filtered.empty else 1

    out_dir = slice_spec.output_path(run_timestamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    filtered_path = out_dir / "filtered_events.json"
    filtered.to_json(filtered_path, orient="records", date_format="iso", indent=2)

    # Import lazily so monkeypatch.setattr(runner, "main", ...) in tests works
    # (the test patches the attribute on the module object after import).
    from pipeline.autoresearch.overshoot_compliance import runner as _runner

    argv = [
        "--out-dir", str(out_dir),
        "--events-override", str(filtered_path),
        "--hypothesis-id", slice_spec.hypothesis_id,
        "--family-size", str(family_size),
    ]
    rc = _runner.main(argv)
    if rc != 0:
        raise RuntimeError(f"runner.main returned non-zero exit code {rc}")

    return out_dir


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint for the slice runner."""
    parser = argparse.ArgumentParser(
        description="Run a LAG- or OVERSHOOT-restricted Phase C compliance pass.",
    )
    parser.add_argument("--parent-events", required=True,
                        help="Path to parent run's events.json (produced by the main compliance runner).")
    parser.add_argument("--slice", required=True, choices=sorted(_VALID_SLICES),
                        help="Geometry slice to extract.")
    parser.add_argument("--hypothesis-id", required=True,
                        help="Pre-registered hypothesis id for this slice run, "
                             "e.g. H-2026-04-23-002 (LAG) or H-2026-04-23-003 (OVERSHOOT).")
    parser.add_argument("--n-permutations", type=int, default=100_000,
                        help="Permutation count for per-ticker fade stats (default 100000).")
    parser.add_argument("--min-events-per-cell", type=int, default=10,
                        help="Minimum events per (ticker, direction) cell to survive filtering (default 10).")
    parser.add_argument("--ticker-filter", default=None,
                        help="If supplied, restrict to a single ticker (useful for smoke runs).")
    parser.add_argument("--run-timestamp", default=None,
                        help="Timestamp tag for the output directory (default: current UTC).")
    args = parser.parse_args(argv)

    run_ts = args.run_timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    spec = SliceSpec(slice_name=args.slice, hypothesis_id=args.hypothesis_id)

    out_dir = run_slice_compliance(
        parent_events_path=Path(args.parent_events),
        slice_spec=spec,
        run_timestamp=run_ts,
        n_permutations=args.n_permutations,
        min_events_per_cell=args.min_events_per_cell,
        ticker_filter=args.ticker_filter,
    )
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
