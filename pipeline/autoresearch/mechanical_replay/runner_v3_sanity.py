"""v3-universe sanity replay — ADDITIVE, does not modify v2 artifacts.

Purpose:
  Re-run the same v2 mechanical-replay orchestration on
  canonical_fno_research_v3 (273 tickers) over the SAME window
  (2026-02-24 → 2026-04-24) to confirm the production-candidate rule
  (PCR-stripped ≥2σ TIME_STOP+TRAIL+ATR) still holds on the bigger universe.

Differences from runner_v2.py:
  1. CanonicalLoader is constructed with canonical_path =
     pipeline/data/canonical_fno_research_v3.json (not the constants.py
     v1 default).
  2. Output dir is pipeline/data/research/mechanical_replay/v3_sanity/
     (separate from the v2 artifact dir).
  3. Z_CROSS exits are disabled (matches the production-candidate rule
     evaluated at trades_no_zcross.csv) — we additionally re-emit the
     no-zcross artifact so this script is self-contained.
  4. PCR archive is implicitly NEUTRAL — same as the v2 reference run
     (recon_phase_c.regenerate inherits classify_break's NEUTRAL default
     when no per-day PCR is available).

NOT a replacement for runner_v2.py. NOT registered as a hypothesis.
This is a one-shot sanity confirmation; nothing here is cited as evidence
for a model promotion.

Spec backing the parent v2 run:
  docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.mechanical_replay import (
    canonical_loader,
    constants as C,
    runner_v2,
)
from pipeline.autoresearch.phase_c_shape_audit import constants as sp1_const

logger = logging.getLogger("mechanical_replay.v3_sanity")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

V3_CANONICAL_JSON = C._REPO / "pipeline" / "data" / "canonical_fno_research_v3.json"
V3_OUT_DIR = (
    C._REPO / "pipeline" / "data" / "research" / "mechanical_replay" / "v3_sanity"
)


def _bucket(z: float) -> str:
    if pd.isna(z):
        return "NA"
    a = abs(float(z))
    if a < 2.0:
        return "<2.0"
    if a < 3.0:
        return "[2.0,3.0)"
    if a < 4.0:
        return "[3.0,4.0)"
    if a < 5.0:
        return "[4.0,5.0)"
    return "5.0+"


def main() -> int:
    window_start = pd.Timestamp("2026-02-24")
    window_end = pd.Timestamp("2026-04-24")

    V3_OUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("v3 sanity replay — out_dir=%s", V3_OUT_DIR)
    logger.info("v3 universe path=%s", V3_CANONICAL_JSON)

    # 1. Construct loader pinned to v3 (constants.py untouched).
    loader = canonical_loader.CanonicalLoader(canonical_path=V3_CANONICAL_JSON)
    logger.info(
        "loaded v3 universe: %d tickers, dataset_id=%s",
        len(loader.universe), loader.dataset_id,
    )

    pair_config = runner_v2._load_pair_config()

    # 2. Reconstruct rosters (regime, phase_c, phase_b, spread) on v3 universe.
    rosters, _universe_bars = runner_v2.reconstruct_all(
        window_start=window_start, window_end=window_end,
        loader=loader, pair_config=pair_config,
    )
    pc_roster = rosters["phase_c"]

    # 3. Simulate Phase C with Z_CROSS disabled (production-candidate rule).
    logger.info(
        "simulating %d Phase C rows with enable_zcross=False…", len(pc_roster),
    )
    trades = runner_v2.simulate_phase_c_trades(
        phase_c_roster=pc_roster, loader=loader,
        bars_dir=sp1_const.BARS_DIR, no_fetch=True,
        enable_zcross=False,
    )
    trades_df = pd.DataFrame(trades)

    # 4. Annotate z_score / sector / abs_z / z_bucket from roster.
    zmap = pc_roster.set_index("signal_id")["z_score"].to_dict()
    secmap = pc_roster.set_index("signal_id")["sector"].to_dict()
    trades_df["z_score"] = trades_df["signal_id"].map(zmap)
    trades_df["sector"] = trades_df["signal_id"].map(secmap)
    trades_df["abs_z"] = trades_df["z_score"].abs()
    filled = trades_df[trades_df["pnl_pct"].notna()].copy()
    filled["z_bucket"] = filled["abs_z"].apply(_bucket)

    # 5. Persist trades_no_zcross.csv (same schema as v2 reference).
    out_cols = [
        "signal_id", "ticker", "date", "regime", "classification",
        "sector", "side", "exit_reason", "pnl_pct", "abs_z", "z_bucket",
    ]
    out = filled[out_cols].copy()
    trades_csv = V3_OUT_DIR / "trades_no_zcross.csv"
    out.to_csv(trades_csv, index=False)
    logger.info("wrote %d filled trades → %s", len(out), trades_csv)

    # Also persist the full pre-filter trades dataframe (incl. FETCH_FAILED rows)
    # for forensic accounting of fetch coverage on v3-new tickers.
    full_csv = V3_OUT_DIR / "trades_full.csv"
    trades_df.to_csv(full_csv, index=False)
    logger.info("wrote %d total trade rows (incl. fetch fails) → %s",
                len(trades_df), full_csv)

    # 6. Print headline stats requested by the sanity-check ticket.
    print()
    print("=== v3 universe sanity replay ===")
    print(f"window: {window_start.date()} -> {window_end.date()}")
    print(f"universe: {len(loader.universe)} tickers (v3)")
    print(f"phase_c roster rows: {len(pc_roster)}")
    print(f"simulated trades (rows): {len(trades_df)}")
    print(
        f"filled (pnl_pct not null): {len(filled)} "
        f"(fetch fails: {len(trades_df) - len(filled)})"
    )

    print()
    print("=== >=2sigma slice on v3 universe (273 tickers) -- no Z_CROSS ===")
    s = filled[filled["abs_z"] >= 2.0]
    if not s.empty:
        n = len(s)
        hit = (s["pnl_pct"] > 0).mean() * 100
        mean = s["pnl_pct"].mean()
        total = s["pnl_pct"].sum()
        print(f"n trades:  {n}")
        print(f"hit rate:  {hit:.2f}%")
        print(f"mean P&L:  {mean:+.2f}%")
        print(f"total P&L: {total:+.2f}pp")
    else:
        print("(no ≥2σ trades — empty slice)")

    print()
    print("=== >=2sigma by regime ===")
    if not s.empty:
        rb = s.groupby("regime").agg(
            n=("pnl_pct", "size"),
            hit=("pnl_pct", lambda x: (x > 0).mean() * 100),
            mean=("pnl_pct", "mean"),
            total=("pnl_pct", "sum"),
        ).round(2).sort_values("total", ascending=False)
        print(rb.to_string())
    else:
        print("(empty)")

    print()
    print("=== >=2sigma by classification ===")
    if not s.empty:
        cl = s.groupby("classification").agg(
            n=("pnl_pct", "size"),
            hit=("pnl_pct", lambda x: (x > 0).mean() * 100),
            mean=("pnl_pct", "mean"),
            total=("pnl_pct", "sum"),
        ).round(2).sort_values("total", ascending=False)
        print(cl.to_string())

    print()
    print("=== |z-score| buckets (no Z_CROSS) -- full filled trade set ===")
    zb = filled.groupby("z_bucket").agg(
        n=("pnl_pct", "size"),
        hit=("pnl_pct", lambda x: (x > 0).mean() * 100),
        mean=("pnl_pct", "mean"),
        total=("pnl_pct", "sum"),
    ).round(2)
    order = ["<2.0", "[2.0,3.0)", "[3.0,4.0)", "[4.0,5.0)", "5.0+", "NA"]
    zb = zb.reindex([b for b in order if b in zb.index])
    print(zb.to_string())

    # 7. Persist a small sanity_summary.json so the next reader doesn't have
    # to recompute. NOT registered, NOT cited in any spec.
    summary = {
        "dataset_id": loader.dataset_id,
        "universe_size": len(loader.universe),
        "window_start": str(window_start.date()),
        "window_end": str(window_end.date()),
        "phase_c_roster_rows": int(len(pc_roster)),
        "simulated_rows": int(len(trades_df)),
        "filled_rows": int(len(filled)),
        "fetch_fail_rows": int(len(trades_df) - len(filled)),
        "ge_2sigma": (
            None if s.empty else {
                "n": int(len(s)),
                "hit_pct": round(float((s["pnl_pct"] > 0).mean() * 100), 2),
                "mean_pnl_pct": round(float(s["pnl_pct"].mean()), 4),
                "total_pnl_pp": round(float(s["pnl_pct"].sum()), 2),
            }
        ),
        "v1_baseline_for_reference": {
            "n": 42, "hit_pct": 92.86,
            "mean_pnl_pct": 1.66, "total_pnl_pp": 69.83,
            "source": "trades_no_zcross.csv on canonical_fno_research_v1",
        },
        "notes": [
            "ADDITIVE sanity run; does not modify v2 artifacts.",
            "PCR-stripped: per-day PCR archive empty → classify_break uses NEUTRAL default.",
            "Z_CROSS exits disabled (TIME_STOP/TRAIL/ATR/HARD_CLOSE only).",
            "Minute-bar cache is no_fetch=True; v3-new tickers without cached parquets fall to FETCH_FAILED.",
        ],
    }
    summary_path = V3_OUT_DIR / "sanity_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("wrote sanity summary → %s", summary_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
