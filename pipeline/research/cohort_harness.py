"""Generic cohort harness — any signal ledger × any feature function → cells.

Replaces the per-engine boilerplate that currently lives in
neutral_cohort_tracker.py + future analogues. New analyses register a
TrackerSpec and call run_tracker(spec). The harness handles:

  - loading the ledger
  - filtering CLOSED rows
  - calling user-supplied feature functions per row
  - aggregating cells per the standard recipe (PUBLISH/MONITOR/INSUFFICIENT)
  - writing trades CSV + cells CSV + summary JSON

Cell publication thresholds are constants here so every tracker uses the
same bar:
  PUBLISH_THRESHOLD = 30
  MONITOR_THRESHOLD = 10

Per analysis, register a TrackerSpec and call run_tracker(spec). Each new
analysis is ~30 lines of config, not a 300-line module rewrite.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = PIPELINE_ROOT / "data" / "research"

IST = timezone(timedelta(hours=5, minutes=30))
PUBLISH_THRESHOLD = 30
MONITOR_THRESHOLD = 10

log = logging.getLogger("cohort_harness")


@dataclass
class TrackerSpec:
    """Declarative description of a tracker run.

    Attributes:
      name: short identifier — output dir name, log prefix
      ledger_path: CSV that holds the signal+outcome ledger
      regime_filter: optional regime to keep ('NEUTRAL', None for all)
      pnl_col: column name with realized P&L percent
      status_col: column name with status (CLOSED filter)
      feature_fns: ordered map name → callable(row_dict) → float|None
      cell_fns: ordered map cell_name → callable(enriched_df) → boolean Series
      tertile_features: feature names to also bucket as LO/MID/HI tertiles
      out_subdir: subdirectory under data/research/
    """
    name: str
    ledger_path: Path
    pnl_col: str = "pnl_pct"
    status_col: str = "status"
    closed_value: str = "CLOSED"
    regime_col: Optional[str] = "regime"
    regime_filter: Optional[str] = None
    feature_fns: dict[str, Callable] = field(default_factory=dict)
    cell_fns: dict[str, Callable] = field(default_factory=dict)
    tertile_features: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    out_subdir: Optional[str] = None


def _cell_status(n: int) -> str:
    if n >= PUBLISH_THRESHOLD:
        return "PUBLISH"
    if n >= MONITOR_THRESHOLD:
        return "MONITOR"
    return "INSUFFICIENT"


def _tertile_labels(values: pd.Series, prefix: str) -> tuple[pd.Series, dict]:
    sub = values.dropna()
    if len(sub) < MONITOR_THRESHOLD:
        return pd.Series([None] * len(values), index=values.index), {}
    q1, q3 = sub.quantile([1 / 3, 2 / 3])

    def label(v: float) -> Optional[str]:
        if pd.isna(v):
            return None
        if v <= q1:
            return f"{prefix}_LO"
        if v >= q3:
            return f"{prefix}_HI"
        return f"{prefix}_MID"

    return values.apply(label), {"q1": float(q1), "q3": float(q3)}


def _aggregate_cells(df: pd.DataFrame, spec: TrackerSpec) -> tuple[pd.DataFrame, dict]:
    cells: list[dict] = []
    cuts: dict[str, dict] = {}

    win_col = "win"
    pnl_col = spec.pnl_col

    def add_cell(name: str, mask: pd.Series) -> None:
        sub = df[mask]
        n = int(len(sub))
        if n == 0:
            return
        cells.append({
            "cell": name,
            "N": n,
            "win_pct": round(sub[win_col].mean() * 100, 2),
            "mean_pnl_pct": round(sub[pnl_col].mean(), 3),
            "median_pnl_pct": round(sub[pnl_col].median(), 3),
            "status": _cell_status(n),
        })

    add_cell("ALL", pd.Series([True] * len(df), index=df.index))

    for col in spec.extra_columns:
        if col not in df.columns:
            continue
        for v in df[col].dropna().unique():
            add_cell(f"{col}={v}", df[col] == v)

    for cell_name, mask_fn in spec.cell_fns.items():
        try:
            mask = mask_fn(df)
            add_cell(cell_name, mask)
        except Exception as exc:
            log.warning("cell_fn %s failed: %s", cell_name, exc)

    for feat_name in spec.tertile_features:
        if feat_name not in df.columns:
            continue
        labels, cut = _tertile_labels(df[feat_name], feat_name)
        cuts[feat_name] = cut
        for tag in (f"{feat_name}_LO", f"{feat_name}_MID", f"{feat_name}_HI"):
            mask = labels == tag
            if mask.sum():
                add_cell(tag, mask)

    cells_df = pd.DataFrame(cells)
    if not cells_df.empty:
        cells_df["status_rank"] = cells_df["status"].map(
            {"PUBLISH": 0, "MONITOR": 1, "INSUFFICIENT": 2}).fillna(3)
        cells_df = cells_df.sort_values(
            ["status_rank", "win_pct"], ascending=[True, False]
        ).drop(columns=["status_rank"]).reset_index(drop=True)

    return cells_df, cuts


def run_tracker(spec: TrackerSpec) -> dict:
    """Run a tracker per spec; write outputs; return summary dict."""
    if not spec.ledger_path.exists():
        raise FileNotFoundError(f"ledger missing: {spec.ledger_path}")
    raw = pd.read_csv(spec.ledger_path)
    closed = raw[raw[spec.status_col] == spec.closed_value].copy()
    if spec.regime_filter and spec.regime_col in closed.columns:
        closed = closed[closed[spec.regime_col] == spec.regime_filter].copy()
    if closed.empty:
        raise RuntimeError(f"{spec.name}: no CLOSED rows after filters")

    closed[spec.pnl_col] = pd.to_numeric(closed[spec.pnl_col], errors="coerce")
    closed = closed.dropna(subset=[spec.pnl_col]).reset_index(drop=True)
    closed["win"] = (closed[spec.pnl_col] > 0).astype(int)

    for fname, fn in spec.feature_fns.items():
        log.info("computing feature %s", fname)
        closed[fname] = closed.apply(lambda r: fn(r.to_dict()), axis=1)

    cells_df, cuts = _aggregate_cells(closed, spec)

    out_dir = RESEARCH_DIR / (spec.out_subdir or spec.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y_%m_%d")
    trades_csv = out_dir / f"trades_{spec.name}_{today}.csv"
    cells_csv = out_dir / f"by_cell_{spec.name}_{today}.csv"
    cells_latest = out_dir / f"by_cell_{spec.name}_latest.csv"
    summary_json = out_dir / f"summary_{spec.name}_{today}.json"

    closed.to_csv(trades_csv, index=False, float_format="%.4f")
    cells_df.to_csv(cells_csv, index=False, float_format="%.4f")
    cells_df.to_csv(cells_latest, index=False, float_format="%.4f")

    publish_cells = cells_df[cells_df["status"] == "PUBLISH"] if not cells_df.empty else pd.DataFrame()
    monitor_cells = cells_df[cells_df["status"] == "MONITOR"] if not cells_df.empty else pd.DataFrame()
    summary = {
        "as_of": datetime.now(IST).isoformat(),
        "tracker": spec.name,
        "source": str(spec.ledger_path.relative_to(PIPELINE_ROOT)),
        "regime_filter": spec.regime_filter,
        "n_trades": int(len(closed)),
        "baseline_win_pct": round(closed["win"].mean() * 100, 2),
        "baseline_mean_pnl_pct": round(closed[spec.pnl_col].mean(), 3),
        "publish_cells": publish_cells.to_dict(orient="records"),
        "monitor_cells": monitor_cells.to_dict(orient="records"),
        "n_publish": int(len(publish_cells)),
        "n_monitor": int(len(monitor_cells)),
        "publish_threshold": PUBLISH_THRESHOLD,
        "monitor_threshold": MONITOR_THRESHOLD,
        "tertile_cuts": cuts,
        "trades_csv": str(trades_csv.relative_to(PIPELINE_ROOT)),
        "cells_csv": str(cells_csv.relative_to(PIPELINE_ROOT)),
    }
    summary_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def print_summary(s: dict) -> None:
    print(f"=== Cohort Tracker: {s['tracker']} — {s['as_of']} ===")
    print(f"Source: {s['source']}")
    if s.get("regime_filter"):
        print(f"Regime filter: {s['regime_filter']}")
    print(f"N CLOSED: {s['n_trades']}")
    print(f"Baseline: win={s['baseline_win_pct']:.2f}%, mean PnL={s['baseline_mean_pnl_pct']:+.3f}%")
    print(f"Cells: PUBLISH={s['n_publish']}, MONITOR={s['n_monitor']}")
    print()
    for cell in s["publish_cells"]:
        print(f"  PUBLISH  {cell['cell']:<32}  N={cell['N']:>4}  "
              f"win={cell['win_pct']:>6.2f}%  mean={cell['mean_pnl_pct']:>+7.3f}%")
    for cell in s["monitor_cells"]:
        print(f"  MONITOR  {cell['cell']:<32}  N={cell['N']:>4}  "
              f"win={cell['win_pct']:>6.2f}%  mean={cell['mean_pnl_pct']:>+7.3f}%")
