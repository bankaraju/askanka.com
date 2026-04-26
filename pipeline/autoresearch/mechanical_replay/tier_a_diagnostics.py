"""Tier A negative-control / sanity-diagnostic backtests for H-2026-04-26-001.

Spec: docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md
Backtest standards: docs/superpowers/specs/backtesting-specs.txt §15.1 verdict
ladder, §7 beats baselines, §8 direction integrity.

Three diagnostics over the in-sample mechanical-replay output (default
``trades_no_zcross.csv``) on the |z| >= sigma_threshold slice:

* **Tier A.1 — Trend-follow opposite (direction integrity).**
  Re-evaluate every observed trade with the side flipped (LONG <-> SHORT).
  ``pnl_pct`` sign is reversed. If the rule is genuine mean-reversion the
  flipped book must lose money; §8 direction integrity gate wants
  ``mean_pnl < 0`` and ``|mean_pnl| >= 0.3%`` (lose >=0.3%/trade on average).

* **Tier A.2 — Random direction (coin flip).**
  For each observed trade, randomly take LONG or SHORT (50/50). Compute
  the realised hit rate. Repeat ``n_perms_random_dir`` times. Report the
  full distribution and the empirical p-value
  ``P(random_hit_rate >= observed_hit_rate)``. Vectorised; seeded RNG.

* **Tier A.3 — Per-week stationarity.**
  Bucket the 60-day window into ISO calendar weeks. For each week report
  ``n``, hit rate, mean P&L, sum P&L, and the share of total P&L. Pass
  criteria: at least 4 weeks individually positive AND no single week
  carries >50% of total P&L.

CLI::

    python -m pipeline.autoresearch.mechanical_replay.tier_a_diagnostics \\
        --in-sample-csv pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv \\
        --out-dir pipeline/data/research/h_2026_04_26_001/tier_a_diagnostics/ \\
        --sigma-threshold 2.0 \\
        --n-perms-random-dir 10000
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_IN_SAMPLE_CSV = Path(
    "pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv"
)
DEFAULT_OUT_DIR = Path(
    "pipeline/data/research/h_2026_04_26_001/tier_a_diagnostics/"
)
DEFAULT_SIGMA_THRESHOLD = 2.0
DEFAULT_N_PERMS_RANDOM_DIR = 10_000
DEFAULT_SEED = 20260426

# §8 direction-integrity thresholds
DIRECTION_INTEGRITY_MEAN_PNL_THRESHOLD_PCT = 0.3  # absolute pct

# Per-week stationarity gate
PER_WEEK_MIN_POSITIVE_WEEKS = 4
PER_WEEK_MAX_SINGLE_WEEK_SHARE = 0.5  # fraction of total P&L

HYPOTHESIS_ID = "H-2026-04-26-001"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_trades(csv_path: Path | str) -> pd.DataFrame:
    """Load and lightly validate the in-sample replay trade CSV."""
    df = pd.read_csv(csv_path)
    required = {"ticker", "date", "side", "pnl_pct", "abs_z"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns in {csv_path}: {missing}")
    df = df.dropna(subset=["pnl_pct", "abs_z", "side", "date"]).copy()
    df["pnl_pct"] = df["pnl_pct"].astype(float)
    df["abs_z"] = df["abs_z"].astype(float)
    df["side"] = df["side"].astype(str).str.upper()
    df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date_parsed"].isna().any():
        bad = df.loc[df["date_parsed"].isna(), "date"].unique().tolist()
        raise ValueError(f"unparseable dates in {csv_path}: {bad[:5]}")
    df["hit"] = (df["pnl_pct"] > 0).astype(np.int8)
    return df


def filter_sigma_slice(
    df: pd.DataFrame, sigma_threshold: float
) -> pd.DataFrame:
    sub = df[df["abs_z"] >= sigma_threshold].copy()
    if sub.empty:
        raise ValueError(
            f"no trades with abs_z >= {sigma_threshold} in input"
        )
    return sub.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tier A.1 — Trend-follow opposite
# ---------------------------------------------------------------------------

def trend_follow_opposite(sigma_trades: pd.DataFrame) -> dict[str, Any]:
    """Flip every side and reverse the realised pnl sign.

    With pnl_pct = (move while LONG), flipping the side means we instead
    held the opposite leg, whose realised pnl is exactly ``-pnl_pct``.

    Returns observed stats, flipped stats, and the §8 direction-integrity
    verdict (PASS / FAIL with a one-line ``flag_message`` when the kill
    condition is hit).
    """
    n = int(len(sigma_trades))
    obs_pnl = sigma_trades["pnl_pct"].to_numpy(dtype=float)
    obs_hit = (obs_pnl > 0).astype(int)
    flipped_pnl = -obs_pnl
    flipped_hit = (flipped_pnl > 0).astype(int)

    obs_mean = float(obs_pnl.mean())
    obs_sum = float(obs_pnl.sum())
    obs_hit_rate = float(obs_hit.mean())

    flipped_mean = float(flipped_pnl.mean())
    flipped_sum = float(flipped_pnl.sum())
    flipped_hit_rate = float(flipped_hit.mean())

    # §8 direction-integrity gate
    threshold = DIRECTION_INTEGRITY_MEAN_PNL_THRESHOLD_PCT
    direction_integrity_pass = (
        flipped_mean < 0.0 and abs(flipped_mean) >= threshold
    )
    flag_message = None
    if not direction_integrity_pass:
        if flipped_mean >= 0.0:
            flag_message = (
                f"KILL: trend-follow opposite mean P&L = {flipped_mean:+.4f}% "
                f">= 0; direction is NOT mean-reversion."
            )
        else:
            flag_message = (
                f"KILL: trend-follow opposite mean P&L = {flipped_mean:+.4f}% "
                f"< 0 but |mean| = {abs(flipped_mean):.4f}% < threshold "
                f"{threshold:.2f}%; direction edge too small to be confident."
            )

    return {
        "n_trades": n,
        "observed": {
            "hit_rate_pct": round(obs_hit_rate * 100.0, 4),
            "hits": int(obs_hit.sum()),
            "mean_pnl_pct": round(obs_mean, 6),
            "sum_pnl_pct": round(obs_sum, 6),
        },
        "flipped": {
            "hit_rate_pct": round(flipped_hit_rate * 100.0, 4),
            "hits": int(flipped_hit.sum()),
            "mean_pnl_pct": round(flipped_mean, 6),
            "sum_pnl_pct": round(flipped_sum, 6),
        },
        "direction_integrity_threshold_pct": threshold,
        "direction_integrity_pass": bool(direction_integrity_pass),
        "flag_message": flag_message,
    }


# ---------------------------------------------------------------------------
# Tier A.2 — Random direction (coin flip)
# ---------------------------------------------------------------------------

def random_direction_perm(
    sigma_trades: pd.DataFrame,
    n_perms: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Random LONG/SHORT per trade; report distribution and empirical p-value.

    For each permutation we draw a Bernoulli(0.5) per trade. If the draw
    matches the original side we keep ``pnl_pct``; otherwise we negate
    it. The hit count is then ``sum(realised_pnl > 0)``.

    Empirical p-value is ``P(random_hit_rate >= observed_hit_rate)``.
    """
    obs_pnl = sigma_trades["pnl_pct"].to_numpy(dtype=float)
    n_trades = obs_pnl.shape[0]
    if n_trades == 0:
        raise ValueError("cannot run random-direction perm with 0 trades")

    obs_hit_rate = float((obs_pnl > 0).mean())

    # Vectorised: draw (n_perms, n_trades) Bernoulli(0.5).
    # 1 = keep original side; -1 = flip.
    # Use chunking to bound memory at large n_perms.
    perm_hit_rates = np.empty(n_perms, dtype=np.float64)
    chunk = 10_000
    for start in range(0, n_perms, chunk):
        end = min(start + chunk, n_perms)
        size = end - start
        flips = rng.integers(0, 2, size=(size, n_trades), dtype=np.int8)
        # signs: +1 if flips==1 else -1 (i.e. 2*flips-1)
        signs = (flips * 2 - 1).astype(np.int8)
        realised = signs.astype(np.float64) * obs_pnl[np.newaxis, :]
        perm_hit_rates[start:end] = (realised > 0).sum(axis=1) / n_trades

    p_value = float(
        np.mean(perm_hit_rates >= obs_hit_rate - 1e-12)
    )

    return {
        "n_trades": int(n_trades),
        "n_perms": int(n_perms),
        "observed_hit_rate_pct": round(obs_hit_rate * 100.0, 4),
        "random_hit_rate_distribution_pct": {
            "min": round(float(np.min(perm_hit_rates) * 100), 4),
            "p01": round(float(np.percentile(perm_hit_rates, 1) * 100), 4),
            "p05": round(float(np.percentile(perm_hit_rates, 5) * 100), 4),
            "p50": round(float(np.percentile(perm_hit_rates, 50) * 100), 4),
            "mean": round(float(np.mean(perm_hit_rates) * 100), 4),
            "p95": round(float(np.percentile(perm_hit_rates, 95) * 100), 4),
            "p99": round(float(np.percentile(perm_hit_rates, 99) * 100), 4),
            "max": round(float(np.max(perm_hit_rates) * 100), 4),
        },
        "p_value_random_beats_observed": p_value,
        "direction_alpha_pass": bool(p_value < 0.01),
    }


