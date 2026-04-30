"""Phase A-Sector: descriptive sector x regime behavior matrix.

Spec: docs/superpowers/specs/2026-04-30-sector-regime-behavior-table-design.md

Reads:
  pipeline/data/research/sector_panel/sector_index_panel.parquet  (22 sectors, daily log returns)
  pipeline/data/research/etf_v3/regime_tape_5y_pit.csv              (PIT regime tape using V3 CURATED-30 frozen weights)

Writes:
  pipeline/data/research/sector_regime/sector_regime_matrix_<date>.csv
  pipeline/data/research/sector_regime/sector_regime_matrix_<date>.md

This is DESCRIPTIVE ONLY. Cells that look interesting feed into NEW
hypotheses (e.g., "Pharma in RISK-OFF earns +X bps with hit Y%") that
then go through the full single-touch holdout pipeline. No edge claim
made by this report.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SECTOR_PANEL = REPO_ROOT / "pipeline" / "data" / "research" / "sector_panel" / "sector_index_panel.parquet"
REGIME_TAPE = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "sector_regime"

VERDICT_BAR = {
    "mean_bps_min": 0,
    "hit_rate_pct_min": 55,
    "sharpe_min": 0.5,
    "bootstrap_stability_pct_min": 70,
    "min_n": 30,
}


def load_panel() -> pd.DataFrame:
    df = pd.read_parquet(SECTOR_PANEL)
    df.index = pd.DatetimeIndex(df.index).normalize()
    return df


def load_regime() -> pd.Series:
    df = pd.read_csv(REGIME_TAPE, parse_dates=["date"])
    s = pd.Series(df["regime"].values, index=pd.DatetimeIndex(df["date"]).normalize())
    s.name = "regime"
    return s


def annualized_sharpe(returns: np.ndarray) -> float:
    if len(returns) < 2:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std == 0.0:
        return 0.0
    return float((np.mean(returns) / std) * math.sqrt(252))


def annualized_vol_pct(returns: np.ndarray) -> float:
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * math.sqrt(252) * 100.0)


def max_drawdown_pct(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return 0.0
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(dd.min() * 100.0)


def bootstrap_mean_positive(returns: np.ndarray, iters: int = 200, window: int = 252, seed: int = 42) -> float:
    """Fraction of bootstrap samples (size=min(len, window)) where mean > 0."""
    if len(returns) < 30:
        return 0.0
    rng = np.random.default_rng(seed)
    n = min(len(returns), window)
    pos = 0
    for _ in range(iters):
        sample = rng.choice(returns, size=n, replace=True)
        if float(np.mean(sample)) > 0:
            pos += 1
    return 100.0 * pos / iters


def cell_metrics(returns: np.ndarray) -> dict[str, Any]:
    if len(returns) == 0:
        return {
            "n_days": 0,
            "mean_bps": 0.0,
            "hit_rate_pct": 0.0,
            "vol_annualized_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "bootstrap_pos_pct": 0.0,
            "verdict": "INSUFFICIENT_N",
        }
    mean_bps = float(np.mean(returns) * 1e4)
    hit_pct = float((returns > 0).mean() * 100.0)
    vol_pct = annualized_vol_pct(returns)
    mdd_pct = max_drawdown_pct(returns)
    sharpe = annualized_sharpe(returns)
    boot_pct = bootstrap_mean_positive(returns)

    verdict = "DESCRIPTIVE_ONLY"
    if len(returns) >= VERDICT_BAR["min_n"]:
        if (
            mean_bps > VERDICT_BAR["mean_bps_min"]
            and hit_pct >= VERDICT_BAR["hit_rate_pct_min"]
            and sharpe >= VERDICT_BAR["sharpe_min"]
            and boot_pct >= VERDICT_BAR["bootstrap_stability_pct_min"]
        ):
            verdict = "PROMOTABLE_TO_HYPOTHESIS"
        else:
            verdict = "DESCRIPTIVE_ONLY"
    else:
        verdict = "INSUFFICIENT_N"

    return {
        "n_days": int(len(returns)),
        "mean_bps": round(mean_bps, 3),
        "hit_rate_pct": round(hit_pct, 2),
        "vol_annualized_pct": round(vol_pct, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "sharpe": round(sharpe, 4),
        "bootstrap_pos_pct": round(boot_pct, 1),
        "verdict": verdict,
    }


def build_matrix(panel: pd.DataFrame, regime: pd.Series) -> pd.DataFrame:
    aligned = panel.join(regime, how="inner")
    rows = []
    sectors = [c for c in panel.columns if c != "regime"]
    for sector in sectors:
        # Unconditional row
        all_ret = aligned[sector].dropna().values
        m = cell_metrics(all_ret)
        rows.append({"sector": sector, "regime": "ALL", **m})
        # Per-regime rows
        for rg, g in aligned.groupby("regime"):
            ret = g[sector].dropna().values
            m = cell_metrics(ret)
            rows.append({"sector": sector, "regime": str(rg), **m})
    return pd.DataFrame(rows)


def render_markdown(df: pd.DataFrame, run_date: str) -> str:
    lines: list[str] = []
    lines.append(f"# Sector x regime behavior matrix — {run_date}")
    lines.append("")
    lines.append(
        "Descriptive only (per spec section 'What this study does NOT do'). "
        "Cells flagged PROMOTABLE_TO_HYPOTHESIS are CANDIDATES for new pre-registered "
        "hypotheses, NOT trade signals. They feed the autoresearch v2 hypothesis "
        "proposal queue."
    )
    lines.append("")

    # Pivot: rows = sectors, cols = regimes, values = mean_bps
    pv_mean = df.pivot(index="sector", columns="regime", values="mean_bps")
    pv_hit = df.pivot(index="sector", columns="regime", values="hit_rate_pct")
    pv_n = df.pivot(index="sector", columns="regime", values="n_days")
    pv_verdict = df.pivot(index="sector", columns="regime", values="verdict")

    regime_order = ["ALL", "RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA"]
    pv_mean = pv_mean[[r for r in regime_order if r in pv_mean.columns]]
    pv_hit = pv_hit[[r for r in regime_order if r in pv_hit.columns]]
    pv_n = pv_n[[r for r in regime_order if r in pv_n.columns]]
    pv_verdict = pv_verdict[[r for r in regime_order if r in pv_verdict.columns]]

    lines.append("## Mean daily return (basis points)")
    lines.append("")
    lines.append(pv_mean.round(2).to_markdown())
    lines.append("")

    lines.append("## Hit rate (% of days positive)")
    lines.append("")
    lines.append(pv_hit.round(1).to_markdown())
    lines.append("")

    lines.append("## n_days per cell")
    lines.append("")
    lines.append(pv_n.to_markdown())
    lines.append("")

    promotable = df[df["verdict"] == "PROMOTABLE_TO_HYPOTHESIS"].copy()
    lines.append("## Cells flagged PROMOTABLE_TO_HYPOTHESIS")
    lines.append("")
    if len(promotable) == 0:
        lines.append("None — every (sector × regime) cell is descriptive only at the strict bar.")
    else:
        promotable = promotable.sort_values("mean_bps", ascending=False)
        cols = ["sector", "regime", "n_days", "mean_bps", "hit_rate_pct", "sharpe", "bootstrap_pos_pct"]
        lines.append(promotable[cols].to_markdown(index=False))
    lines.append("")

    lines.append("## Verdict bar")
    lines.append(f"- mean > 0 bps")
    lines.append(f"- hit rate >= {VERDICT_BAR['hit_rate_pct_min']}%")
    lines.append(f"- annualized Sharpe >= {VERDICT_BAR['sharpe_min']}")
    lines.append(f"- bootstrap mean-positive fraction >= {VERDICT_BAR['bootstrap_stability_pct_min']}%")
    lines.append(f"- n_days per cell >= {VERDICT_BAR['min_n']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
    log = logging.getLogger("sector_regime_matrix")

    panel = load_panel()
    regime = load_regime()
    log.info("panel %s, regime span %s -> %s", panel.shape, regime.index.min(), regime.index.max())

    df = build_matrix(panel, regime)
    args.out.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    csv_path = args.out / f"sector_regime_matrix_{today}.csv"
    md_path = args.out / f"sector_regime_matrix_{today}.md"
    df.to_csv(csv_path, index=False)
    md_path.write_text(render_markdown(df, today), encoding="utf-8")

    n_promotable = int((df["verdict"] == "PROMOTABLE_TO_HYPOTHESIS").sum())
    n_desc = int((df["verdict"] == "DESCRIPTIVE_ONLY").sum())
    n_insuff = int((df["verdict"] == "INSUFFICIENT_N").sum())

    print(json.dumps({
        "csv": str(csv_path.relative_to(REPO_ROOT)),
        "md": str(md_path.relative_to(REPO_ROOT)),
        "n_cells": int(len(df)),
        "n_promotable": n_promotable,
        "n_descriptive": n_desc,
        "n_insufficient_n": n_insuff,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
