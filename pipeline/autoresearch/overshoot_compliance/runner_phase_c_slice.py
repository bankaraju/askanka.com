"""Slice-restricted compliance runner for Phase C LAG/OVERSHOOT audit.

This module provides two symbols consumed by the Task 9 test suite:

  filter_events_by_geometry(events, slice_name) -> pd.DataFrame
      Delegates per-row geometry classification to classify_event_geometry
      (from pipeline.autoresearch.reverse_regime_breaks) and returns only
      the rows whose geometry matches the requested slice.

  SliceSpec
      Dataclass that holds slice_name + hypothesis_id and builds the output
      Path under pipeline/autoresearch/results/.

Design decision — option B (no run_slice_compliance in this task):
  The existing runner.main() is a 16-step procedural pipeline where events
  are built from raw price data inside Steps 4/4b (compute_residuals →
  classify_events → raw-bar canonicity gate). Injecting a pre-filtered
  events_override would require bypassing those steps entirely, which is
  non-trivial to thread through 300+ lines of tightly-coupled state.
  The full slice runner (run_slice_compliance) is deferred to Tasks 11/12
  where it will shell out to a refactored CLI or duplicate the orchestration
  explicitly.  The two symbols below are everything Task 9 requires.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
