"""Phase 2 regime evaluation — Tests 1 through 4.

The smoke-diagnostic verdict (STOP on edge t-stat = 0.27) was correct for the
question it asked: does the model predict NIFTY direction better than the
51.72 percent global baseline. But that is the wrong question for v3-CURATED.

The model's job is to label each day as one of five regime zones --
EUPHORIA / RISK-ON / NEUTRAL / CAUTION / RISK-OFF -- and the trading thesis
is that *given the regime label*, regime-specific sectors / stocks have a
directional edge. NIFTY directional accuracy on all days collapses that
information into a single binary, which is the wrong lens.

This module implements the four-test evaluation framework discussed
2026-04-26 with the user, against the smoke run's saved per-window weights:

  Test 1 -- Daily regime classification accuracy
            Reconstruct the daily 5-zone label from each OOS window's
            weight vector, apply the production 2-day hysteresis, and
            measure NIFTY next-day directional accuracy per zone.
            Expectation: NEUTRAL ~50 percent + roughly 77 percent of days,
            RISK-ON / EUPHORIA bullish bias, CAUTION / RISK-OFF bearish bias.

  Test 2 -- Regime-specific stock selection (sector excess returns).
  Test 3 -- Full regime-then-sector pipeline P&L.
  Test 4 -- High-conviction marker stack.

Tests 2-4 are wired in this module but Test 1 is the load-bearing one --
without per-zone directional separation, Tests 2-4 are moot.

Zone thresholds are re-derived per window from the in-sample signal
distribution to avoid look-ahead. Test 1 ignores the window's own NIFTY
target -- it scores the *zone label* against next-day NIFTY return, which
the rolling-refit module never optimised against.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ZONE_LABELS = ("EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF")

# Zone hypothesis: the direction a zone is expected to lean for NIFTY next day.
# +1 = expect up, 0 = no directional expectation, -1 = expect down. Used to
# compute "directional accuracy" only for zones with a directional hypothesis.
ZONE_DIRECTION_HYPOTHESIS = {
    "EUPHORIA": -1,   # overextended -> reversal risk (down bias)
    "RISK-ON": +1,    # bullish trending
    "NEUTRAL": 0,     # ~50 percent, no direction
    "CAUTION": -1,    # defensive, rising volatility
    "RISK-OFF": -1,   # crisis mode, sharp drops
}


# ---------------------------------------------------------------------------
# Pure helpers (testable without panel / yfinance)
# ---------------------------------------------------------------------------


def signal_to_zone(signal: float, center: float, band: float) -> str:
    """5-zone bucketing using mean +/- band brackets.

    Mirrors `pipeline.autoresearch.etf_v3_curated_signal._signal_to_zone` so the
    evaluator and the live signal use the same boundaries; if production ever
    flips a boundary, both sides stay in sync.
    """
    if not np.isfinite(signal):
        raise ValueError("signal must be finite")
    if not np.isfinite(center) or not np.isfinite(band) or band <= 0:
        raise ValueError("center must be finite and band must be positive finite")
    if signal >= center + 2 * band:
        return "EUPHORIA"
    if signal >= center + band:
        return "RISK-ON"
    if signal >= center - band:
        return "NEUTRAL"
    if signal >= center - 2 * band:
        return "CAUTION"
    return "RISK-OFF"


def apply_hysteresis(raw_zones: Sequence[str], k: int = 2) -> list[str]:
    """Apply the production 2-day hysteresis rule.

    The official zone flips only after the raw classification stays in a new
    zone for `k` consecutive days. Single-day flips are absorbed into the
    previous official zone.

    Edge case: the first day has no prior official zone; we initialise the
    official zone to the first raw zone (no hysteresis to apply yet).
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if not raw_zones:
        return []
    out: list[str] = [raw_zones[0]]
    candidate: Optional[str] = None
    candidate_count = 0
    for raw in raw_zones[1:]:
        official = out[-1]
        if raw == official:
            candidate = None
            candidate_count = 0
            out.append(official)
            continue
        if candidate == raw:
            candidate_count += 1
        else:
            candidate = raw
            candidate_count = 1
        if candidate_count >= k:
            out.append(raw)
            candidate = None
            candidate_count = 0
        else:
            out.append(official)
    return out