# ---------------------------------------------------------------------------
# Tier A.3 — Per-week stationarity
# ---------------------------------------------------------------------------

def per_week_stationarity(
    sigma_trades: pd.DataFrame,
) -> dict[str, Any]:
    """Bucket sigma trades by ISO calendar week, return per-week stats."""
    df = sigma_trades.copy()
    iso = df["date_parsed"].dt.isocalendar()
    # Compose a "YYYY-Www" bucket label using ISO year + ISO week.
    df["week_label"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    # week start date (Monday) for ordering
    df["week_start"] = df["date_parsed"] - pd.to_timedelta(
        df["date_parsed"].dt.weekday, unit="d"
    )
    df["week_start"] = df["week_start"].dt.normalize()

    total_pnl = float(df["pnl_pct"].sum())

    rows: list[dict[str, Any]] = []
    for (label, wstart), sub in df.groupby(["week_label", "week_start"], sort=True):
        n = int(len(sub))
        hits = int((sub["pnl_pct"] > 0).sum())
        mean_pnl = float(sub["pnl_pct"].mean())
        sum_pnl = float(sub["pnl_pct"].sum())
        share = sum_pnl / total_pnl if total_pnl != 0.0 else 0.0
        rows.append({
            "week_label": label,
            "week_start": wstart.strftime("%Y-%m-%d"),
            "n_trades": n,
            "hits": hits,
            "hit_rate_pct": round(100.0 * hits / n, 4) if n else 0.0,
            "mean_pnl_pct": round(mean_pnl, 6),
            "sum_pnl_pct": round(sum_pnl, 6),
            "share_of_total_pnl": round(share, 6),
        })

    rows.sort(key=lambda r: r["week_start"])

    n_weeks = len(rows)
    n_positive_weeks = sum(1 for r in rows if r["mean_pnl_pct"] > 0.0)
    max_share = max((abs(r["share_of_total_pnl"]) for r in rows), default=0.0)

    pass_min_positive = n_positive_weeks >= PER_WEEK_MIN_POSITIVE_WEEKS
    pass_no_dominant_week = max_share <= PER_WEEK_MAX_SINGLE_WEEK_SHARE
    overall_pass = bool(pass_min_positive and pass_no_dominant_week)

    return {
        "n_weeks": int(n_weeks),
        "min_positive_weeks_required": PER_WEEK_MIN_POSITIVE_WEEKS,
        "max_single_week_share_allowed": PER_WEEK_MAX_SINGLE_WEEK_SHARE,
        "n_positive_weeks": int(n_positive_weeks),
        "max_single_week_share": round(float(max_share), 6),
        "stationarity_pass": overall_pass,
        "per_week": rows,
        "total_pnl_pct": round(total_pnl, 6),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_tier_a(
    in_sample_csv: Path | str = DEFAULT_IN_SAMPLE_CSV,
    sigma_threshold: float = DEFAULT_SIGMA_THRESHOLD,
    n_perms_random_dir: int = DEFAULT_N_PERMS_RANDOM_DIR,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    in_sample_csv = Path(in_sample_csv)
    df = load_trades(in_sample_csv)
    sigma_trades = filter_sigma_slice(df, sigma_threshold)

    rng = np.random.default_rng(seed)

    a1 = trend_follow_opposite(sigma_trades)
    a2 = random_direction_perm(sigma_trades, n_perms_random_dir, rng)
    a3 = per_week_stationarity(sigma_trades)

    elapsed = time.perf_counter() - t0

    overall_pass = bool(
        a1["direction_integrity_pass"]
        and a2["direction_alpha_pass"]
        and a3["stationarity_pass"]
    )

    return {
        "hypothesis_id": HYPOTHESIS_ID,
        "in_sample_csv": str(in_sample_csv).replace("\\", "/"),
        "sigma_threshold": float(sigma_threshold),
        "n_observed_trades": int(len(sigma_trades)),
        "candidate_pool_size": int(len(df)),
        "seed": int(seed),
        "tier_a1_trend_follow_opposite": a1,
        "tier_a2_random_direction": a2,
        "tier_a3_per_week_stationarity": a3,
        "overall_tier_a_pass": overall_pass,
        "compute_time_seconds": round(elapsed, 4),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:+.4f}%"


def render_report(summary: dict[str, Any]) -> str:
    a1 = summary["tier_a1_trend_follow_opposite"]
    a2 = summary["tier_a2_random_direction"]
    a3 = summary["tier_a3_per_week_stationarity"]

    a1_status = "PASS" if a1["direction_integrity_pass"] else "FAIL"
    a2_status = "PASS" if a2["direction_alpha_pass"] else "FAIL"
    a3_status = "PASS" if a3["stationarity_pass"] else "FAIL"
    overall = "PASS" if summary["overall_tier_a_pass"] else "FAIL"

    flag_block = ""
    if a1.get("flag_message"):
        flag_block = (
            "\n> **!! KILL FLAG !!** "
            + a1["flag_message"]
            + "\n"
        )

    week_lines = ["| Week | Start | n | Hits | Hit % | Mean P&L | Sum P&L | Share |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in a3["per_week"]:
        week_lines.append(
            f"| {r['week_label']} | {r['week_start']} | {r['n_trades']} | "
            f"{r['hits']} | {r['hit_rate_pct']:.2f}% | "
            f"{_fmt_pct(r['mean_pnl_pct'])} | {_fmt_pct(r['sum_pnl_pct'])} | "
            f"{r['share_of_total_pnl'] * 100:+.2f}% |"
        )
    week_table = "\n".join(week_lines)

    obs_hit_rate = a1["observed"]["hit_rate_pct"]
    obs_mean = a1["observed"]["mean_pnl_pct"]
    obs_sum = a1["observed"]["sum_pnl_pct"]
    flipped_hit_rate = a1["flipped"]["hit_rate_pct"]
    flipped_mean = a1["flipped"]["mean_pnl_pct"]
    flipped_sum = a1["flipped"]["sum_pnl_pct"]

    rd = a2["random_hit_rate_distribution_pct"]

    md = f"""# Tier A negative-control diagnostics — {summary['hypothesis_id']}

- **Generated:** {summary['generated_at']}
- **Input:** `{summary['in_sample_csv']}`
- **Sigma threshold:** {summary['sigma_threshold']}
- **Observed trades (sigma slice):** {summary['n_observed_trades']} of {summary['candidate_pool_size']} candidate-pool rows
- **Seed:** {summary['seed']}
- **Compute time:** {summary['compute_time_seconds']:.3f}s

**Overall Tier A verdict: {overall}**
{flag_block}
---

## Tier A.1 — Trend-follow opposite (direction integrity) — {a1_status}

Spec gate: §8 direction integrity. The flipped book must lose money,
with `|mean P&L| >= {a1['direction_integrity_threshold_pct']:.2f}%` per
trade. If trend-follow opposite is positive or break-even, our edge isn't
mean-reversion — KILL.

| Side | n | Hit rate | Mean P&L | Sum P&L |
|---|---:|---:|---:|---:|
| Observed (FADE) | {a1['n_trades']} | {obs_hit_rate:.4f}% | {_fmt_pct(obs_mean)} | {_fmt_pct(obs_sum)} |
| Flipped (TREND-FOLLOW) | {a1['n_trades']} | {flipped_hit_rate:.4f}% | {_fmt_pct(flipped_mean)} | {_fmt_pct(flipped_sum)} |

- Direction-integrity threshold: |mean P&L| >= {a1['direction_integrity_threshold_pct']:.2f}% AND mean P&L < 0
- Flipped mean P&L: {_fmt_pct(flipped_mean)}
- Verdict: **{a1_status}**

---

## Tier A.2 — Random direction (coin flip) — {a2_status}

For each of the {a2['n_trades']} trades draw LONG/SHORT 50/50 and recompute
hit rate. {a2['n_perms']:,} permutations, seeded.

- **Observed hit rate:** {a2['observed_hit_rate_pct']:.4f}%
- **Random-direction distribution (hit %):**
  - min: {rd['min']:.2f}, p01: {rd['p01']:.2f}, p05: {rd['p05']:.2f}, p50: {rd['p50']:.2f}, mean: {rd['mean']:.2f}, p95: {rd['p95']:.2f}, p99: {rd['p99']:.2f}, max: {rd['max']:.2f}
- **p-value (P(random >= observed)):** {a2['p_value_random_beats_observed']:.6f}
- Direction-alpha threshold: p < 0.01
- Verdict: **{a2_status}**

---

## Tier A.3 — Per-week stationarity — {a3_status}

ISO-week stratification within the in-sample window. Pass requires
>= {a3['min_positive_weeks_required']} positive weeks AND no single week
carrying > {a3['max_single_week_share_allowed'] * 100:.0f}% of total P&L.

- **n weeks:** {a3['n_weeks']}
- **n weeks with positive mean P&L:** {a3['n_positive_weeks']}
- **Max single-week P&L share:** {a3['max_single_week_share'] * 100:+.2f}%
- **Total sigma-slice P&L:** {_fmt_pct(a3['total_pnl_pct'])}
- Verdict: **{a3_status}**

{week_table}

---

## Bottom-line verdict

"""

    bottom = _bottom_line(summary)
    md += bottom + "\n"
    return md


def _bottom_line(summary: dict[str, Any]) -> str:
    a1 = summary["tier_a1_trend_follow_opposite"]
    a2 = summary["tier_a2_random_direction"]
    a3 = summary["tier_a3_per_week_stationarity"]

    parts: list[str] = []
    if summary["overall_tier_a_pass"]:
        parts.append(
            "Tier A diagnostics PASS overall: trend-follow opposite loses "
            f"{a1['flipped']['mean_pnl_pct']:+.4f}% per trade (kills the "
            "trend-follow alternative), random-direction p-value is "
            f"{a2['p_value_random_beats_observed']:.4f} (direction choice IS "
            f"the alpha), and {a3['n_positive_weeks']} of {a3['n_weeks']} "
            "weeks individually contribute positive mean P&L with no single "
            f"week dominating (max share {a3['max_single_week_share'] * 100:+.2f}%). "
            "Edge is at least temporally consistent within the 60-day window."
        )
    else:
        failed = []
        if not a1["direction_integrity_pass"]:
            failed.append(
                f"A.1 direction-integrity FAIL (flipped mean "
                f"{a1['flipped']['mean_pnl_pct']:+.4f}%)"
            )
        if not a2["direction_alpha_pass"]:
            failed.append(
                f"A.2 random-direction FAIL (p={a2['p_value_random_beats_observed']:.4f})"
            )
        if not a3["stationarity_pass"]:
            failed.append(
                f"A.3 per-week stationarity FAIL "
                f"({a3['n_positive_weeks']} positive weeks, "
                f"max share {a3['max_single_week_share'] * 100:+.2f}%)"
            )
        parts.append(
            "Tier A diagnostics FAIL overall: " + "; ".join(failed) + "."
        )
        if a1.get("flag_message"):
            parts.append("KILL: " + a1["flag_message"])
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Tier A negative-control diagnostics for H-2026-04-26-001 "
            "(in-sample mechanical replay)."
        )
    )
    parser.add_argument(
        "--in-sample-csv",
        type=Path,
        default=DEFAULT_IN_SAMPLE_CSV,
        help="In-sample candidate trades CSV (default: %(default)s)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--sigma-threshold",
        type=float,
        default=DEFAULT_SIGMA_THRESHOLD,
        help="abs_z threshold for the observed slice (default: %(default)s)",
    )
    parser.add_argument(
        "--n-perms-random-dir",
        type=int,
        default=DEFAULT_N_PERMS_RANDOM_DIR,
        help="Random-direction permutation count (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="RNG seed (default: %(default)s)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_tier_a(
        in_sample_csv=args.in_sample_csv,
        sigma_threshold=args.sigma_threshold,
        n_perms_random_dir=args.n_perms_random_dir,
        seed=args.seed,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "tier_a_results.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_md = render_report(summary)
    md_path = args.out_dir / "2026-04-26-tier-a-report.md"
    md_path.write_text(report_md, encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
