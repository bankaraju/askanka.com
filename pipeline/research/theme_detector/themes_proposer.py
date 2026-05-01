"""Theme Proposer v1.1.0 — discover emergent stock clusters from data.

v1 detector reads `themes_frozen.json` (12 hand-curated baskets). The real
test of theme-detector alpha is whether it can DISCOVER new clusters that
go on to mature into proper themes (Bharat 2026-05-02). This module is the
discovery half.

Inputs (all PIT at run_date d):
  - 60 trading days of daily returns from fno_historical/ + india_historical/
  - Reconstructed NIFTY-500 weight history (TD-D1 canonical)
  - multigroup_curtailed (RS quarter %, sector tag) — as fallback only
  - results_dashboard (NPS) — concentration test

Pipeline:
  1. Build returns matrix R: 60 × N over NIFTY-500 ∩ have-bars
  2. Correlation matrix C = R.corr(); distance = 1 - C
  3. Agglomerative average-linkage clustering at distance ≤ 1 - MIN_CORR
  4. Filter: 3 ≤ cluster_size ≤ 30
  5. Score each surviving cluster on 4 axes (cohesion, weight drift,
     RS concentration, EPS-surprise concentration); rank by emergence_score
  6. Emit top-K as themes JSON in same shape as themes_frozen.json

Output: pipeline/data/research/theme_detector/proposer/proposed_themes_<date>.json

Caveats:
  - No constituent-history yet — proposer uses today's NIFTY-500 set only
    (survivorship bias in look-back window). Acceptable for v1.1.0 alpha.
  - Cluster IDs are auto-generated per run; cross-week attribution
    (lifecycle continuity) is a separate component to write next.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from pipeline.research.theme_detector.data_loaders import (
    FNO_HISTORICAL_DIR,
    REPO_ROOT,
    load_multigroup_curtailed,
    load_nifty500_weights_reconstructed,
    load_results_dashboard,
)

INDIA_HISTORICAL_DIR = REPO_ROOT / "pipeline" / "data" / "india_historical"
PROPOSER_OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "theme_detector" / "proposer"

LOOKBACK_DAYS = 60
MIN_CORR = 0.55  # avg-linkage distance cut at 1 - MIN_CORR
MIN_CLUSTER_SIZE = 3
MAX_CLUSTER_SIZE = 30
TOP_K_PROPOSALS = 20


def _load_close(symbol: str) -> pd.Series | None:
    for d in (FNO_HISTORICAL_DIR, INDIA_HISTORICAL_DIR):
        p = d / f"{symbol}.csv"
        if p.exists():
            df = pd.read_csv(p)
            if "Date" in df.columns:
                date_col, close_col = "Date", "Close"
            elif "date" in df.columns:
                date_col, close_col = "date", "close"
            else:
                return None
            df[date_col] = pd.to_datetime(df[date_col])
            s = df.set_index(df[date_col].dt.date)[close_col]
            s = s[~s.index.duplicated(keep="last")]
            return s
    return None


def _build_returns_matrix(
    symbols: list[str], run_date: date, lookback: int = LOOKBACK_DAYS
) -> pd.DataFrame:
    """Returns N-day daily-return matrix indexed by date, columns by symbol.

    Drops symbols missing > 5% of dates in the window.
    """
    closes: dict[str, pd.Series] = {}
    for s in symbols:
        c = _load_close(s)
        if c is None:
            continue
        c = c[c.index <= run_date].tail(lookback + 5)
        if len(c) < lookback - 2:
            continue
        closes[s] = c
    if not closes:
        return pd.DataFrame()
    df = pd.DataFrame(closes)
    df = df.sort_index()
    df = df.tail(lookback + 1)
    rets = df.pct_change(fill_method=None).iloc[1:]
    rets = rets.dropna(axis=1, thresh=int(0.95 * lookback))
    return rets


def _cluster(rets: pd.DataFrame) -> dict[int, list[str]]:
    """Agglomerative clustering, returns {cluster_id: [symbols]}."""
    if rets.shape[1] < MIN_CLUSTER_SIZE:
        return {}
    corr = rets.corr().fillna(0.0).values
    np.fill_diagonal(corr, 1.0)
    dist = 1.0 - corr
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2  # enforce symmetry against fp noise
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=1.0 - MIN_CORR, criterion="distance")
    clusters: dict[int, list[str]] = {}
    cols = list(rets.columns)
    for i, lab in enumerate(labels):
        clusters.setdefault(int(lab), []).append(cols[i])
    return {
        cid: members for cid, members in clusters.items()
        if MIN_CLUSTER_SIZE <= len(members) <= MAX_CLUSTER_SIZE
    }


def _avg_pairwise_corr(rets: pd.DataFrame, members: list[str]) -> float:
    sub = rets[members]
    if sub.shape[1] < 2:
        return 0.0
    c = sub.corr().values
    n = c.shape[0]
    iu = np.triu_indices(n, k=1)
    return float(np.nanmean(c[iu]))


def _weight_delta_6m(weights_df: pd.DataFrame | None, members: list[str], run_date: date) -> float:
    """Sum-weight delta over ~180 days, in pp. 0 if no canonical reconstruction."""
    if weights_df is None or weights_df.empty:
        return 0.0
    dates = sorted(set(weights_df.index))
    if not dates:
        return 0.0
    today = max(dates)
    target = today - timedelta(days=180)
    past_d = max((d for d in dates if d <= target), default=None)
    if past_d is None:
        return 0.0
    today_w = weights_df[weights_df.index == today].set_index("nse_symbol")["weight_pct"]
    past_w = weights_df[weights_df.index == past_d].set_index("nse_symbol")["weight_pct"]
    members_today = [m for m in members if m in today_w.index]
    members_past = [m for m in members if m in past_w.index]
    if len(members_today) < 2 or len(members_past) < 2:
        return 0.0
    return float(today_w.reindex(members_today).sum() - past_w.reindex(members_past).sum())


def _rs_concentration(mg: pd.DataFrame | None, members: list[str]) -> float:
    """Median quarter rel-ret of members. Higher = stronger leadership."""
    if mg is None:
        return 0.0
    col = "Relative returns vs Nifty50 quarter%"
    if col not in mg.columns:
        return 0.0
    present = [m for m in members if m in mg.index]
    if not present:
        return 0.0
    return float(mg.loc[present, col].dropna().median())


def _eps_surprise_share(rd: pd.DataFrame | None, members: list[str]) -> float:
    """Share of cluster members with positive Net Profit Surprise Qtr %."""
    if rd is None:
        return 0.0
    col = "Net Profit Surprise Qtr %"
    if col not in rd.columns:
        return 0.0
    present = [m for m in members if m in rd.index]
    if not present:
        return 0.0
    s = rd.loc[present, col].dropna()
    if s.empty:
        return 0.0
    return float((s > 0).sum()) / len(s)


def _dominant_sector(mg: pd.DataFrame | None, members: list[str]) -> str:
    if mg is None:
        return "MIXED"
    sec_col = next((c for c in mg.columns if c.lower().startswith("sector")), None)
    if sec_col is None:
        return "MIXED"
    present = [m for m in members if m in mg.index]
    if not present:
        return "MIXED"
    secs = mg.loc[present, sec_col].dropna().astype(str).tolist()
    if not secs:
        return "MIXED"
    common, n = Counter(secs).most_common(1)[0]
    if n / len(secs) >= 0.5:
        return common
    return "MIXED"


def _emergence_score(
    avg_corr: float, weight_delta_pp: float, rs_median: float, eps_share: float
) -> float:
    """Emergence score in [0, ~1+]; higher = stronger candidate.

    Linear sum with hand-tuned weights. v1.1.0 alpha — to be calibrated.
    """
    avg_corr_n = max(0.0, min(1.0, (avg_corr - 0.4) / 0.5))
    weight_delta_n = max(0.0, min(1.0, weight_delta_pp / 1.0))
    rs_n = max(0.0, min(1.0, rs_median / 30.0))
    eps_n = max(0.0, min(1.0, eps_share))
    return 0.4 * avg_corr_n + 0.3 * weight_delta_n + 0.2 * rs_n + 0.1 * eps_n


def propose(run_date: date, top_k: int = TOP_K_PROPOSALS) -> dict:
    """Run proposer end-to-end at run_date. Returns themes-JSON dict."""
    weights_df = load_nifty500_weights_reconstructed(run_date)
    if weights_df is None or weights_df.empty:
        raise SystemExit(
            "No reconstructed NIFTY-500 weights available — run "
            "pipeline.scripts.reconstruct_nifty500_weight_history first."
        )
    today = max(weights_df.index)
    if today > run_date:
        weights_df = weights_df[weights_df.index <= run_date]
        today = max(weights_df.index)
    universe = sorted(set(weights_df[weights_df.index == today]["nse_symbol"]))
    print(f"universe: {len(universe)} stocks (NIFTY-500 intersect have-bars at {today})")

    rets = _build_returns_matrix(universe, run_date)
    print(f"returns matrix: {rets.shape[0]} days × {rets.shape[1]} stocks")
    if rets.empty:
        raise SystemExit("returns matrix empty")

    clusters = _cluster(rets)
    print(f"clusters surviving size + corr filter: {len(clusters)}")

    mg = load_multigroup_curtailed(run_date, "returns_shareholding")
    rd = load_results_dashboard(run_date)
    today_w = weights_df[weights_df.index == today].set_index("nse_symbol")["weight_pct"]

    proposals: list[dict] = []
    for cid, members in clusters.items():
        avg_c = _avg_pairwise_corr(rets, members)
        wdelta = _weight_delta_6m(weights_df, members, run_date)
        rs_med = _rs_concentration(mg, members)
        eps_share = _eps_surprise_share(rd, members)
        sector = _dominant_sector(mg, members)
        sum_w = float(today_w.reindex(members).fillna(0).sum())
        score = _emergence_score(avg_c, wdelta, rs_med, eps_share)
        proposals.append({
            "theme_id": f"PROPOSED_{run_date.isoformat()}_C{cid:03d}",
            "tier_1_sector": sector,
            "rule_kind": "A",
            "rule_definition": {"members": sorted(members)},
            "rationale": (
                f"auto-discovered cluster: avg_pairwise_corr={avg_c:.3f}, "
                f"sum_weight_pct={sum_w:.3f}, weight_delta_6m_pp={wdelta:+.4f}, "
                f"rs_median_qtr_pct={rs_med:+.2f}, eps_surprise_share={eps_share:.2f}, "
                f"sector_dom={sector}"
            ),
            "proposer_metadata": {
                "run_date": run_date.isoformat(),
                "n_members": len(members),
                "avg_pairwise_corr": round(avg_c, 6),
                "sum_weight_pct": round(sum_w, 6),
                "weight_delta_6m_pp": round(wdelta, 6),
                "rs_median_qtr_pct": round(rs_med, 4),
                "eps_surprise_share": round(eps_share, 4),
                "emergence_score": round(score, 6),
                "sector_dominant": sector,
            },
        })
    proposals.sort(key=lambda r: -r["proposer_metadata"]["emergence_score"])
    proposals = proposals[:top_k]

    out = {
        "schema_version": "v1.1",
        "frozen_date": run_date.isoformat(),
        "source": "themes_proposer_v1.1.0",
        "notes": (
            f"Auto-proposed clusters at run_date={run_date.isoformat()}. "
            f"{len(proposals)} clusters above MIN_CORR={MIN_CORR} and "
            f"size {MIN_CLUSTER_SIZE}-{MAX_CLUSTER_SIZE}. "
            "Discovery candidates only — not human-vetted; lifecycle FSM still "
            "applies whether human-curated or proposed."
        ),
        "themes": proposals,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--top-k", type=int, default=TOP_K_PROPOSALS)
    ap.add_argument("--out-dir", default=str(PROPOSER_OUT_DIR))
    args = ap.parse_args(argv)
    run_d = date.fromisoformat(args.run_date) if args.run_date else date.today()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = propose(run_d, top_k=args.top_k)
    out_path = out_dir / f"proposed_themes_{run_d.isoformat()}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path.relative_to(REPO_ROOT)} ({len(payload['themes'])} themes)")
    print("\nTop 5 by emergence score:")
    for t in payload["themes"][:5]:
        m = t["proposer_metadata"]
        print(
            f"  {t['theme_id']}  "
            f"score={m['emergence_score']:.3f}  "
            f"n={m['n_members']:>2d}  "
            f"corr={m['avg_pairwise_corr']:.2f}  "
            f"w_d6m={m['weight_delta_6m_pp']:+.3f}pp  "
            f"sec={m['sector_dominant']}  "
            f"members={', '.join(t['rule_definition']['members'][:5])}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