def per_zone_metrics(
    zones: Sequence[str],
    nifty_next_ret_pct: Sequence[float],
) -> pd.DataFrame:
    """Aggregate per-zone outcome stats.

    `nifty_next_ret_pct` is the next-trading-day NIFTY percent return aligned
    to `zones` (day t -> close[t+1] / close[t] - 1, in percent).

    Returns a DataFrame indexed by zone with columns:
      n, pct_of_days, mean_ret_pp, median_ret_pp, std_ret_pp,
      pct_up, pct_down, hypothesis_dir, hypothesis_acc_pct
    """
    if len(zones) != len(nifty_next_ret_pct):
        raise ValueError(
            f"zones and nifty_next_ret_pct length mismatch: "
            f"{len(zones)} vs {len(nifty_next_ret_pct)}"
        )
    df = pd.DataFrame({"zone": list(zones), "ret": list(nifty_next_ret_pct)})
    df = df.dropna(subset=["ret"])
    n_total = len(df)
    rows = []
    for z in ZONE_LABELS:
        sub = df[df["zone"] == z]
        n = int(len(sub))
        if n == 0:
            rows.append({
                "zone": z,
                "n": 0,
                "pct_of_days": 0.0,
                "mean_ret_pp": float("nan"),
                "median_ret_pp": float("nan"),
                "std_ret_pp": float("nan"),
                "pct_up": float("nan"),
                "pct_down": float("nan"),
                "hypothesis_dir": ZONE_DIRECTION_HYPOTHESIS[z],
                "hypothesis_acc_pct": float("nan"),
            })
            continue
        ret = sub["ret"].astype(float)
        pct_up = float((ret > 0).mean() * 100.0)
        pct_down = float((ret < 0).mean() * 100.0)
        hyp = ZONE_DIRECTION_HYPOTHESIS[z]
        if hyp == +1:
            hyp_acc = pct_up
        elif hyp == -1:
            hyp_acc = pct_down
        else:
            hyp_acc = float("nan")
        rows.append({
            "zone": z,
            "n": n,
            "pct_of_days": round(100.0 * n / n_total, 2) if n_total else 0.0,
            "mean_ret_pp": round(float(ret.mean()), 4),
            "median_ret_pp": round(float(ret.median()), 4),
            "std_ret_pp": round(float(ret.std(ddof=1)) if n >= 2 else float("nan"), 4),
            "pct_up": round(pct_up, 2),
            "pct_down": round(pct_down, 2),
            "hypothesis_dir": hyp,
            "hypothesis_acc_pct": round(hyp_acc, 2) if np.isfinite(hyp_acc) else float("nan"),
        })
    return pd.DataFrame(rows).set_index("zone")


