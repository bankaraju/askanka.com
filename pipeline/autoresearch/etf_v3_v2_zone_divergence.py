"""60-day v2-vs-v3 zone-label divergence.

Per user's 2026-04-26 cutover question: "the stock that we get in that
run must be compared to the current in use v2 model and compare the
differences..i suspect there will be none..lets still try."

This is the upstream half of that test — does the REGIME LABEL itself
diverge between v2 and v3 day-by-day on the same panel? If labels agree
most days, downstream stock selection will mostly agree (and the v3
cutover changes little for trade flow). If labels diverge often, the
downstream stock differences become the interesting question (#55).

Method (stage 1 — completed today):
  - For each of the last 60 trading days, compute v2's zone via
    etf_reoptimize._signal_to_zone using v2's stored optimal weights
  - For each same day, compute v3-curated's zone via _signal_to_zone
    using v3's calibrated center/band and CURATED-30 features
  - Output agreement matrix + day-by-day disagreement table

Method (stage 2 — pending cadence=1 results):
  - Replace v3-curated stage-1 weights with daily-refit weights from the
    cadence=1 rolling refit (writes per-window weights to per_window_detail)
  - Re-run divergence; see if daily-refit changes the agreement profile

Output: pipeline/data/research/etf_v3/2026-04-26-zone-divergence-60d.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "etf_v3"

V2_WEIGHTS = HERE / "etf_optimal_weights.json"
V3_WEIGHTS = HERE / "etf_v3_curated_optimal_weights.json"


def _v2_zone(signal: float) -> str:
    """v2's static thresholds."""
    if signal >= 1.5:
        return "EUPHORIA"
    if signal >= 0.5:
        return "RISK-ON"
    if signal >= -0.5:
        return "NEUTRAL"
    if signal >= -1.5:
        return "CAUTION"
    return "RISK-OFF"


def _v3_zone(signal: float, center: float, band: float) -> str:
    if signal >= center + 2 * band:
        return "EUPHORIA"
    if signal >= center + band:
        return "RISK-ON"
    if signal >= center - band:
        return "NEUTRAL"
    if signal >= center - 2 * band:
        return "CAUTION"
    return "RISK-OFF"


