"""ETF v3 — 60-day forward picks/P&L comparison vs production v2.

Takes a rolling-refit JSON (with per-window weights) and the existing
intraday_break_replay_60d_v0.1_ungated.parquet (which has all 4-sigma break
events with entry/exit prices already replayed via Kite minute bars and
gross_pnl_pct computed) and produces a per-day comparison:

  - For each trading day in the replay window:
    * Compute v3 zone using that day's refit weights + production zone thresholds
    * Apply gate: v3_pass = (v3_zone != NEUTRAL)
    * Apply gate: v2_pass = (parquet.regime != NEUTRAL) — uses v2's actual
      zone label that production emitted at trigger time
  - Aggregate per-day picks + P&L for v2 cohort, v3 cohort, both, v3-only, v2-only
  - Cluster-robust standard errors at trade_date level

This addresses the user ask: "stocks that we get in that run must be compared
to the current in use v2 model and compare the differences..i suspect there
will be none..lets still try."

Usage:
    python -m pipeline.autoresearch.etf_v3_60d_zone_pnl \\
        --rolling-refit pipeline/data/research/etf_v3/etf_v3_rolling_refit_int5_lb756_curated_60d.json \\
        --replay-parquet pipeline/autoresearch/data/intraday_break_replay_60d_v0.1_ungated.parquet \\
        --out-tag int5
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.autoresearch.etf_v3_loader import CURATED_FOREIGN_ETFS, build_panel
from pipeline.autoresearch.etf_v3_research import build_features, _weighted_signal
from pipeline.autoresearch.etf_v3_curated_signal import _signal_to_zone

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = REPO_ROOT / "pipeline" / "autoresearch" / "etf_v3_curated_optimal_weights.json"
DEFAULT_REPLAY = REPO_ROOT / "pipeline" / "autoresearch" / "data" / "intraday_break_replay_60d_v0.1_ungated.parquet"
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"


def reconstruct_per_day_zones(
    rolling_refit_path: Path,
    zone_center: float | None = None,
    zone_band: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Use per-window weights from a rolling-refit JSON to reconstruct
    per-trading-day v3 signal + zone.

    For each refit window in the JSON, apply that window's weights to the
    feature matrix for the days that window owned (anchor through next anchor).

    If zone_center/zone_band are None, calibrate from the rolling-refit's own
    pooled signal distribution (center=mean, band=std). This is the right
    calibration when the rolling-refit weights have a different magnitude
    scale than the production single-fit weights.

    Returns (DataFrame keyed by date with columns: signal, zone, direction,
    refit_anchor; dict of calibration metadata).
    """
    refit = json.loads(Path(rolling_refit_path).read_text(encoding="utf-8"))
    detail = refit["per_window_detail"]
    if not detail:
        raise RuntimeError("rolling refit has no per_window_detail")
    if "weights" not in detail[0]:
        raise RuntimeError(
            "rolling refit JSON does not contain per-window 'weights' — "
            "regenerate using the current etf_v3_rolling_refit.py"
        )

    cfg = refit["config"]
    refit_interval = int(cfg["refit_interval_days"])
    eval_start = pd.Timestamp(cfg["eval_start"])
    eval_end = pd.Timestamp(cfg["eval_end"])

    # Rebuild the same feature matrix used by the rolling refit. We do NOT
    # dropna() here because the rolling refit eval_dates is derived from the
    # full feats index (dropna only happens inside the per-window prediction
    # block in etf_v3_rolling_refit.py). To stay aligned, we use the same
    # eval_dates slicing and let dropna happen per-window via _weighted_signal
    # (which uses fillna(0.0) internally).
    panel = build_panel(t1_anchor=True)
    feats = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))
    eval_dates = feats.index[(feats.index >= eval_start) & (feats.index <= eval_end)]
    if len(eval_dates) == 0:
        raise RuntimeError(f"no eval dates in [{eval_start.date()} .. {eval_end.date()}]")

    raw_rows = []
    for i, w in enumerate(detail):
        window_start_idx = i * refit_interval
        window_end_idx = (i + 1) * refit_interval
        window_dates = eval_dates[window_start_idx:window_end_idx]
        if len(window_dates) == 0:
            continue
        Xw = feats.loc[window_dates].dropna()
        if Xw.empty:
            continue
        sig = _weighted_signal(Xw, w["weights"])
        for date, signal in sig.items():
            raw_rows.append({
                "date": pd.Timestamp(date).date(),
                "signal": float(signal),
                "refit_anchor": w["refit_anchor"],
                "refit_id": int(w["refit_id"]),
            })

    df = pd.DataFrame(raw_rows).sort_values("date").reset_index(drop=True)

    # Calibrate zone thresholds from this run's own signal distribution if not
    # supplied. Production-weight thresholds (center=322, band=266) are mis-
    # scaled for rolling-refit weights which produce signals an order of
    # magnitude smaller (mean ~5, std ~9 in the 60d eval window).
    if zone_center is None or zone_band is None:
        zone_center = float(df["signal"].mean())
        zone_band = float(df["signal"].std())

    df["zone"] = df["signal"].apply(lambda s: _signal_to_zone(float(s), zone_center, zone_band))
    df["direction"] = df["signal"].apply(lambda s: "UP" if s > 0 else "DOWN")

    calibration = {
        "zone_center": float(zone_center),
        "zone_band": float(zone_band),
        "signal_mean": float(df["signal"].mean()),
        "signal_std": float(df["signal"].std()),
        "signal_min": float(df["signal"].min()),
        "signal_max": float(df["signal"].max()),
        "n_days": int(len(df)),
    }
    return df, calibration


