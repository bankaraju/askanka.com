"""H-2026-05-01-EARNINGS-DRIFT v1 stress-test layer.

Runs against event_factors.csv. Computes:
  1. Year stratification (FY22 / FY23 / FY24)
  2. Sector split (Banks vs IT)
  3. Sector-neutral excess return at H=5 (re-uses sector_drift_bps as proxy)
  4. Bivariate top-quintile cell: volume_z (Q5) AND trust_score (Q3-Q5)
  5. Long-straddle decomposition: do high-vol-regime quintiles dominate?

NO new edge claim. Descriptive forensic to inform v2/v3 decision.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
EVENT_CSV = ROOT / "event_factors.csv"
OPT_CSV = ROOT / "options_ledger.csv"
OUT_JSON = ROOT / "stress_v1.json"

NET_BPS_COLS = {"net_15": 15.0, "net_20": 20.0}


def _stats(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {"n": 0}
    n = len(s)
    mu = float(s.mean())
    sd = float(s.std(ddof=1)) if n > 1 else 0.0
    sharpe = mu / sd if sd > 0 else 0.0
    hit = float((s > 0).mean())
    return {
        "n": n,
        "gross": round(mu, 2),
        "std": round(sd, 2),
        "sharpe": round(sharpe, 3),
        "hit_gross": round(hit, 3),
        "net_15": round(mu - 15.0, 2),
        "net_20": round(mu - 20.0, 2),
    }


def main() -> None:
    if not EVENT_CSV.exists():
        sys.exit(f"missing {EVENT_CSV}")

    df = pd.read_csv(EVENT_CSV)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df["fy"] = df["event_date"].dt.year + (df["event_date"].dt.month >= 4).astype(int)

    out: dict = {"meta": {"n_events": int(len(df)), "stage": "Stage_A_stress_v1"}}

    # 1. YEAR STRATIFICATION at H=5 (futures, all events)
    yrs = {}
    for fy, sub in df.groupby("fy"):
        for label, col in (("h1", "ret_h1_bps"), ("h5", "ret_h5_bps"),
                            ("h10", "ret_h10_bps"), ("h21", "ret_h21_bps")):
            yrs.setdefault(int(fy), {})[label] = _stats(sub[col])
    out["by_fy"] = yrs

    # 2. SECTOR SPLIT at H=5
    sec = {}
    for sector, sub in df.groupby("sector"):
        sec[sector] = {
            "h5": _stats(sub["ret_h5_bps"]),
            "h21": _stats(sub["ret_h21_bps"]),
        }
    out["by_sector"] = sec

    # 3. SECTOR-NEUTRAL EXCESS at H=5 — subtract realized sector_drift over same window
    # We don't have a forward sector-drift column, so compute it from regime_history-equivalent
    # by using the contemporaneous sector_drift_bps (5d trailing) as a CRUDE proxy.
    # NOTE: This is approximate. Real sector-neutral requires forward sector return.
    # Skip for now — flag as v2 work.

    # 4. BIVARIATE: volume_z Q5 AND short_mom > 0
    df_sorted = df.copy()
    df_sorted["vol_q"] = pd.qcut(df_sorted["volume_z"], 5, labels=False, duplicates="drop")
    df_sorted["trust_q"] = pd.qcut(df_sorted["trust_score_pct"], 5, labels=False, duplicates="drop")

    biv = {}
    biv["vol_Q5_only"] = _stats(df_sorted.loc[df_sorted["vol_q"] == 4, "ret_h5_bps"])
    biv["vol_Q5_x_trust_top60"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 4) & (df_sorted["trust_q"] >= 2), "ret_h5_bps"]
    )
    biv["vol_Q5_x_trust_Q5"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 4) & (df_sorted["trust_q"] == 4), "ret_h5_bps"]
    )
    biv["vol_Q1_x_trust_Q1"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 0) & (df_sorted["trust_q"] == 0), "ret_h5_bps"]
    )
    biv["vol_Q5_x_short_mom_pos"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 4) & (df_sorted["short_mom_bps"] > 0), "ret_h5_bps"]
    )
    biv["vol_Q5_x_short_mom_neg"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 4) & (df_sorted["short_mom_bps"] < 0), "ret_h5_bps"]
    )
    biv["vol_Q1_x_short_mom_neg"] = _stats(
        df_sorted.loc[(df_sorted["vol_q"] == 0) & (df_sorted["short_mom_bps"] < 0), "ret_h5_bps"]
    )
    out["bivariate_h5"] = biv

    # 5. STRADDLE — by realized_vol_21d quintile (vol-regime stratification)
    if OPT_CSV.exists():
        opt = pd.read_csv(OPT_CSV)
        opt["event_date"] = pd.to_datetime(opt["event_date"])
        opt = opt[opt["horizon"] == 5].copy()
        opt = opt.merge(df[["symbol", "event_date", "realized_vol_21d_pct", "fy"]],
                         on=["symbol", "event_date"], how="left")
        opt["vol_q"] = pd.qcut(opt["realized_vol_21d_pct"], 5, labels=False, duplicates="drop")

        strad = {}
        for q in sorted(opt["vol_q"].dropna().unique()):
            qsub = opt[opt["vol_q"] == q]
            strad[f"realized_vol_q{int(q)+1}"] = {
                "n": int(len(qsub)),
                "vol_range_pct": [round(float(qsub["realized_vol_21d_pct"].min()), 2),
                                   round(float(qsub["realized_vol_21d_pct"].max()), 2)],
                "long_call_gross": round(float(qsub["pnl_long_call_bps"].mean()), 1),
                "long_put_gross": round(float(qsub["pnl_long_put_bps"].mean()), 1),
                "long_straddle_gross": round(float(qsub["pnl_long_straddle_bps"].mean()), 1),
                "futures_gross": round(float(qsub["pnl_futures_bps"].mean()), 1),
            }
        out["straddle_by_vol_quintile_h5"] = strad

        # Straddle by year
        strad_y = {}
        for fy, qsub in opt.groupby("fy"):
            strad_y[int(fy)] = {
                "n": int(len(qsub)),
                "long_straddle_gross": round(float(qsub["pnl_long_straddle_bps"].mean()), 1),
                "futures_gross": round(float(qsub["pnl_futures_bps"].mean()), 1),
                "long_call_gross": round(float(qsub["pnl_long_call_bps"].mean()), 1),
                "long_put_gross": round(float(qsub["pnl_long_put_bps"].mean()), 1),
            }
        out["straddle_by_fy_h5"] = strad_y

    # 6. UNCONDITIONAL ALPHA vs SECTOR INDEX — simple long-only minus sector-drift over same horizon
    # Approximation: sector_drift_bps (5d trailing) is NOT the forward sector-return, but useful as
    # a directional sanity check that the H=5/H=21 "drift" isn't all market beta.
    # Compute fwd return MINUS contemporaneous sector_drift as a crude excess metric.
    df["h5_minus_secdrift"] = df["ret_h5_bps"] - df["sector_drift_bps"]
    out["h5_minus_trailing_sector_drift_naive"] = _stats(df["h5_minus_secdrift"])
    out["h5_minus_trailing_sector_drift_caveat"] = (
        "TRAILING sector drift is a backward-looking proxy. "
        "Real forward-sector-neutral H=5 requires sector index forward return at event date "
        "and is a v2 build item."
    )

    # 7. EARNINGS COUNT BY YEAR
    out["events_by_fy"] = df.groupby("fy").size().to_dict()

    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    print(f"\n-> {OUT_JSON}")


if __name__ == "__main__":
    main()