def reconstruct_daily_signals(
    per_window_detail: Iterable[dict],
    features: pd.DataFrame,
    pred_offset_days: int = 5,
) -> pd.DataFrame:
    """Reproduce the per-day signal series for every OOS day across all windows.

    For each window with refit_anchor d_a and weight vector w, the OOS days
    are the next `pred_offset_days` *trading* dates in the feature index.
    Signal[d] = sum_k w[k] * features[d, k] using the column intersection
    between w and features (any feature missing from w is treated as zero
    weight, and any feature missing from features will raise).

    Returns a DataFrame indexed by date (DatetimeIndex) with columns:
      window_id, refit_anchor, signal
    The same date may appear in multiple windows if their OOS spans overlap;
    the *latest* window with that date wins (production behavior is to use
    the most recent refit's signal).
    """
    if not isinstance(features.index, pd.DatetimeIndex):
        raise ValueError("features must be DatetimeIndex")
    feat_cols = list(features.columns)
    feat_arr = features.to_numpy(dtype=float)
    feat_index = features.index
    feat_pos = {d: i for i, d in enumerate(feat_index)}
    rows: list[dict] = []
    for w in per_window_detail:
        anchor_str = w["refit_anchor"]
        anchor = pd.Timestamp(anchor_str)
        weights = w["weights"]
        # Build aligned weight vector in feature column order
        wvec = np.array([weights.get(c, 0.0) for c in feat_cols], dtype=float)
        # OOS = next trading days *strictly after* anchor in the feature index
        if anchor not in feat_pos:
            # Anchor must align to a feature date; fall back to the next
            # feature date >= anchor (rare; happens if anchor is a non-trading
            # day in the panel calendar)
            after = feat_index[feat_index >= anchor]
            if len(after) == 0:
                continue
            anchor_pos = feat_pos[after[0]]
        else:
            anchor_pos = feat_pos[anchor]
        end_pos = min(anchor_pos + pred_offset_days, len(feat_index) - 1)
        for pos in range(anchor_pos + 1, end_pos + 1):
            d = feat_index[pos]
            sig = float(feat_arr[pos] @ wvec)
            rows.append({
                "date": d,
                "window_id": w["refit_id"],
                "refit_anchor": anchor,
                "signal": sig,
            })
    if not rows:
        raise ValueError("no OOS rows reconstructed; check window anchors vs feature index")
    out = pd.DataFrame(rows).sort_values(["date", "window_id"])
    out = out.drop_duplicates("date", keep="last").set_index("date").sort_index()
    return out


def per_window_zone_thresholds(
    per_window_detail: Iterable[dict],
    features: pd.DataFrame,
    lookback_days: int,
) -> dict[int, tuple[float, float]]:
    """Re-derive (center, band) per window from the in-sample signal mean / std.

    No look-ahead: for each window with anchor d_a, we use only the
    `lookback_days` trading days strictly before d_a. center = mean(in_sample
    signals), band = std(in_sample signals). Mirrors the calm-zone calibration
    in `etf_v3_curated_reoptimize` but per-window so each OOS day's
    classification uses thresholds derivable at refit time.
    """
    feat_cols = list(features.columns)
    feat_arr = features.to_numpy(dtype=float)
    feat_index = features.index
    feat_pos = {d: i for i, d in enumerate(feat_index)}
    out: dict[int, tuple[float, float]] = {}
    for w in per_window_detail:
        anchor = pd.Timestamp(w["refit_anchor"])
        wvec = np.array([w["weights"].get(c, 0.0) for c in feat_cols], dtype=float)
        if anchor not in feat_pos:
            after = feat_index[feat_index >= anchor]
            if len(after) == 0:
                continue
            anchor_pos = feat_pos[after[0]]
        else:
            anchor_pos = feat_pos[anchor]
        lo = max(0, anchor_pos - lookback_days)
        hi = anchor_pos  # exclusive of anchor itself
        if hi - lo < 30:
            raise ValueError(
                f"window {w['refit_id']} has only {hi - lo} in-sample obs; need >=30"
            )
        signals = feat_arr[lo:hi] @ wvec
        center = float(np.mean(signals))
        band = float(np.std(signals, ddof=1))
        if not np.isfinite(center) or not np.isfinite(band) or band <= 0:
            raise ValueError(
                f"window {w['refit_id']} invalid thresholds: center={center} band={band}"
            )
        out[int(w["refit_id"])] = (center, band)
    return out


def classify_with_per_window_thresholds(
    daily_signals: pd.DataFrame,
    thresholds: dict[int, tuple[float, float]],
) -> pd.Series:
    """Apply each window's own thresholds to its OOS days; return zone series."""
    zones = []
    for d, row in daily_signals.iterrows():
        wid = int(row["window_id"])
        center, band = thresholds[wid]
        zones.append(signal_to_zone(float(row["signal"]), center, band))
    return pd.Series(zones, index=daily_signals.index, name="raw_zone")


