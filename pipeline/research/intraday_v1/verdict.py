"""End-of-holdout strict-gate evaluator: §9, §9A Fragility, §9B Margin.

Per spec §9 thresholds:
- Hit-rate vs random null: p < 0.05 (single-tailed binomial)
- Sharpe (annualized) >= 0.5
- MaxDD (cumulative P&L) <= 5%
- §9A Fragility: >= 8 of 12 perturbations Sharpe-positive AND hit-rate > 50%
- §9B Margin: hit-rate beats max(always-long, always-short) by >= 0.5pp
"""
from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from scipy.stats import binomtest

SHARPE_FLOOR = 0.5
MAXDD_CEILING = 0.05  # 5% cumulative equity-curve drawdown (pnl_pct units / 100)
HITRATE_NULL = 0.5
HITRATE_ALPHA = 0.05
FRAGILITY_PASS_MIN = 8  # of 12 perturbations
FRAGILITY_TOTAL = 12
MARGIN_FLOOR_PP = 0.5  # percentage points


def compute_hit_rate(df: pd.DataFrame) -> float:
    closed = df[df["status"] == "CLOSED"]
    if closed.empty:
        return 0.0
    return float((closed["pnl_pct"] > 0).mean())


def compute_sharpe(df: pd.DataFrame) -> float:
    closed = df[df["status"] == "CLOSED"]
    if closed.empty:
        return 0.0
    daily = closed.groupby("instrument")["pnl_pct"].mean()  # crude proxy if no date col
    if daily.std() == 0:
        return 0.0
    return float(daily.mean() / daily.std() * sqrt(252))


def compute_max_drawdown(df: pd.DataFrame) -> float:
    closed = df[df["status"] == "CLOSED"]
    if closed.empty:
        return 0.0
    cum = closed["pnl_pct"].cumsum() / 100.0
    peak = cum.cummax()
    dd = (peak - cum).max()
    return float(dd)


def compute_baseline_hit_rate(df: pd.DataFrame) -> float:
    """Better of always-long / always-short hit rates on the same instruments."""
    closed = df[df["status"] == "CLOSED"]
    if closed.empty:
        return 0.0
    always_long_hits = float((closed["pnl_pct"] > 0).mean())  # implementations may vary
    always_short_hits = 1.0 - always_long_hits
    return max(always_long_hits, always_short_hits)


def hit_rate_pvalue(df: pd.DataFrame) -> float:
    closed = df[df["status"] == "CLOSED"]
    if closed.empty:
        return 1.0
    n_wins = int((closed["pnl_pct"] > 0).sum())
    n = len(closed)
    res = binomtest(n_wins, n, p=HITRATE_NULL, alternative="greater")
    return float(res.pvalue)


def fragility_pass_count(fragility: Dict) -> int:
    """Count perturbations with sharpe > 0 AND hit_rate > 0.50."""
    perturbed = fragility.get("perturbed_results", [])
    cnt = 0
    for p in perturbed:
        if p.get("sharpe", -1) > 0 and p.get("hit_rate", 0) > 0.50:
            cnt += 1
    return cnt


def evaluate(df: pd.DataFrame, fragility: Dict, baseline_hit_rate: float) -> Dict:
    hit = compute_hit_rate(df)
    sharpe = compute_sharpe(df)
    maxdd = compute_max_drawdown(df)
    pvalue = hit_rate_pvalue(df)
    frag_pass = fragility_pass_count(fragility)
    margin_pp = (hit - baseline_hit_rate) * 100.0

    reasons = []
    if pvalue >= HITRATE_ALPHA:
        reasons.append("BELOW_HITRATE_SIGNIFICANCE")
    if sharpe < SHARPE_FLOOR:
        reasons.append("BELOW_SHARPE")
    if maxdd > MAXDD_CEILING:
        reasons.append("ABOVE_MAXDD")
    if frag_pass < FRAGILITY_PASS_MIN:
        reasons.append(f"FRAGILITY_{frag_pass}/{FRAGILITY_TOTAL}")
    if margin_pp < MARGIN_FLOOR_PP:
        reasons.append("BELOW_MARGIN")

    if not reasons:
        return {
            "pass": True,
            "reason": "ALL_GATES_CLEAR",
            "hit_rate": hit,
            "hit_rate_pvalue": pvalue,
            "sharpe": sharpe,
            "max_drawdown": maxdd,
            "fragility_pass_count": frag_pass,
            "fragility_total": FRAGILITY_TOTAL,
            "margin_pp": margin_pp,
            "baseline_hit_rate": baseline_hit_rate,
        }
    return {
        "pass": False,
        "reason": " | ".join(reasons),
        "hit_rate": hit,
        "hit_rate_pvalue": pvalue,
        "sharpe": sharpe,
        "max_drawdown": maxdd,
        "fragility_pass_count": frag_pass,
        "fragility_total": FRAGILITY_TOTAL,
        "margin_pp": margin_pp,
        "baseline_hit_rate": baseline_hit_rate,
    }


def write_verdict(df: pd.DataFrame, fragility: Dict, baseline_hit_rate: float, out_path: Path) -> Dict:
    v = evaluate(df, fragility, baseline_hit_rate)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(v, indent=2, default=str), encoding="utf-8")
    return v