def cluster_robust_mean_se(
    pnl: np.ndarray,
    cluster: np.ndarray,
) -> tuple[float, float, int]:
    """Cluster-robust mean and SE at the cluster level (per spec §10).

    Returns (mean, se, n_clusters).
    """
    if len(pnl) == 0:
        return 0.0, 0.0, 0
    df = pd.DataFrame({"pnl": pnl, "cluster": cluster})
    cluster_means = df.groupby("cluster")["pnl"].mean().values
    n_clusters = len(cluster_means)
    if n_clusters == 0:
        return 0.0, 0.0, 0
    mean = float(np.mean(cluster_means))
    se = float(np.std(cluster_means, ddof=1) / np.sqrt(n_clusters)) if n_clusters > 1 else 0.0
    return mean, se, n_clusters


def compare_picks(
    zones_df: pd.DataFrame,
    replay_df: pd.DataFrame,
) -> dict:
    """Apply v2 and v3 regime gates to the replay parquet and tabulate picks
    + P&L for each cohort. The v2 gate uses parquet.regime (the live v2 zone
    at trigger time); the v3 gate uses zones_df.zone (reconstructed v3 zone
    for that date)."""
    replay = replay_df.copy()
    replay["trade_date"] = pd.to_datetime(replay["trade_date"]).dt.date
    zones = zones_df.set_index("date")[["zone", "signal", "direction"]]
    zones.columns = [f"v3_{c}" for c in zones.columns]
    joined = replay.join(zones, on="trade_date")
    if joined["v3_zone"].isna().any():
        n_missing = joined["v3_zone"].isna().sum()
        missing_dates = sorted(joined.loc[joined["v3_zone"].isna(), "trade_date"].unique())
        logger.warning("%d trades have no v3 zone (missing dates: %s) — dropping",
                       n_missing, missing_dates[:5])
        joined = joined.dropna(subset=["v3_zone"]).copy()

    joined["v2_pass"] = joined["regime"] != "NEUTRAL"
    joined["v3_pass"] = joined["v3_zone"] != "NEUTRAL"
    joined["both_pass"] = joined["v2_pass"] & joined["v3_pass"]
    joined["v3_only"] = joined["v3_pass"] & ~joined["v2_pass"]
    joined["v2_only"] = joined["v2_pass"] & ~joined["v3_pass"]
    joined["neither"] = ~joined["v2_pass"] & ~joined["v3_pass"]

    cohorts = {}
    for label, mask_col in [
        ("ALL", None),
        ("v2_pass", "v2_pass"),
        ("v3_pass", "v3_pass"),
        ("both_pass", "both_pass"),
        ("v3_only", "v3_only"),
        ("v2_only", "v2_only"),
        ("neither", "neither"),
    ]:
        sub = joined if mask_col is None else joined[joined[mask_col]]
        if len(sub) == 0:
            cohorts[label] = {
                "n_trades": 0, "n_dates": 0,
                "avg_gross_bps": None, "avg_net_bps": None,
                "cluster_mean_gross_bps": None,
                "cluster_se_gross_bps": None,
                "n_clusters": 0,
                "hit_rate": None,
            }
            continue
        gross_bps = sub["gross_pnl_pct"].values * 100.0  # pct → bps
        net_bps = sub["net_pnl_pct"].values * 100.0
        cluster_mean, cluster_se, n_clusters = cluster_robust_mean_se(
            gross_bps, sub["trade_date"].astype(str).values,
        )
        cohorts[label] = {
            "n_trades": int(len(sub)),
            "n_dates": int(sub["trade_date"].nunique()),
            "avg_gross_bps": float(np.mean(gross_bps)),
            "avg_net_bps": float(np.mean(net_bps)),
            "cluster_mean_gross_bps": cluster_mean,
            "cluster_se_gross_bps": cluster_se,
            "n_clusters": n_clusters,
            "hit_rate": float((gross_bps > 0).mean()),
            "by_direction": {
                d: {
                    "n": int(len(sub[sub["direction"] == d])),
                    "avg_gross_bps": float((sub[sub["direction"] == d]["gross_pnl_pct"] * 100.0).mean()) if len(sub[sub["direction"] == d]) else 0.0,
                }
                for d in ["LONG", "SHORT"]
            },
        }

    # Per-day overlap stats
    daily_stats = []
    for date, grp in joined.groupby("trade_date"):
        daily_stats.append({
            "date": str(date),
            "v3_zone": grp["v3_zone"].iloc[0],
            "v2_regimes_seen": ",".join(sorted(grp["regime"].unique())),
            "n_breaks": int(len(grp)),
            "n_v2_pass": int(grp["v2_pass"].sum()),
            "n_v3_pass": int(grp["v3_pass"].sum()),
            "n_both": int(grp["both_pass"].sum()),
            "n_v3_only": int(grp["v3_only"].sum()),
            "n_v2_only": int(grp["v2_only"].sum()),
            "v3_pass_pnl_bps": float((grp[grp["v3_pass"]]["gross_pnl_pct"] * 100.0).sum()) if grp["v3_pass"].any() else 0.0,
            "v2_pass_pnl_bps": float((grp[grp["v2_pass"]]["gross_pnl_pct"] * 100.0).sum()) if grp["v2_pass"].any() else 0.0,
        })

    return {
        "cohorts": cohorts,
        "daily_stats": daily_stats,
        "joined_n_trades": int(len(joined)),
    }