def compute_divergence(*, lookback_days: int = 60) -> dict:
    from pipeline.autoresearch.etf_v3_loader import (
        CURATED_FOREIGN_ETFS, build_panel,
    )
    from pipeline.autoresearch.etf_v3_research import (
        build_features, _weighted_signal,
    )

    if not V3_WEIGHTS.is_file():
        raise RuntimeError(
            f"v3 weights not found ({V3_WEIGHTS}). Run "
            f"`python -m pipeline.autoresearch.etf_v3_curated_reoptimize` first."
        )
    v3_data = json.loads(V3_WEIGHTS.read_text(encoding="utf-8"))
    v3_weights = v3_data["optimal_weights"]
    v3_center = v3_data["zone_thresholds"]["center"]
    v3_band = v3_data["zone_thresholds"]["band"]

    if not V2_WEIGHTS.is_file():
        raise RuntimeError(f"v2 weights not found ({V2_WEIGHTS})")
    v2_data = json.loads(V2_WEIGHTS.read_text(encoding="utf-8"))
    v2_weights = v2_data["optimal_weights"]

    # v3 panel + features
    panel = build_panel(t1_anchor=True)
    feats = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS))
    feats_clean = feats.dropna()
    last_n = feats_clean.iloc[-lookback_days:]
    sig_v3 = _weighted_signal(last_n, v3_weights)

    # For v2, we need the v2-shape features. v2's weights mix global ETF 1d
    # returns with raw Indian levels. Approximate with same panel using
    # 1d returns of the foreign cols + raw indian features. This is
    # APPROXIMATE — production v2 uses yfinance live fetch, not the
    # canonical loader. So this is a directionally-correct comparison,
    # not byte-identical to what production v2 would emit for the same day.
    # The point is "do the regime labels broadly agree?" which this
    # answers within the loader's representation.
    v2_feat_cols = [k for k in v2_weights if k in panel.columns]
    if v2_feat_cols:
        # Use 1d returns for foreign ETF cols (v2 architecture)
        # Identify which v2 keys are foreign ETFs (have a daily price col in panel)
        foreign_panel_cols = set(CURATED_FOREIGN_ETFS) | {
            c for c in panel.columns
            if c not in {"india_vix", "fii_net", "dii_net", "nifty_close",
                         "nifty_open", "nifty_high", "nifty_low"}
        }
        sig_v2 = pd.Series(0.0, index=last_n.index)
        for k, w in v2_weights.items():
            if k in foreign_panel_cols and k in panel.columns:
                ret_1d = panel[k].pct_change() * 100.0
                sig_v2 = sig_v2 + ret_1d.reindex(last_n.index).fillna(0.0) * float(w)
            elif k in panel.columns:
                sig_v2 = sig_v2 + panel[k].reindex(last_n.index).fillna(0.0) * float(w)
    else:
        sig_v2 = pd.Series(np.nan, index=last_n.index)

    rows = []
    agree_count = 0
    direction_agree_count = 0
    for ts in last_n.index:
        v2_signal = float(sig_v2.loc[ts])
        v3_signal = float(sig_v3.loc[ts])
        v2_zone = _v2_zone(v2_signal)
        v3_zone = _v3_zone(v3_signal, v3_center, v3_band)
        v2_dir = "UP" if v2_signal > 0 else "DOWN"
        v3_dir = "UP" if v3_signal > v3_center else "DOWN"  # relative to center
        is_zone_agree = v2_zone == v3_zone
        is_dir_agree = v2_dir == v3_dir
        if is_zone_agree:
            agree_count += 1
        if is_dir_agree:
            direction_agree_count += 1
        rows.append({
            "date": str(ts.date()),
            "v2_signal": round(v2_signal, 4),
            "v2_zone": v2_zone,
            "v3_signal": round(v3_signal, 2),
            "v3_zone": v3_zone,
            "zone_agree": is_zone_agree,
            "v2_dir": v2_dir,
            "v3_dir": v3_dir,
            "dir_agree": is_dir_agree,
        })

    n = len(rows)
    # confusion matrix
    zones = ["EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]
    confusion = {z2: {z3: 0 for z3 in zones} for z2 in zones}
    for r in rows:
        confusion[r["v2_zone"]][r["v3_zone"]] += 1

    return {
        "lookback_days": lookback_days,
        "n_days": n,
        "zone_agreement_pct": round(agree_count / n * 100, 2) if n else 0.0,
        "direction_agreement_pct": round(direction_agree_count / n * 100, 2) if n else 0.0,
        "v2_zone_distribution": {z: sum(1 for r in rows if r["v2_zone"] == z) for z in zones},
        "v3_zone_distribution": {z: sum(1 for r in rows if r["v3_zone"] == z) for z in zones},
        "confusion_matrix": confusion,
        "first_date": rows[0]["date"] if rows else None,
        "last_date": rows[-1]["date"] if rows else None,
        "rows": rows,
        "v3_zone_thresholds": {"center": v3_center, "band": v3_band},
    }


def _format_md(result: dict) -> str:
    lines = []
    lines.append("# v2-vs-v3 60-day Zone Divergence")
    lines.append("")
    lines.append(f"**Window:** {result['first_date']} → {result['last_date']} "
                 f"({result['n_days']} trading days)")
    lines.append(f"**Zone agreement:** {result['zone_agreement_pct']}%")
    lines.append(f"**Direction agreement:** {result['direction_agreement_pct']}%")
    lines.append("")
    lines.append("**v3 zone thresholds:** center="
                 f"{result['v3_zone_thresholds']['center']:.2f}, "
                 f"band={result['v3_zone_thresholds']['band']:.2f}")
    lines.append("")
    lines.append("## Zone distribution")
    lines.append("")
    lines.append("| zone | v2 days | v3 days |")
    lines.append("|---|---|---|")
    for z in ["EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]:
        lines.append(f"| {z} | {result['v2_zone_distribution'][z]} | "
                     f"{result['v3_zone_distribution'][z]} |")
    lines.append("")
    lines.append("## Confusion matrix (rows: v2 says, cols: v3 says)")
    lines.append("")
    zones = ["EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF"]
    header = "| v2 \\ v3 | " + " | ".join(zones) + " |"
    sep = "|" + "---|" * (len(zones) + 1)
    lines.append(header)
    lines.append(sep)
    for z2 in zones:
        cells = [str(result['confusion_matrix'][z2][z3]) for z3 in zones]
        lines.append(f"| **{z2}** | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Day-by-day detail (last 60)")
    lines.append("")
    lines.append("| date | v2 sig | v2 zone | v3 sig | v3 zone | zone= |")
    lines.append("|---|---|---|---|---|---|")
    for r in result["rows"]:
        agree_mark = "Y" if r["zone_agree"] else "N"
        lines.append(
            f"| {r['date']} | {r['v2_signal']:>+.3f} | {r['v2_zone']} | "
            f"{r['v3_signal']:>+.1f} | {r['v3_zone']} | {agree_mark} |"
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lookback-days", type=int, default=60)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    result = compute_divergence(lookback_days=args.lookback_days)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "zone_divergence_60d.json"
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    md_path = OUT_DIR / "2026-04-26-zone-divergence-60d.md"
    md_path.write_text(_format_md(result), encoding="utf-8")
    print(_format_md(result))
    print(f"\nwrote {json_path}\nwrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
