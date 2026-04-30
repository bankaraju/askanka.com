"""Sector-correlation stability study — full pipeline.

Run with:  python -m pipeline.research.sector_correlation.run_study

Phases follow the design doc 2026-04-30:
  0. (delegated) Data acceptance audit + sector-panel build —
     :mod:`pipeline.research.sector_panel` is the canonical, registered
     dataset every study reads from. We do NOT re-audit per study.
  1. Load the canonical panel
  2. Pairwise stability via 100 bootstrap 1y windows
  3. Lead-lag at lags 0, +1, +2, +3
  4. Up/down asymmetric correlation
  5. Hierarchical clustering on the full-period matrix
  6. Findings markdown

Discovery-only. No edge claim, no trading rule, no kill-switch file.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("anka.sector_correlation")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT_DIR = REPO_ROOT / "pipeline" / "data" / "research" / "sector_correlation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Stability thresholds — locked here per the design doc, not parameterised
# at call time. Changing these mid-flight is what produces p-hacked findings.
# Data-validation thresholds (coverage, staleness, etc.) live in
# pipeline.research.sector_panel.builder — single dataset, one contract.
STABILITY_FRAC = 0.70          # fraction of windows |corr|>=0.5 to be "stable"
STABILITY_ABS = 0.50
ANTI_CORR_FRAC = 0.70
ANTI_CORR_THRESHOLD = -0.30
ASYMMETRIC_GAP = 0.30          # |corr_up - corr_down| threshold
N_BOOTSTRAP_WINDOWS = 100
BOOTSTRAP_WINDOW_DAYS = 252    # ≈1y trading days
RNG_SEED = 20260430            # deterministic — same draws every run


# ---------------------------------------------------------------------------
# Phase 2 + 3 — Pairwise stability + lead-lag (panel comes from
# pipeline.research.sector_panel — see main() for the load path).
# ---------------------------------------------------------------------------

def _safe_corr(x: pd.Series, y: pd.Series) -> float | None:
    aligned = pd.concat([x, y], axis=1).dropna()
    if len(aligned) < 30:
        return None
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def phase_2_pairwise_stability(panel: pd.DataFrame) -> dict:
    """Full-period correlation + bootstrap stability + lead-lag per pair."""
    rng = np.random.default_rng(RNG_SEED)
    sectors = list(panel.columns)
    n = len(panel)
    if n < BOOTSTRAP_WINDOW_DAYS + 50:
        raise RuntimeError(f"panel too short for {BOOTSTRAP_WINDOW_DAYS}-day windows")

    starts = rng.integers(low=0, high=n - BOOTSTRAP_WINDOW_DAYS,
                          size=N_BOOTSTRAP_WINDOWS)

    out_pairs: list[dict] = []
    for i, s_i in enumerate(sectors):
        for s_j in sectors[i + 1:]:
            full_corr = _safe_corr(panel[s_i], panel[s_j])
            if full_corr is None:
                continue
            window_corrs = []
            for st in starts:
                w = panel.iloc[st:st + BOOTSTRAP_WINDOW_DAYS]
                c = _safe_corr(w[s_i], w[s_j])
                if c is not None:
                    window_corrs.append(c)
            if not window_corrs:
                continue
            arr = np.asarray(window_corrs)
            stable_pos = float(np.mean(arr >= STABILITY_ABS))
            stable_neg = float(np.mean(arr <= ANTI_CORR_THRESHOLD))
            stable_abs = float(np.mean(np.abs(arr) >= STABILITY_ABS))

            # Lead-lag: i leads j at lag k means corr(i_t, j_{t+k}) is
            # higher than contemporaneous. Test lags +1, +2, +3.
            lead_lag = {}
            for k in (1, 2, 3):
                ck = _safe_corr(panel[s_i], panel[s_j].shift(-k))
                lead_lag[f"lag_+{k}"] = ck
            # Reciprocal: j leads i
            lead_lag_rev = {}
            for k in (1, 2, 3):
                ck = _safe_corr(panel[s_j], panel[s_i].shift(-k))
                lead_lag_rev[f"lag_+{k}"] = ck

            out_pairs.append({
                "sector_i": s_i,
                "sector_j": s_j,
                "full_corr": round(full_corr, 4),
                "boot_mean": round(float(np.mean(arr)), 4),
                "boot_p5": round(float(np.percentile(arr, 5)), 4),
                "boot_p95": round(float(np.percentile(arr, 95)), 4),
                "stability_pos": round(stable_pos, 3),
                "stability_neg": round(stable_neg, 3),
                "stability_abs": round(stable_abs, 3),
                "is_stable_correlated": stable_pos >= STABILITY_FRAC,
                "is_stable_anti": stable_neg >= ANTI_CORR_FRAC,
                "lead_lag_i_leads_j": {k: round(v, 4) if v is not None else None
                                        for k, v in lead_lag.items()},
                "lead_lag_j_leads_i": {k: round(v, 4) if v is not None else None
                                        for k, v in lead_lag_rev.items()},
            })
    out = {"thresholds": {"stability_frac": STABILITY_FRAC,
                          "stability_abs": STABILITY_ABS,
                          "anti_corr_frac": ANTI_CORR_FRAC,
                          "anti_corr_threshold": ANTI_CORR_THRESHOLD,
                          "n_windows": N_BOOTSTRAP_WINDOWS,
                          "window_days": BOOTSTRAP_WINDOW_DAYS},
           "pairs": out_pairs}
    (OUT_DIR / "pairwise_correlation.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    log.info("wrote pairwise_correlation.json — %d pairs", len(out_pairs))
    return out


# ---------------------------------------------------------------------------
# Phase 4 — Up/down asymmetric correlation
# ---------------------------------------------------------------------------

def phase_4_asymmetric(panel: pd.DataFrame) -> dict:
    """For each pair, compute correlation conditional on market-up/down days.

    Market-up day = day where the cross-sectional median sector return > 0.
    """
    median_day = panel.median(axis=1)
    up_mask = median_day > 0
    dn_mask = median_day < 0

    sectors = list(panel.columns)
    rows = []
    for i, s_i in enumerate(sectors):
        for s_j in sectors[i + 1:]:
            corr_up = _safe_corr(panel[s_i][up_mask], panel[s_j][up_mask])
            corr_dn = _safe_corr(panel[s_i][dn_mask], panel[s_j][dn_mask])
            if corr_up is None or corr_dn is None:
                continue
            gap = corr_up - corr_dn
            rows.append({
                "sector_i": s_i,
                "sector_j": s_j,
                "corr_up_days": round(corr_up, 4),
                "corr_down_days": round(corr_dn, 4),
                "gap_up_minus_down": round(gap, 4),
                "is_asymmetric": abs(gap) >= ASYMMETRIC_GAP,
            })
    out = {"threshold": ASYMMETRIC_GAP, "pairs": rows}
    (OUT_DIR / "up_down_conditional.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    log.info("wrote up_down_conditional.json — %d pairs", len(rows))
    return out


# ---------------------------------------------------------------------------
# Phase 5 — Hierarchical clustering with bootstrap
# ---------------------------------------------------------------------------

def phase_5_clusters(panel: pd.DataFrame) -> dict:
    """Hierarchical clustering on (1 - |corr|) distance + bootstrap stability.

    Cuts at distance 0.5 (loose) and reports cluster membership. For
    bootstrap stability, re-cluster on each window and count co-membership
    frequency for each pair.
    """
    from scipy.cluster import hierarchy
    from scipy.spatial.distance import squareform

    rng = np.random.default_rng(RNG_SEED + 1)
    sectors = list(panel.columns)
    n_sec = len(sectors)
    full_corr = panel.corr().values
    full_dist = 1.0 - np.abs(full_corr)
    np.fill_diagonal(full_dist, 0.0)
    condensed = squareform(full_dist, checks=False)
    Z = hierarchy.linkage(condensed, method="average")
    full_clusters = hierarchy.fcluster(Z, t=0.5, criterion="distance")

    cluster_map: dict[int, list[str]] = {}
    for sec, c in zip(sectors, full_clusters):
        cluster_map.setdefault(int(c), []).append(sec)

    # Bootstrap co-membership: for each pair, fraction of windows in
    # which they end up in the same cluster at the same distance cut.
    n_panel = len(panel)
    starts = rng.integers(low=0, high=n_panel - BOOTSTRAP_WINDOW_DAYS,
                          size=N_BOOTSTRAP_WINDOWS)
    co_member = np.zeros((n_sec, n_sec), dtype=float)
    n_valid = 0
    for st in starts:
        w = panel.iloc[st:st + BOOTSTRAP_WINDOW_DAYS]
        if len(w.dropna(how="all")) < BOOTSTRAP_WINDOW_DAYS // 2:
            continue
        wcorr = w.corr().values
        if np.isnan(wcorr).any():
            continue
        wdist = 1.0 - np.abs(wcorr)
        np.fill_diagonal(wdist, 0.0)
        try:
            wcond = squareform(wdist, checks=False)
            wZ = hierarchy.linkage(wcond, method="average")
            wclust = hierarchy.fcluster(wZ, t=0.5, criterion="distance")
        except Exception:
            continue
        for a in range(n_sec):
            for b in range(n_sec):
                if wclust[a] == wclust[b]:
                    co_member[a, b] += 1.0
        n_valid += 1
    if n_valid > 0:
        co_member /= n_valid

    clusters_out = []
    for cid, members in cluster_map.items():
        if len(members) < 2:
            continue
        idx = [sectors.index(m) for m in members]
        sub_corrs = [full_corr[i, j] for ii, i in enumerate(idx) for j in idx[ii + 1:]]
        sub_co = [co_member[i, j] for ii, i in enumerate(idx) for j in idx[ii + 1:]]
        clusters_out.append({
            "cluster_id": cid,
            "members": sorted(members),
            "size": len(members),
            "mean_within_corr": round(float(np.mean(sub_corrs)), 4) if sub_corrs else None,
            "mean_co_membership_freq": round(float(np.mean(sub_co)), 4) if sub_co else None,
            "is_stable_cluster": bool(np.mean(sub_co) >= 0.60) if sub_co else False,
        })
    clusters_out.sort(key=lambda c: -c["size"])

    out = {
        "distance_cutoff": 0.5,
        "linkage": "average",
        "n_valid_bootstrap_windows": n_valid,
        "clusters": clusters_out,
        "singletons": sorted([c["members"][0] for c in
                              [{"members": v} for k, v in cluster_map.items()]
                              if len(c["members"]) == 1]),
    }
    (OUT_DIR / "clusters.json").write_text(json.dumps(out, indent=2),
                                            encoding="utf-8")
    log.info("wrote clusters.json — %d clusters of size>=2 (n_valid windows=%d)",
             len(clusters_out), n_valid)
    return out


# ---------------------------------------------------------------------------
# Phase 6 — Findings markdown
# ---------------------------------------------------------------------------

def phase_6_findings(audit: dict, panel: pd.DataFrame, pairwise: dict,
                     asym: dict, clusters: dict,
                     panel_meta: dict | None = None) -> None:
    today = date.today().isoformat()
    pairs = pairwise["pairs"]
    asym_pairs = asym["pairs"]

    stable_pos = sorted([p for p in pairs if p["is_stable_correlated"]],
                         key=lambda p: -p["boot_mean"])
    stable_neg = sorted([p for p in pairs if p["is_stable_anti"]],
                         key=lambda p: p["boot_mean"])

    def _best_lead(p: dict) -> tuple[str, str, float] | None:
        full = p["full_corr"]
        candidates = []
        for k, v in p["lead_lag_i_leads_j"].items():
            if v is not None and v > full:
                candidates.append((p["sector_i"], p["sector_j"], k, v - full))
        for k, v in p["lead_lag_j_leads_i"].items():
            if v is not None and v > full:
                candidates.append((p["sector_j"], p["sector_i"], k, v - full))
        if not candidates:
            return None
        return max(candidates, key=lambda c: c[3])

    leaders = []
    for p in pairs:
        if p["stability_abs"] < STABILITY_FRAC:
            continue
        best = _best_lead(p)
        if best is None:
            continue
        leaders.append({"leader": best[0], "follower": best[1], "lag": best[2],
                        "improvement_over_contemp": round(best[3], 4),
                        "full_corr": p["full_corr"]})
    leaders.sort(key=lambda x: -x["improvement_over_contemp"])

    asymmetric = sorted([a for a in asym_pairs if a["is_asymmetric"]],
                         key=lambda a: -abs(a["gap_up_minus_down"]))

    pu_telecom = next(
        (p for p in pairs
         if {p["sector_i"], p["sector_j"]} == {"Power_Utilities", "Telecom"}),
        None,
    )

    pm = panel_meta or {}
    pm_built = pm.get("started_at", "n/a")
    pm_sha = pm.get("git_sha") or "?"
    lines = [
        f"# Sector-correlation study — findings {today}",
        "",
        "_Discovery-only. No edge claim, no hypothesis-registry entry. "
        "See `docs/research/sector_correlation/2026-04-30-design.md`._",
        "",
        "## Dataset provenance (canonical sector panel)",
        f"- Source: `pipeline/research/sector_panel` (canonical, "
        f"registered)",
        f"- Built at: `{pm_built}` (git `{pm_sha}`)",
        f"- Audit: {audit.get('accepted','?')} tickers accepted, "
        f"{audit.get('low_coverage_excluded','?')} low-coverage excluded, "
        f"{audit.get('stale_tail_excluded','?')} stale-tail excluded, "
        f"{audit.get('mapped_to_sector','?')} mapped to sector",
        "",
        "## Coverage",
        f"- {panel.shape[1]} sectors × {panel.shape[0]} trading days in panel",
        f"- {N_BOOTSTRAP_WINDOWS} random {BOOTSTRAP_WINDOW_DAYS}-day windows "
        f"used for stability tests",
        "",
        "## Stable correlated pairs (top 10)",
        "| Sector A | Sector B | full corr | boot mean | stability % |",
        "|---|---|---|---|---|",
    ]
    for p in stable_pos[:10]:
        lines.append(f"| {p['sector_i']} | {p['sector_j']} | "
                      f"{p['full_corr']:+.3f} | {p['boot_mean']:+.3f} | "
                      f"{int(p['stability_pos']*100)}% |")
    if not stable_pos:
        lines.append("| _(none above threshold)_ | | | | |")

    lines += [
        "",
        "## Stable anti-correlated pairs (top 10)",
        "| Sector A | Sector B | full corr | boot mean | stability % |",
        "|---|---|---|---|---|",
    ]
    for p in stable_neg[:10]:
        lines.append(f"| {p['sector_i']} | {p['sector_j']} | "
                      f"{p['full_corr']:+.3f} | {p['boot_mean']:+.3f} | "
                      f"{int(p['stability_neg']*100)}% |")
    if not stable_neg:
        lines.append("| _(none above threshold)_ | | | | |")

    lines += [
        "",
        "## Stable lead-lag candidates (top 10)",
        "_Sectors whose return at day d predicts the other's return at "
        "day d+k better than contemporaneous correlation._",
        "",
        "| Leader | Follower | Lag | Lift over contemp | Full corr |",
        "|---|---|---|---|---|",
    ]
    for ld in leaders[:10]:
        lines.append(f"| {ld['leader']} | {ld['follower']} | {ld['lag']} | "
                      f"+{ld['improvement_over_contemp']:.3f} | "
                      f"{ld['full_corr']:+.3f} |")
    if not leaders:
        lines.append("| _(no stable lead-lag found)_ | | | | |")

    lines += [
        "",
        "## Asymmetric pairs (top 5 — different on up vs down days)",
        "| Sector A | Sector B | corr (up days) | corr (down days) | gap |",
        "|---|---|---|---|---|",
    ]
    for a in asymmetric[:5]:
        lines.append(f"| {a['sector_i']} | {a['sector_j']} | "
                      f"{a['corr_up_days']:+.3f} | {a['corr_down_days']:+.3f} | "
                      f"{a['gap_up_minus_down']:+.3f} |")
    if not asymmetric:
        lines.append("| _(no asymmetric pair above threshold)_ | | | | |")

    lines += [
        "",
        "## Stable clusters (size ≥ 2, co-membership ≥ 60%)",
    ]
    stable_clusters = [c for c in clusters["clusters"] if c["is_stable_cluster"]]
    if not stable_clusters:
        lines.append("_No clusters met the 60% bootstrap stability bar at "
                      "the 0.5 distance cutoff. Sector co-movement is "
                      "regime-dependent._")
    else:
        for c in stable_clusters:
            lines.append(f"- **{', '.join(c['members'])}** "
                          f"(size {c['size']}, mean within-corr "
                          f"{c['mean_within_corr']:+.3f}, co-membership "
                          f"{int(c['mean_co_membership_freq']*100)}%)")

    lines += [
        "",
        "## Today's motivating observation",
        "_2026-04-30 H-001: Power & Utilities n=5 1W/4L mean -0.84%; "
        "Telecom n=2 2W/0L mean +4.01%._",
        "",
    ]
    if pu_telecom:
        lines.append(f"Power_Utilities × Telecom historical pair stats:")
        lines.append(f"- full-period corr: {pu_telecom['full_corr']:+.3f}")
        lines.append(f"- bootstrap mean: {pu_telecom['boot_mean']:+.3f}")
        lines.append(f"- bootstrap [p5, p95]: "
                      f"[{pu_telecom['boot_p5']:+.3f}, "
                      f"{pu_telecom['boot_p95']:+.3f}]")
        lines.append(f"- stability (|corr|≥0.5): "
                      f"{int(pu_telecom['stability_abs']*100)}%")
        if pu_telecom["is_stable_anti"]:
            lines.append("- **VERDICT:** stably anti-correlated. "
                          "Today's split (Telecom up, P&U down) "
                          "matches the historical pattern.")
        elif pu_telecom["is_stable_correlated"]:
            lines.append("- **VERDICT:** stably positively correlated. "
                          "Today's split (Telecom up, P&U down) is "
                          "*against* the historical pattern — possible "
                          "regime break or single-day noise.")
        else:
            lines.append("- **VERDICT:** no stable correlation either way. "
                          "Today's split is consistent with these two "
                          "sectors not having a structural relationship.")
    else:
        lines.append("_(Pair not found in panel — check sector mapping)_")

    lines += [
        "",
        "## What this study does NOT certify",
        "- No pair certified for live execution.",
        "- No trading rule emitted.",
        "- Acting on any finding requires a fresh single-touch holdout "
        "registration per backtesting-specs.txt §10.4.",
    ]

    out = OUT_DIR / f"findings_{today.replace('-','_')}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote %s", out)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    log.info("PHASE 0/1 — loading canonical sector panel "
             "(pipeline.research.sector_panel)")
    from pipeline.research.sector_panel import (
        load_canonical_panel, load_canonical_metadata,
    )
    panel = load_canonical_panel()
    panel_meta = load_canonical_metadata()
    audit_summary = (panel_meta.get("extras") or {}).get("audit", {})
    log.info("canonical panel: shape %s, built %s, sectors=%d",
             list(panel.shape), panel_meta.get("started_at"), panel.shape[1])

    log.info("PHASE 2/3 — pairwise stability + lead-lag (%d windows)",
              N_BOOTSTRAP_WINDOWS)
    pairwise = phase_2_pairwise_stability(panel)

    log.info("PHASE 4 — up/down asymmetric correlation")
    asym = phase_4_asymmetric(panel)

    log.info("PHASE 5 — hierarchical clustering")
    clusters = phase_5_clusters(panel)

    log.info("PHASE 6 — findings markdown")
    phase_6_findings(audit_summary, panel, pairwise, asym, clusters,
                     panel_meta=panel_meta)

    log.info("DONE — outputs in %s", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