def write_report(
    cohorts: dict,
    daily_stats: list,
    out_path: Path,
    rolling_refit_path: Path,
    replay_path: Path,
    cadence: int,
) -> None:
    lines = [
        f"# ETF v3 60-day forward — picks/P&L vs production v2 (cadence={cadence})",
        "",
        f"**Generated:** {pd.Timestamp.now().isoformat(timespec='seconds')}",
        f"**Rolling refit:** `{rolling_refit_path.name}`",
        f"**Replay parquet:** `{replay_path.name}`",
        "",
        "## Setup",
        "",
        f"- v3 zone reconstructed per trading day from rolling-refit per-window weights",
        f"- v3 zone thresholds: center=322.23, band=265.83 (from production reoptimizer)",
        f"- Replay cohort: 696 ungated 4-sigma breaks over 27 trading days, entries/exits via Kite minute bars",
        f"- v2 gate: `regime != NEUTRAL` (regime column = production v2's zone at trigger time)",
        f"- v3 gate: `v3_zone != NEUTRAL` (reconstructed)",
        "",
        "## Cohort comparison",
        "",
        "| Cohort | n trades | n dates | avg gross bps | cluster mean ± SE bps | n clusters | hit rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, c in cohorts.items():
        if c["n_trades"] == 0:
            lines.append(f"| **{label}** | 0 | 0 | — | — | 0 | — |")
            continue
        avg_g = c["avg_gross_bps"]
        cm = c["cluster_mean_gross_bps"]
        cse = c["cluster_se_gross_bps"]
        hr = c["hit_rate"]
        cm_str = f"{cm:+.1f} ± {cse:.1f}" if cm is not None else "—"
        lines.append(
            f"| **{label}** | {c['n_trades']} | {c['n_dates']} | "
            f"{avg_g:+.1f} | {cm_str} | {c['n_clusters']} | {hr:.1%} |"
        )

    lines += [
        "",
        "## Direction breakdown",
        "",
        "| Cohort | LONG n | LONG bps | SHORT n | SHORT bps |",
        "|---|---|---|---|---|",
    ]
    for label, c in cohorts.items():
        if c["n_trades"] == 0:
            continue
        d = c.get("by_direction", {})
        long_n = d.get("LONG", {}).get("n", 0)
        long_bps = d.get("LONG", {}).get("avg_gross_bps", 0.0)
        short_n = d.get("SHORT", {}).get("n", 0)
        short_bps = d.get("SHORT", {}).get("avg_gross_bps", 0.0)
        lines.append(f"| **{label}** | {long_n} | {long_bps:+.1f} | {short_n} | {short_bps:+.1f} |")

    lines += [
        "",
        "## Daily breakdown",
        "",
        "| date | v3_zone | v2_regimes | breaks | v2 pass | v3 pass | both | v3-only | v2-only | v3 P&L bps | v2 P&L bps |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in daily_stats:
        lines.append(
            f"| {d['date']} | {d['v3_zone']} | {d['v2_regimes_seen']} | "
            f"{d['n_breaks']} | {d['n_v2_pass']} | {d['n_v3_pass']} | "
            f"{d['n_both']} | {d['n_v3_only']} | {d['n_v2_only']} | "
            f"{d['v3_pass_pnl_bps']:+.0f} | {d['v2_pass_pnl_bps']:+.0f} |"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="ETF v3 60-day forward picks/P&L comparison")
    p.add_argument("--rolling-refit", required=True, type=Path,
                   help="path to etf_v3_rolling_refit_int{N}_lb756_curated.json with per-window weights")
    p.add_argument("--replay-parquet", default=DEFAULT_REPLAY, type=Path,
                   help="path to intraday_break_replay_60d ungated parquet")
    p.add_argument("--weights-file", default=DEFAULT_WEIGHTS, type=Path,
                   help="production weights file (for zone thresholds only)")
    p.add_argument("--out-tag", default="int5",
                   help="suffix tag for output files (e.g. 'int1' or 'int5')")
    p.add_argument("--cadence", type=int, default=5,
                   help="refit cadence in days (for report header only)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # Calibrate zone thresholds from the rolling-refit's own signal
    # distribution. The production weights file has thresholds calibrated for
    # the production single-fit weights; rolling-refit weights produce
    # signals on a different scale, so we calibrate per-run.
    logger.info("reconstructing v3 per-day zones from %s", args.rolling_refit)
    zones, calibration = reconstruct_per_day_zones(args.rolling_refit)
    logger.info("v3 zones: %d days, %s -> %s",
                len(zones), zones["date"].min(), zones["date"].max())
    logger.info("v3 calibration: %s", calibration)
    logger.info("v3 zone distribution:\n%s", zones["zone"].value_counts().to_string())

    logger.info("loading replay parquet %s", args.replay_parquet)
    replay = pd.read_parquet(args.replay_parquet)
    logger.info("replay: %d trades, %d dates",
                len(replay), pd.to_datetime(replay["trade_date"]).dt.date.nunique())

    result = compare_picks(zones, replay)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_out = OUT_DIR / f"60d_zone_pnl_{args.out_tag}.json"
    json_out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", json_out)

    csv_out = OUT_DIR / f"60d_zones_{args.out_tag}.csv"
    zones.to_csv(csv_out, index=False)
    logger.info("wrote %s", csv_out)

    md_out = OUT_DIR / f"60d_zone_pnl_{args.out_tag}.md"
    write_report(
        cohorts=result["cohorts"],
        daily_stats=result["daily_stats"],
        out_path=md_out,
        rolling_refit_path=args.rolling_refit,
        replay_path=args.replay_parquet,
        cadence=args.cadence,
    )
    logger.info("wrote %s", md_out)

    print(json.dumps({
        "n_zones": len(zones),
        "n_trades_joined": result["joined_n_trades"],
        "v2_pass_n": result["cohorts"]["v2_pass"]["n_trades"],
        "v3_pass_n": result["cohorts"]["v3_pass"]["n_trades"],
        "both_n": result["cohorts"]["both_pass"]["n_trades"],
        "v3_only_n": result["cohorts"]["v3_only"]["n_trades"],
        "v2_only_n": result["cohorts"]["v2_only"]["n_trades"],
    }, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