# ---------------------------------------------------------------------------
# Test 1 driver
# ---------------------------------------------------------------------------


@dataclass
class Test1Result:
    n_oos_days: int
    n_unique_zones: int
    zone_distribution: dict[str, int]
    per_zone_table: pd.DataFrame
    raw_zone_series: pd.Series = field(repr=False)
    official_zone_series: pd.Series = field(repr=False)
    nifty_next_ret_pct: pd.Series = field(repr=False)
    summary_md: str = field(repr=False)

    def to_report_dict(self) -> dict:
        return {
            "n_oos_days": self.n_oos_days,
            "n_unique_zones": self.n_unique_zones,
            "zone_distribution": self.zone_distribution,
            "per_zone_table": self.per_zone_table.reset_index().to_dict(orient="records"),
        }


def run_test_1(
    rolling_refit_path: Path,
    lookback_days: int,
    pred_offset_days: int = 5,
    hysteresis_k: int = 2,
) -> Test1Result:
    """End-to-end Test 1 -- daily regime classification accuracy.

    Lazy imports the panel + features builders so the pure helpers above can
    be unit-tested without the heavy data-loader stack.
    """
    from pipeline.autoresearch.etf_v3_loader import CURATED_FOREIGN_ETFS, build_panel
    from pipeline.autoresearch.etf_v3_research import build_features

    rolling_refit_path = Path(rolling_refit_path)
    refit = json.loads(rolling_refit_path.read_text(encoding="utf-8"))
    pwd = refit["per_window_detail"]
    if not pwd:
        raise ValueError("rolling_refit.json has empty per_window_detail")

    panel = build_panel(t1_anchor=True)
    feats = build_features(panel, foreign_cols=list(CURATED_FOREIGN_ETFS)).dropna()

    # NIFTY next-day percent return aligned to feature index (decision day = t,
    # outcome = close[t+1] / close[t] - 1, in percent). The panel is
    # T-1 anchored so we use the un-shifted nifty close to compute the next-day
    # change of the *decision* day, which is panel index + 1 in raw calendar.
    nifty_close = panel["nifty_close"].astype(float)
    nifty_next_ret = (nifty_close.shift(-1) / nifty_close - 1.0) * 100.0
    nifty_next_ret = nifty_next_ret.reindex(feats.index)

    daily_signals = reconstruct_daily_signals(
        pwd, feats, pred_offset_days=pred_offset_days
    )
    thresholds = per_window_zone_thresholds(pwd, feats, lookback_days=lookback_days)
    raw_zones = classify_with_per_window_thresholds(daily_signals, thresholds)
    official_list = apply_hysteresis(list(raw_zones.values), k=hysteresis_k)
    official_zones = pd.Series(official_list, index=raw_zones.index, name="official_zone")

    aligned_ret = nifty_next_ret.reindex(official_zones.index)
    table = per_zone_metrics(list(official_zones.values), list(aligned_ret.values))

    dist_official = official_zones.value_counts().to_dict()
    dist_int = {z: int(dist_official.get(z, 0)) for z in ZONE_LABELS}

    md_lines = [
        "# Test 1 -- Daily regime classification accuracy",
        "",
        f"Source: `{rolling_refit_path}`",
        f"OOS days: **{len(official_zones)}**  |  unique zones seen: "
        f"**{sum(1 for v in dist_int.values() if v > 0)} / 5**  "
        f"|  hysteresis k={hysteresis_k}  |  lookback={lookback_days}d",
        "",
        "## Zone distribution (official, post-hysteresis)",
        "",
        "| Zone | n | pct |",
        "|---|---:|---:|",
    ]
    n_total = len(official_zones)
    for z in ZONE_LABELS:
        n = dist_int[z]
        pct = (100.0 * n / n_total) if n_total else 0.0
        md_lines.append(f"| {z} | {n} | {pct:.1f}% |")
    md_lines += [
        "",
        "## Per-zone NIFTY next-day outcome",
        "",
        "Hypothesis direction: +1 expect up, -1 expect down, 0 = no directional view.",
        "Hypothesis accuracy = pct_up if +1, pct_down if -1, NaN if 0.",
        "",
        "| Zone | n | mean ret pp | median ret pp | pct up | pct down | hyp dir | hyp acc % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for z in ZONE_LABELS:
        if z not in table.index:
            continue
        r = table.loc[z]
        n = int(r["n"])
        mean_pp = r["mean_ret_pp"]
        med_pp = r["median_ret_pp"]
        pu = r["pct_up"]
        pd_ = r["pct_down"]
        hyp = int(r["hypothesis_dir"])
        ha = r["hypothesis_acc_pct"]
        if n == 0:
            md_lines.append(
                f"| {z} | 0 | -- | -- | -- | -- | {hyp:+d} | -- |"
            )
        else:
            md_lines.append(
                f"| {z} | {n} | {mean_pp:+.4f} | {med_pp:+.4f} | "
                f"{pu:.1f}% | {pd_:.1f}% | {hyp:+d} | "
                f"{('--' if not np.isfinite(ha) else f'{ha:.1f}%')} |"
            )
    md_lines += [
        "",
        "## Interpretation",
        "",
        "Test 1 PASSES if (a) NEUTRAL captures roughly 60-80 percent of days, ",
        "(b) RISK-ON shows pct_up > 55 percent OR EUPHORIA shows pct_down > 55 percent, ",
        "(c) RISK-OFF / CAUTION show pct_down > 55 percent. ",
        "Test 1 FAILS if every directional zone hovers near 50 percent -- in that case ",
        "the regime label has no information about NIFTY direction and Tests 2-4 are moot.",
    ]
    summary_md = "\n".join(md_lines)

    return Test1Result(
        n_oos_days=len(official_zones),
        n_unique_zones=sum(1 for v in dist_int.values() if v > 0),
        zone_distribution=dist_int,
        per_zone_table=table,
        raw_zone_series=raw_zones,
        official_zone_series=official_zones,
        nifty_next_ret_pct=aligned_ret,
        summary_md=summary_md,
    )


def write_test_1_report(result: Test1Result, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test_1_regime_classification.md").write_text(result.summary_md, encoding="utf-8")
    (out_dir / "test_1_per_zone_table.csv").write_text(
        result.per_zone_table.reset_index().to_csv(index=False), encoding="utf-8"
    )
    (out_dir / "test_1_raw_zones.csv").write_text(
        pd.DataFrame({
            "date": result.raw_zone_series.index,
            "raw_zone": result.raw_zone_series.values,
            "official_zone": result.official_zone_series.values,
            "nifty_next_ret_pct": result.nifty_next_ret_pct.values,
        }).to_csv(index=False),
        encoding="utf-8",
    )
    (out_dir / "test_1_summary.json").write_text(
        json.dumps(result.to_report_dict(), indent=2, default=str), encoding="utf-8"
    )
    return out_dir / "test_1_regime_classification.md"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Phase 2 regime evaluation -- Test 1")
    p.add_argument("--rolling-refit", required=True, type=Path)
    p.add_argument("--lookback-days", type=int, default=756)
    p.add_argument("--pred-offset-days", type=int, default=5)
    p.add_argument("--hysteresis-k", type=int, default=2)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    r = run_test_1(
        rolling_refit_path=args.rolling_refit,
        lookback_days=args.lookback_days,
        pred_offset_days=args.pred_offset_days,
        hysteresis_k=args.hysteresis_k,
    )
    md_path = write_test_1_report(r, args.out_dir)
    print(f"Test 1 complete: {md_path}")
    print(f"  n_oos_days={r.n_oos_days}  unique_zones_seen={r.n_unique_zones}")
    print(f"  zone_distribution={r.zone_distribution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
