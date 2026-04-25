"""Build Tables A-G + pick verdict + render markdown.

Spec §6 (analysis) + §7 (verdict thresholds).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from pipeline.autoresearch.phase_c_shape_audit import constants as C


def _cell_n_winrate(df: pd.DataFrame) -> tuple[int, float, float]:
    n = len(df)
    if n == 0:
        return 0, float("nan"), float("nan")
    wr = float(df["cf_grid_avg_win"].mean())
    avg_pnl = float(df["cf_grid_avg_pnl_pct"].mean())
    return n, wr, avg_pnl


def _table_shape_x_side_x_source(df: pd.DataFrame) -> pd.DataFrame:
    grp = df.groupby(["shape", "trade_rec", "source"], dropna=False).size().unstack(fill_value=0)
    return grp.reset_index()


def _table_winrate_by_shape_side(df: pd.DataFrame, view: str) -> pd.DataFrame:
    if view == "actual":
        sub = df[df["source"] == "actual"].dropna(subset=["actual_pnl_pct"]).copy()
        sub["win"] = sub["actual_pnl_pct"] > 0
        sub["pnl"] = sub["actual_pnl_pct"]
    elif view == "cf_grid_avg":
        sub = df.dropna(subset=["cf_grid_avg_pnl_pct"]).copy()
        sub["win"] = sub["cf_grid_avg_win"]
        sub["pnl"] = sub["cf_grid_avg_pnl_pct"]
    else:
        sub = df.dropna(subset=["cf_best_grid_pnl_pct"]).copy()
        sub["win"] = sub["cf_best_grid_pnl_pct"] > 0
        sub["pnl"] = sub["cf_best_grid_pnl_pct"]
    if sub.empty:
        return pd.DataFrame(columns=["shape", "trade_rec", "n", "win_rate", "avg_pnl_pct"])
    grp = sub.groupby(["shape", "trade_rec"], dropna=False).agg(
        n=("win", "size"),
        win_rate=("win", "mean"),
        avg_pnl_pct=("pnl", "mean"),
    ).reset_index()
    return grp


def _table_regime_cube(df: pd.DataFrame) -> pd.DataFrame:
    sub = df.dropna(subset=["cf_grid_avg_pnl_pct"]).copy()
    if sub.empty:
        return pd.DataFrame(columns=["regime", "shape", "trade_rec", "n", "win_rate", "avg_pnl_pct"])
    sub["win"] = sub["cf_grid_avg_win"]
    grp = sub.groupby(["regime", "shape", "trade_rec"], dropna=False).agg(
        n=("win", "size"),
        win_rate=("win", "mean"),
        avg_pnl_pct=("cf_grid_avg_pnl_pct", "mean"),
    ).reset_index()
    return grp


def _pick_verdict(table_b_cf: pd.DataFrame, table_f: pd.DataFrame, df: pd.DataFrame) -> str:
    """Spec §7."""
    valid = df.dropna(subset=["cf_grid_avg_pnl_pct"])
    if len(valid) < C.MIN_CELL_N:
        return "INSUFFICIENT_N"

    qualifying = table_b_cf[
        (table_b_cf["n"] >= C.MIN_CELL_N)
        & (table_b_cf["win_rate"] >= C.CONFIRMED_WIN_RATE)
    ]

    if not qualifying.empty:
        for _, row in qualifying.iterrows():
            n_wins = int(row["n"] * row["win_rate"])
            test = binomtest(n_wins, int(row["n"]), p=C.BASELINE_WIN_RATE, alternative="greater")
            if test.pvalue < 0.05:
                actual_rows = df.dropna(subset=["actual_pnl_pct"])
                if not actual_rows.empty:
                    delta = (actual_rows["actual_pnl_pct"] - actual_rows["cf_grid_avg_pnl_pct"]).mean()
                    if delta > 0:
                        continue

                cube_match = table_f[
                    (table_f["shape"] == row["shape"])
                    & (table_f["trade_rec"] == row["trade_rec"])
                    & (table_f["n"] >= C.MIN_CELL_N)
                    & (table_f["win_rate"] >= C.CONFIRMED_WIN_RATE)
                ]
                survived = len(cube_match)
                if survived >= C.REGIME_SURVIVAL_MIN:
                    return "CONFIRMED"
                if survived == 1:
                    return "REGIME_CONDITIONAL_CONFIRMED"

    weak = table_b_cf[
        (table_b_cf["n"] >= C.MIN_CELL_N)
        & (table_b_cf["win_rate"] >= C.WEAK_WIN_RATE_LO)
        & (table_b_cf["win_rate"] < C.WEAK_WIN_RATE_HI)
    ]
    if not weak.empty:
        return "WEAK_SIGNAL"

    actual_rows = df.dropna(subset=["actual_pnl_pct"])
    if not actual_rows.empty:
        delta = (actual_rows["cf_grid_avg_pnl_pct"] - actual_rows["actual_pnl_pct"]).mean()
        if delta > C.DISCIPLINE_DELTA_PP:
            return "DISCIPLINE_ONLY"

    return "NULL"


def build_report(per_trade_df: pd.DataFrame) -> dict[str, Any]:
    """Build Tables A-G + pick verdict. Returns dict keyed by table name + 'verdict'."""
    valid = per_trade_df[per_trade_df["validation"] == "OK"].copy() if "validation" in per_trade_df.columns else per_trade_df.copy()

    table_a = _table_shape_x_side_x_source(valid)
    table_b_actual = _table_winrate_by_shape_side(valid, "actual")
    table_b_cf = _table_winrate_by_shape_side(valid, "cf_grid_avg")
    table_b_best = (
        _table_winrate_by_shape_side(valid, "cf_best_grid")
        if "cf_best_grid_pnl_pct" in valid.columns else pd.DataFrame()
    )
    table_f = _table_regime_cube(valid)

    verdict = _pick_verdict(table_b_cf, table_f, valid)

    return {
        "table_a_distribution": table_a,
        "table_b_actual": table_b_actual,
        "table_b_cf_grid_avg": table_b_cf,
        "table_b_cf_best_grid": table_b_best,
        "table_f_regime_cube": table_f,
        "verdict": verdict,
        "n_total": len(per_trade_df),
        "n_valid": len(valid),
    }


def render_markdown(report_dict: dict[str, Any], window_start: pd.Timestamp, window_end: pd.Timestamp) -> str:
    """Render the report dict to a markdown document body."""
    lines: list[str] = []
    lines.append("# Phase C Intraday Shape Audit — SP1 Report\n")
    lines.append(f"**Window:** {window_start.date()} → {window_end.date()}")
    lines.append(f"**N total roster:** {report_dict['n_total']}  ")
    lines.append(f"**N valid (after BARS_INSUFFICIENT/MISMATCH):** {report_dict['n_valid']}")
    lines.append(f"**Verdict:** **{report_dict['verdict']}**\n")

    for key, label in [
        ("table_a_distribution", "Table A — Shape × side × source distribution"),
        ("table_b_actual", "Table B-actual — Win rate × shape × side (actual P&L)"),
        ("table_b_cf_grid_avg", "Table B-cf — Win rate × shape × side (counterfactual grid avg)"),
        ("table_b_cf_best_grid", "Table B-best — Win rate × shape × side (counterfactual best grid)"),
        ("table_f_regime_cube", "Table F — Regime × shape × side cube"),
    ]:
        df = report_dict.get(key)
        lines.append(f"## {label}\n")
        if df is None or len(df) == 0:
            lines.append("_(empty)_\n")
        else:
            lines.append(df.to_markdown(index=False))
            lines.append("")
    return "\n".join(lines)
