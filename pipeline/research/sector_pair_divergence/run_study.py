"""Sector pair divergence-reversion — discovery study.

Run with:  python -m pipeline.research.sector_pair_divergence.run_study

Spec: docs/research/sector_pair_divergence/2026-04-30-design.md

Tests the user hypothesis (2026-04-30): when a normally tight pair like
Banks × NBFC_HFC diverges by >k·σ on day d, does the spread close on
day d+1 enough to make the contrarian pair-trade pay?

Reads from the canonical sector panel — ONE registered dataset, no
re-validation per study (per Anka data-validation policy + 2026-04-30
user directive).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("anka.sector_pair_divergence")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "sector_pair_divergence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---- Locked at study start. Do not edit post-look. ------------------------
PAIRS = [
    ("Banks", "NBFC_HFC"),
    ("Capital_Goods", "Logistics_Transport"),
    ("Capital_Goods", "NBFC_HFC"),
    ("NBFC_HFC", "Infra_EPC"),
    ("Logistics_Transport", "NBFC_HFC"),
    ("Capital_Goods", "Infra_EPC"),
    ("Power_Utilities", "Oil_Gas"),
    ("Capital_Goods", "Power_Utilities"),
    ("Power_Utilities", "Logistics_Transport"),
    ("Logistics_Transport", "Infra_EPC"),
]
THRESHOLDS_K = [1.0, 1.5, 2.0, 2.5]   # in σ_s units, full-sample
ROUND_TRIP_BPS = 20.0                  # 5 bp per leg per turn × 4 legs
N_BOOTSTRAP = 200
BOOTSTRAP_WINDOW_DAYS = 252
RNG_SEED = 20260430
BH_FDR_ALPHA = 0.10
T_STAT_BAR = 2.0
STABILITY_FRAC_BAR = 0.60              # bootstrap windows positive after cost
HOLDING_DAYS = 1                       # next-day reversion only
# ---------------------------------------------------------------------------


def _t_stat(x: np.ndarray) -> float:
    if len(x) < 3:
        return 0.0
    sd = float(np.std(x, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(x)) / (sd / np.sqrt(len(x)))


def _bh_fdr(pvals: list[float], alpha: float) -> list[bool]:
    """Benjamini-Hochberg. Returns True/False per input p-value (in order)."""
    n = len(pvals)
    if n == 0:
        return []
    order = np.argsort(pvals)
    ranked = np.array(pvals)[order]
    crit = (np.arange(1, n + 1) / n) * alpha
    passed = ranked <= crit
    if not passed.any():
        survive_idx = -1
    else:
        survive_idx = int(np.max(np.where(passed)[0]))
    out = [False] * n
    for k in range(survive_idx + 1):
        out[order[k]] = True
    return out


def _two_sided_p(t: float, n: int) -> float:
    """Conservative two-sided p from t-stat using normal approx (n>=30)."""
    if n < 3:
        return 1.0
    from math import erfc, sqrt
    z = abs(t)
    return float(erfc(z / sqrt(2.0)))


def _enumerate_events(panel: pd.DataFrame, a: str, b: str,
                       k_grid: list[float]) -> dict:
    """For one pair: full-sample σ_s, then per-k event series + next-day P&L."""
    s_i = panel[a]
    s_j = panel[b]
    aligned = pd.concat([s_i, s_j], axis=1).dropna()
    aligned.columns = ["A", "B"]
    if len(aligned) < BOOTSTRAP_WINDOW_DAYS + 50:
        return {"error": f"not enough aligned days ({len(aligned)})"}

    spread = aligned["A"] - aligned["B"]
    sigma_s = float(spread.std(ddof=1))
    if sigma_s == 0.0:
        return {"error": "zero spread variance"}

    next_day_A = aligned["A"].shift(-HOLDING_DAYS)
    next_day_B = aligned["B"].shift(-HOLDING_DAYS)
    raw_revert = -np.sign(spread) * (next_day_A - next_day_B)

    out = {
        "pair": f"{a}__{b}",
        "sigma_s": sigma_s,
        "n_aligned": len(aligned),
        "by_k": {},
    }

    cost = ROUND_TRIP_BPS / 1e4

    for k in k_grid:
        threshold = k * sigma_s
        mask = spread.abs() > threshold
        events = aligned[mask].index
        events_with_next = [d for d in events
                             if pd.notna(next_day_A.loc[d])
                             and pd.notna(next_day_B.loc[d])]
        n_events = len(events_with_next)
        if n_events == 0:
            out["by_k"][k] = {"n_events": 0}
            continue

        pnl_pre = raw_revert.loc[events_with_next].astype(float).values
        pnl_post = pnl_pre - cost

        win_pre = float(np.mean(pnl_pre > 0))
        win_post = float(np.mean(pnl_post > 0))
        t_pre = _t_stat(pnl_pre)
        t_post = _t_stat(pnl_post)
        p_post = _two_sided_p(t_post, n_events)

        out["by_k"][k] = {
            "n_events": n_events,
            "threshold_pct": threshold * 100,
            "mean_pnl_pre_bps": float(np.mean(pnl_pre)) * 1e4,
            "mean_pnl_post_bps": float(np.mean(pnl_post)) * 1e4,
            "median_pnl_post_bps": float(np.median(pnl_post)) * 1e4,
            "win_rate_pre": win_pre,
            "win_rate_post": win_post,
            "t_stat_pre": t_pre,
            "t_stat_post": t_post,
            "p_value_post": p_post,
            "events_dates": [str(d.date()) for d in events_with_next],
            "pnl_pre_series": pnl_pre.tolist(),
            "pnl_post_series": pnl_post.tolist(),
        }
    return out


def _bootstrap_pair_k(panel: pd.DataFrame, a: str, b: str, k: float) -> dict:
    """Bootstrap stability: re-run on N random 1y windows, record post-cost."""
    rng = np.random.default_rng(hash(f"{a}|{b}|{k}|{RNG_SEED}") % (2**32))
    aligned = pd.concat([panel[a], panel[b]], axis=1).dropna()
    aligned.columns = ["A", "B"]
    n = len(aligned)
    if n < BOOTSTRAP_WINDOW_DAYS + 10:
        return {"error": "panel too short"}

    starts = rng.integers(0, n - BOOTSTRAP_WINDOW_DAYS, size=N_BOOTSTRAP)
    cost = ROUND_TRIP_BPS / 1e4
    n_pos = 0
    n_with_events = 0
    means = []
    for s in starts:
        sub = aligned.iloc[s:s + BOOTSTRAP_WINDOW_DAYS]
        spread = sub["A"] - sub["B"]
        sigma_s = float(spread.std(ddof=1))
        if sigma_s == 0.0:
            continue
        threshold = k * sigma_s
        mask = spread.abs() > threshold
        nA = sub["A"].shift(-HOLDING_DAYS)
        nB = sub["B"].shift(-HOLDING_DAYS)
        revert = -np.sign(spread) * (nA - nB)
        pnl = revert[mask].dropna().astype(float).values - cost
        if len(pnl) < 3:
            continue
        n_with_events += 1
        m = float(np.mean(pnl))
        means.append(m)
        if m > 0:
            n_pos += 1

    if n_with_events == 0:
        return {"error": "no windows produced events"}

    return {
        "n_windows_with_events": n_with_events,
        "n_windows_pos_post": n_pos,
        "stability_post": n_pos / n_with_events,
        "median_window_mean_bps": float(np.median(means)) * 1e4 if means else 0.0,
    }


def _verdict(combo: dict) -> str:
    """Apply the locked verdict bar."""
    n = combo.get("n_events", 0)
    if n < 10:
        return "INSUFFICIENT_N"
    if combo.get("mean_pnl_post_bps", 0) <= 0:
        return "FAIL_POSTCOST"
    if combo.get("t_stat_post", 0) < T_STAT_BAR:
        return "FAIL_TSTAT"
    if not combo.get("bh_fdr_pass", False):
        return "FAIL_BH_FDR"
    if combo.get("bootstrap_stability_post", 0) < STABILITY_FRAC_BAR:
        return "FAIL_STABILITY"
    return "PASS"


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    today = date.today().isoformat()

    log.info("loading canonical sector panel...")
    from pipeline.research.sector_panel import load_canonical_panel, load_canonical_metadata
    panel = load_canonical_panel()
    panel_meta = load_canonical_metadata()
    log.info("panel loaded: %s", panel.shape)

    log.info("Phase 1 — per-pair event tabulation × %d thresholds", len(THRESHOLDS_K))
    per_pair: list[dict] = []
    for a, b in PAIRS:
        if a not in panel.columns or b not in panel.columns:
            log.warning("missing sector(s) for pair %s × %s, skipping", a, b)
            continue
        per_pair.append(_enumerate_events(panel, a, b, THRESHOLDS_K))

    summary_rows: list[dict] = []
    for pp in per_pair:
        if "error" in pp:
            log.warning("pair %s: %s", pp.get("pair"), pp["error"])
            continue
        for k, r in pp["by_k"].items():
            if r.get("n_events", 0) == 0:
                continue
            summary_rows.append({
                "pair": pp["pair"],
                "k": k,
                "sigma_s_pct": pp["sigma_s"] * 100,
                "n_events": r["n_events"],
                "threshold_pct": r["threshold_pct"],
                "mean_pnl_pre_bps": r["mean_pnl_pre_bps"],
                "mean_pnl_post_bps": r["mean_pnl_post_bps"],
                "median_pnl_post_bps": r["median_pnl_post_bps"],
                "win_rate_pre": r["win_rate_pre"],
                "win_rate_post": r["win_rate_post"],
                "t_stat_post": r["t_stat_post"],
                "p_value_post": r["p_value_post"],
            })
    summary = pd.DataFrame(summary_rows)

    log.info("Phase 2 — BH-FDR @ alpha=%.2f across %d combos", BH_FDR_ALPHA, len(summary))
    if not summary.empty:
        pvs = summary["p_value_post"].tolist()
        survive = _bh_fdr(pvs, BH_FDR_ALPHA)
        summary["bh_fdr_pass"] = survive
    else:
        summary["bh_fdr_pass"] = []

    log.info("Phase 3 — bootstrap stability per (pair, k)")
    boot_rows: list[dict] = []
    for _, row in summary.iterrows():
        a, b = row["pair"].split("__")
        boot = _bootstrap_pair_k(panel, a, b, row["k"])
        boot["pair"] = row["pair"]
        boot["k"] = row["k"]
        boot_rows.append(boot)
    boot_df = pd.DataFrame(boot_rows)

    if not boot_df.empty and "stability_post" in boot_df.columns:
        summary = summary.merge(
            boot_df[["pair", "k", "stability_post", "median_window_mean_bps"]]
            .rename(columns={"stability_post": "bootstrap_stability_post"}),
            on=["pair", "k"], how="left",
        )
    else:
        summary["bootstrap_stability_post"] = float("nan")
        summary["median_window_mean_bps"] = float("nan")

    summary["verdict"] = summary.apply(lambda r: _verdict(r.to_dict()), axis=1)
    summary = summary.sort_values(["verdict", "mean_pnl_post_bps"],
                                    ascending=[True, False])

    summary_path = OUT_DIR / f"summary_{today}.csv"
    summary.to_csv(summary_path, index=False)
    log.info("wrote %s", summary_path)

    boot_path = OUT_DIR / f"bootstrap_{today}.csv"
    boot_df.to_csv(boot_path, index=False)

    per_pair_rows: list[dict] = []
    for pp in per_pair:
        if "error" in pp:
            continue
        for k, r in pp["by_k"].items():
            if r.get("n_events", 0) == 0:
                continue
            for d, pre, post in zip(r["events_dates"],
                                      r["pnl_pre_series"],
                                      r["pnl_post_series"]):
                per_pair_rows.append({
                    "pair": pp["pair"], "k": k, "event_date": d,
                    "pnl_pre_bps": pre * 1e4, "pnl_post_bps": post * 1e4,
                })
    per_pair_df = pd.DataFrame(per_pair_rows)
    per_pair_df.to_csv(OUT_DIR / f"events_{today}.csv", index=False)

    _write_findings(summary, panel_meta, today)
    return 0


def _fmt_bps(v: float) -> str:
    return f"{v:+.1f} bps" if pd.notna(v) else "—"


def _fmt_pct(v: float) -> str:
    return f"{v*100:.0f}%" if pd.notna(v) else "—"


def _write_findings(summary: pd.DataFrame, panel_meta: dict, today: str) -> None:
    lines = [
        f"# Sector pair divergence-reversion — findings {today}",
        "",
        "_Discovery-only. No edge claim, no hypothesis-registry entry. See "
        "`docs/research/sector_pair_divergence/2026-04-30-design.md`._",
        "",
        "## Hypothesis under test",
        "",
        "When a normally-tight pair (top-10 5y stable pairs) diverges by "
        ">k·σ on day d, contrarian pair trade (long laggard, short leader, "
        "1-day hold) earns positive post-cost return.",
        "",
        "## Setup",
        f"- Canonical panel: shape {panel_meta.get('extras', {}).get('shape', '?')}, "
        f"git `{panel_meta.get('git_sha', '?')}`",
        f"- Pairs tested: {len(PAIRS)}",
        f"- Threshold grid: k ∈ {THRESHOLDS_K}",
        f"- Round-trip cost: {ROUND_TRIP_BPS:.0f} bps",
        f"- Bootstrap: {N_BOOTSTRAP} × {BOOTSTRAP_WINDOW_DAYS}-day windows",
        f"- BH-FDR @ {BH_FDR_ALPHA:.0%}, t-stat bar {T_STAT_BAR}, "
        f"stability bar {STABILITY_FRAC_BAR:.0%}",
        "",
    ]

    if summary.empty:
        lines.append("**No events generated. Study aborted.**")
        (OUT_DIR / f"findings_{today}.md").write_text("\n".join(lines), encoding="utf-8")
        return

    passes = summary[summary["verdict"] == "PASS"]

    lines += ["## Verdict counts", ""]
    vc = summary["verdict"].value_counts()
    for v, n in vc.items():
        lines.append(f"- {v}: {n}")
    lines.append("")

    if not passes.empty:
        lines += [
            "## PASSING (post-cost, t>2, BH-FDR survive, ≥60% boot-stable)",
            "",
            "| Pair | k | n | mean post | median post | win % | t | boot stab |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for _, r in passes.iterrows():
            lines.append(
                f"| {r['pair'].replace('__', ' × ')} | {r['k']:.1f} "
                f"| {int(r['n_events'])} "
                f"| {_fmt_bps(r['mean_pnl_post_bps'])} "
                f"| {_fmt_bps(r['median_pnl_post_bps'])} "
                f"| {_fmt_pct(r['win_rate_post'])} "
                f"| {r['t_stat_post']:+.2f} "
                f"| {_fmt_pct(r['bootstrap_stability_post'])} |"
            )
        lines.append("")
    else:
        lines += [
            "## PASSING combos: NONE",
            "",
            "No (pair, k) combination cleared the locked verdict bar.",
            "",
        ]

    lines += [
        "## All combos (sorted by post-cost mean P&L)",
        "",
        "| Pair | k | n | mean pre | mean post | win % post | t post | p | BH | boot stab | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    sorted_all = summary.sort_values("mean_pnl_post_bps", ascending=False)
    for _, r in sorted_all.iterrows():
        lines.append(
            f"| {r['pair'].replace('__', ' × ')} | {r['k']:.1f} "
            f"| {int(r['n_events'])} "
            f"| {_fmt_bps(r['mean_pnl_pre_bps'])} "
            f"| {_fmt_bps(r['mean_pnl_post_bps'])} "
            f"| {_fmt_pct(r['win_rate_post'])} "
            f"| {r['t_stat_post']:+.2f} "
            f"| {r['p_value_post']:.3f} "
            f"| {'✓' if bool(r['bh_fdr_pass']) else '·'} "
            f"| {_fmt_pct(r['bootstrap_stability_post'])} "
            f"| **{r['verdict']}** |"
        )
    lines.append("")

    lines += [
        "## What this study does NOT certify",
        "- This is daily close-to-close reversion. The user's intuition was "
        "intraday divergence; the daily test is a low-frequency proxy.",
        "- A PASS here does NOT authorise live trading. Next step is a "
        "single-touch holdout under backtesting-specs.txt §10.4.",
        "- A FAIL here only disproves daily-frequency reversion. Intraday "
        "(open → 11:00 IST → close) divergence-reversion is a separate study "
        "that needs minute-bar sector indices we do not currently store.",
    ]

    (OUT_DIR / f"findings_{today}.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote findings %s", OUT_DIR / f"findings_{today}.md")


if __name__ == "__main__":
    sys.exit(main())
