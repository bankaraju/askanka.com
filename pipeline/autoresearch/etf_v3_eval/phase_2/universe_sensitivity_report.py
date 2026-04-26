# pipeline/autoresearch/etf_v3_eval/phase_2/universe_sensitivity_report.py
"""Writes pipeline/data/research/etf_v3_evaluation/phase_2_backtest/universe_sensitivity.md.

Compares per-marker results across u126 (126-ticker universe) vs u273
(273-ticker universe) to test whether edge conclusions are robust to
universe definition.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

# Single source of truth for column ordering — header and row formatting are
# both derived from this constant so they can never drift apart.
_HEADER_COLS = [
    "Marker",
    "u126 mean P&L",
    "u126 n",
    "u273 mean P&L",
    "u273 n",
    "Δ pp",
    "Verdict changed",
]

_REQUIRED_KEYS = frozenset(
    {"marker", "u126_mean_pnl", "u273_mean_pnl", "u126_n", "u273_n",
     "delta_pp", "verdict_changed"}
)


def _validate_row(row: dict) -> None:
    """Raise ValueError if any required key is absent from row."""
    missing = _REQUIRED_KEYS - set(row.keys())
    if missing:
        raise ValueError(
            f"universe_sensitivity_report: row is missing required keys {sorted(missing)}; "
            f"keys present: {sorted(row.keys())}"
        )


def write_universe_sensitivity_md(rows: Iterable[dict], out_path: Path) -> None:
    """Write a markdown universe-sensitivity table to out_path.

    Parameters
    ----------
    rows:
        Iterable of dicts with keys: marker, u126_mean_pnl, u273_mean_pnl,
        u126_n, u273_n, delta_pp, verdict_changed.
        Each row is validated before writing; ValueError is raised on the first
        row with missing keys (lists missing keys + keys present).
    out_path:
        Destination path. Parent directories are created automatically.

    Notes
    -----
    Empty rows input produces a header-only table with an explicit
    "No marker rows supplied" note rather than crashing.
    """
    # Materialise the iterable once so we can check emptiness and validate.
    row_list = list(rows)

    # Validate all rows before touching the filesystem.
    for row in row_list:
        _validate_row(row)

    # Derive markdown header and alignment row from the constant.
    header_line = "| " + " | ".join(_HEADER_COLS) + " |"
    align_cells = ["---", "---:", "---:", "---:", "---:", "---:", "---"]
    align_line = "| " + " | ".join(align_cells) + " |"

    lines = [
        "# Phase 2 Universe Sensitivity (126 vs 273)",
        "",
        header_line,
        align_line,
    ]

    if not row_list:
        lines.append("| — | — | — | — | — | — | — |")
        lines.append("")
        lines.append("*No marker rows supplied.*")
    else:
        for r in row_list:
            lines.append(
                f"| {r['marker']} | {r['u126_mean_pnl']:.4f} | {r['u126_n']} | "
                f"{r['u273_mean_pnl']:.4f} | {r['u273_n']} | {r['delta_pp']:+.2f} | "
                f"{'YES' if r['verdict_changed'] else 'no'} |"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
