"""Canonical, audited sector-index panel — read-side library.

The first study that needed an audited sector panel was the 2026-04-30
sector-correlation study. Per the user directive 2026-04-30 ("when we
do the data validation and backfill it and ensure completeness — that
data set must be used for all future tests rather than keep on doing
the same thing"), the panel is built ONCE through the audit gate and
then read by every downstream study via :func:`load_canonical_panel`.

Public API:

    >>> from pipeline.research.sector_panel import load_canonical_panel
    >>> panel = load_canonical_panel()         # validated parquet, read-only
    >>> meta  = load_canonical_metadata()      # registration sidecar dict

The panel is a DataFrame indexed by Date, columns = sector keys,
values = equal-weighted daily log returns of constituent F&O tickers.

The build path lives in ``builder.py`` and runs through the
``anka_data_validation_policy_global_standard.md`` gate. The build
emits a provenance sidecar so consumers can verify they're reading
the dataset they think they are.
"""

from .builder import (
    build_canonical_panel,
    load_canonical_panel,
    load_canonical_metadata,
    CANONICAL_PANEL_PATH,
    CANONICAL_METADATA_PATH,
)

__all__ = [
    "build_canonical_panel",
    "load_canonical_panel",
    "load_canonical_metadata",
    "CANONICAL_PANEL_PATH",
    "CANONICAL_METADATA_PATH",
]
