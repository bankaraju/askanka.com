# pipeline/autoresearch/etf_v3_eval/phase_2/decomposition_report.py
"""Writes pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md.

Per marker rows include: standalone P&L, incremental contribution after stacking,
cluster-robust SE, permutation null p-value, fragility verdict, naive benchmark p.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

# Single source of truth for column ordering — header and row formatting are
# both derived from this constant so they can never drift apart.
_HEADER_COLS = [
    "Marker",
    "n",
    "Mean P&L",
    "SE (cluster)",
    "Incremental",
    "Permutation p",
    "Naive random p",
    "Fragility",
]

_REQUIRED_KEYS = frozenset(
    {"marker", "n_trades", "mean_pnl", "se", "p_perm", "fragility",
     "incremental_pnl", "naive_random_p"}
)


def _validate_row(row: dict) -> None:
    """Raise ValueError if any required key is absent from row."""
    missing = _REQUIRED_KEYS - set(row.keys())
    if missing:
        raise ValueError(
            f"decomposition_report: row is missing required keys {sorted(missing)}; "
            f"keys present: {sorted(row.keys())}"
        )


def write_markers_decomposition_md(rows: Iterable[dict], out_path: Path) -> None:
    """Write a markdown marker-decomposition table to out_path.

    Parameters
    ----------
    rows:
        Iterable of dicts with keys: marker, n_trades, mean_pnl, se, p_perm,
        fragility, incremental_pnl, naive_random_p.
        Each row is validated before writing; ValueError is raised on the first
        row with missing keys (lists missing keys + keys present).
    out_path:
        Destination path. Parent directories are created automatically.

    Notes
    -----
    Empty rows input produces a header-only table with an explicit
    "No marker rows supplied" note rather than crashing. This is intentional
    because T6 step output may legitimately be empty if all markers are
    filtered out.
    """
    # Materialise the iterable once so we can check emptiness and validate.
    row_list = list(rows)

    # Validate all rows before touching the filesystem.
    for row in row_list:
        _validate_row(row)

    # Derive markdown header and alignment row from the constant.
    header_line = "| " + " | ".join(_HEADER_COLS) + " |"
    align_cells = ["---", "---:", "---:", "---:", "---:", "---:", "---:", "---"]
    align_line = "| " + " | ".join(align_cells) + " |"

    lines = [
        "# Phase 2 Marker Decomposition",
        "",
        header_line,
        align_line,
    ]

    if not row_list:
        lines.append("| — | — | — | — | — | — | — | — |")
        lines.append("")
        lines.append("*No marker rows supplied.*")
    else:
        for r in row_list:
            lines.append(
                f"| {r['marker']} | {r['n_trades']} | {r['mean_pnl']:.4f} | "
                f"{r['se']:.4f} | {r['incremental_pnl']:.4f} | {r['p_perm']:.3f} | "
                f"{r['naive_random_p']:.3f} | {r['fragility']} |"
            )

    lines.append("")
    lines.append(
        "Cluster level: trade_date. "
        "n trades = events surviving the marker stack at that point."
    )
    lines.append(
        "Permutation null: 10,000 shuffles two-sided, "
        "naive_random_p = signed-flip benchmark."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
