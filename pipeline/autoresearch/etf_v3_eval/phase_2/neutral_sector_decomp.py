"""Phase 2 NEUTRAL-day sector decomposition.

Test 1 showed NEUTRAL is the dominant zone (412 of 493 OOS days = 83.8 percent).
The user's catalog notes that on NEUTRAL days, *short-fades* in
PSU BANK / BANKPSE / ENERGY / INFRA worked while AUTO / IT / FMCG lost.
This module evaluates that claim directly:

  - For each NEUTRAL day d (from Test 1's official_zone series), compute the
    next-day percent return for each of the 10 NSE sectoral indices.
  - Aggregate per-sector: mean, median, pct_up, pct_down, IR.
  - Group sectors into the catalog buckets (fadeable shorts vs lossy shorts).
  - Test the directional asymmetry: do PSU BANK / ENERGY have negative mean
    while AUTO / IT / FMCG have non-negative mean on NEUTRAL days.

Output is descriptive, not strategy P&L. The full ZCROSS / sector_overlay /
coef_delta_marker overlay engine the user asked for is the next module after
this one establishes whether the per-sector NEUTRAL-day asymmetry exists at
all on this 412-day sample.

Sectoral index proxies:
  PSU BANK / BANKPSE -> NIFTYPSUBANK
  ENERGY            -> NIFTYENERGY
  INFRA             -> no direct NIFTYINFRA in the dataset; reported as
                       MISSING and excluded from the catalog bucket.
  AUTO              -> NIFTYAUTO
  IT                -> NIFTYIT
  FMCG              -> NIFTYFMCG
  (PHARMA / METAL / MEDIA / REALTY / BANKNIFTY also reported individually.)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Map our internal label -> on-disk CSV stem
SECTOR_CSV_MAP = {
    "BANKNIFTY":   "BANKNIFTY_daily.csv",
    "NIFTYAUTO":   "NIFTYAUTO_daily.csv",
    "NIFTYENERGY": "NIFTYENERGY_daily.csv",
    "NIFTYFMCG":   "NIFTYFMCG_daily.csv",
    "NIFTYIT":     "NIFTYIT_daily.csv",
    "NIFTYMEDIA":  "NIFTYMEDIA_daily.csv",
    "NIFTYMETAL":  "NIFTYMETAL_daily.csv",
    "NIFTYPHARMA": "NIFTYPHARMA_daily.csv",
    "NIFTYPSUBANK":"NIFTYPSUBANK_daily.csv",
    "NIFTYREALTY": "NIFTYREALTY_daily.csv",
}

# Catalog buckets per the user's "NEUTRAL-day short-fades worked / lost" claim.
# Sectors marked MISSING are reported separately so the bucket aggregate is
# honest about which proxies were actually available.
FADE_HYPOTHESIS_BUCKETS = {
    "fade_works":   ["NIFTYPSUBANK", "NIFTYENERGY"],   # INFRA missing
    "fade_loses":   ["NIFTYAUTO", "NIFTYIT", "NIFTYFMCG"],
    "neutral_set":  ["BANKNIFTY", "NIFTYMETAL", "NIFTYPHARMA", "NIFTYMEDIA", "NIFTYREALTY"],
}
MISSING_PROXIES = ["INFRA"]  # no NIFTYINFRA index in the dataset


def load_sector_panel(sector_dir: Path) -> pd.DataFrame:
    """Load all 10 sectoral indices into a single date-indexed close-price DF."""
    sector_dir = Path(sector_dir)
    frames = {}
    for label, fname in SECTOR_CSV_MAP.items():
        path = sector_dir / fname
        if not path.is_file():
            raise FileNotFoundError(f"missing sectoral CSV: {path}")
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        if "close" not in df.columns:
            raise ValueError(f"{path} missing 'close' column; got {list(df.columns)}")
        frames[label] = df["close"].astype(float)
    panel = pd.DataFrame(frames).sort_index()
    return panel


def next_day_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute per-column next-day percent return aligned to decision day."""
    return (panel.shift(-1) / panel - 1.0) * 100.0


def per_sector_metrics(
    sector_returns: pd.DataFrame,
    neutral_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Aggregate per-sector outcome stats restricted to NEUTRAL days."""
    sub = sector_returns.reindex(neutral_dates).dropna(how="all")
    rows = []
    for col in sector_returns.columns:
        s = sub[col].dropna()
        n = int(len(s))
        if n == 0:
            rows.append({
                "sector": col, "n": 0,
                "mean_pp": float("nan"), "median_pp": float("nan"),
                "std_pp": float("nan"), "pct_up": float("nan"),
                "pct_down": float("nan"), "IR_per_day": float("nan"),
                "fade_short_pp": float("nan"),
            })
            continue
        mean = float(s.mean())
        std = float(s.std(ddof=1)) if n >= 2 else float("nan")
        rows.append({
            "sector": col,
            "n": n,
            "mean_pp": round(mean, 4),
            "median_pp": round(float(s.median()), 4),
            "std_pp": round(std, 4) if np.isfinite(std) else float("nan"),
            "pct_up": round(float((s > 0).mean() * 100.0), 2),
            "pct_down": round(float((s < 0).mean() * 100.0), 2),
            "IR_per_day": round(mean / std, 4) if std and np.isfinite(std) and std > 0 else float("nan"),
            # "fade_short" = profit from shorting at decision close, covering
            # at next-day close. Equals -mean.
            "fade_short_pp": round(-mean, 4),
        })
    return pd.DataFrame(rows).set_index("sector")


def bucket_table(per_sector: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-bucket means + IR using equal-weighted average of sector means."""
    rows = []
    for bucket, sectors in FADE_HYPOTHESIS_BUCKETS.items():
        present = [s for s in sectors if s in per_sector.index and per_sector.loc[s, "n"] > 0]
        if not present:
            rows.append({
                "bucket": bucket, "n_sectors": 0, "sectors": "",
                "mean_pp": float("nan"), "fade_short_pp": float("nan"),
                "pct_up_avg": float("nan"),
            })
            continue
        sub = per_sector.loc[present]
        rows.append({
            "bucket": bucket,
            "n_sectors": len(present),
            "sectors": ",".join(present),
            "mean_pp": round(float(sub["mean_pp"].mean()), 4),
            "fade_short_pp": round(-float(sub["mean_pp"].mean()), 4),
            "pct_up_avg": round(float(sub["pct_up"].mean()), 2),
        })
    return pd.DataFrame(rows).set_index("bucket")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class NeutralSectorResult:
    n_neutral_days: int
    per_sector: pd.DataFrame
    buckets: pd.DataFrame
    missing_proxies: list[str]
    summary_md: str = field(repr=False)


def run_neutral_sector_decomp(
    test_1_zones_csv: Path,
    sector_dir: Path,
) -> NeutralSectorResult:
    test_1_zones_csv = Path(test_1_zones_csv)
    df = pd.read_csv(test_1_zones_csv, parse_dates=["date"])
    neutral_dates = df.loc[df["official_zone"] == "NEUTRAL", "date"]
    if neutral_dates.empty:
        raise ValueError(f"no NEUTRAL days found in {test_1_zones_csv}")
    neutral_idx = pd.DatetimeIndex(neutral_dates.values)

    panel = load_sector_panel(sector_dir)
    rets = next_day_returns(panel)
    per = per_sector_metrics(rets, neutral_idx)
    buckets = bucket_table(per)

    # Build the report
    lines = [
        "# Test 1 + NEUTRAL-day sector decomposition",
        "",
        f"NEUTRAL days from `{test_1_zones_csv}`: **{len(neutral_idx)}**",
        f"Sectoral indices source: `{sector_dir}`  ({len(SECTOR_CSV_MAP)} indices)",
        f"Missing proxies vs catalog: {', '.join(MISSING_PROXIES) or 'none'}",
        "",
        "## Per-sector NIFTY-style next-day return on NEUTRAL days",
        "",
        "Columns: `mean_pp` = mean next-day percent return when held LONG; ",
        "`fade_short_pp` = profit from a fade-short (covers at next close), equals `-mean_pp`. ",
        "`IR_per_day` = mean / std.",
        "",
        "| Sector | n | mean (pp) | median (pp) | std | pct up | pct down | IR/day | fade short pp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sec, r in per.iterrows():
        if int(r["n"]) == 0:
            lines.append(f"| {sec} | 0 | -- | -- | -- | -- | -- | -- | -- |")
            continue
        lines.append(
            f"| {sec} | {int(r['n'])} | {r['mean_pp']:+.4f} | {r['median_pp']:+.4f} | "
            f"{r['std_pp']:.4f} | {r['pct_up']:.1f}% | {r['pct_down']:.1f}% | "
            f"{r['IR_per_day']:+.4f} | {r['fade_short_pp']:+.4f} |"
        )
    lines += [
        "",
        "## Catalog hypothesis: NEUTRAL-day fade-shorts",
        "",
        "Catalog: PSU BANK / ENERGY / INFRA short-fades **worked**; ",
        "AUTO / IT / FMCG short-fades **lost**. ",
        "Bucket mean is the equal-weighted average of the per-sector mean returns. ",
        "`fade_short_pp` is the profit from fading SHORT (= -mean_pp). ",
        "Hypothesis confirmed if `fade_works` bucket has fade_short_pp > 0 ",
        "AND `fade_loses` bucket has fade_short_pp <= 0.",
        "",
        "| Bucket | n sectors | sectors | mean (pp) | fade short pp | avg pct up |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for bucket, r in buckets.iterrows():
        if int(r["n_sectors"]) == 0:
            lines.append(f"| {bucket} | 0 | -- | -- | -- | -- |")
            continue
        lines.append(
            f"| {bucket} | {int(r['n_sectors'])} | {r['sectors']} | "
            f"{r['mean_pp']:+.4f} | {r['fade_short_pp']:+.4f} | {r['pct_up_avg']:.1f}% |"
        )
    lines += [
        "",
        "## Verdict logic",
        "",
        "If `fade_works.fade_short_pp` > 0 AND `fade_loses.fade_short_pp` < 0 ",
        "AND the spread is at least 0.05pp/day (~12.5pp/yr), the catalog claim holds ",
        "on the smoke window and Test 2 should proceed to a full P&L backtest with ",
        "the ZCROSS / sector_overlay / coef_delta_marker stack restricted to the ",
        "fade_works sectors. Otherwise, the catalog claim is unsupported on this ",
        "sample and Tests 2-4 need a different cut.",
    ]
    summary_md = "\n".join(lines)

    return NeutralSectorResult(
        n_neutral_days=int(len(neutral_idx)),
        per_sector=per,
        buckets=buckets,
        missing_proxies=list(MISSING_PROXIES),
        summary_md=summary_md,
    )


def write_neutral_sector_report(result: NeutralSectorResult, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "test_1b_neutral_sector_decomp.md"
    md_path.write_text(result.summary_md, encoding="utf-8")
    result.per_sector.reset_index().to_csv(out_dir / "test_1b_per_sector.csv", index=False)
    result.buckets.reset_index().to_csv(out_dir / "test_1b_buckets.csv", index=False)
    (out_dir / "test_1b_summary.json").write_text(
        json.dumps({
            "n_neutral_days": result.n_neutral_days,
            "missing_proxies": result.missing_proxies,
            "per_sector": result.per_sector.reset_index().to_dict(orient="records"),
            "buckets": result.buckets.reset_index().to_dict(orient="records"),
        }, indent=2, default=str),
        encoding="utf-8",
    )
    return md_path


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="NEUTRAL-day sector decomposition")
    p.add_argument("--test-1-zones", required=True, type=Path,
                   help="path to Test 1 raw_zones CSV (date,raw_zone,official_zone,nifty_next_ret_pct)")
    p.add_argument("--sector-dir", type=Path,
                   default=Path("pipeline/data/sectoral_indices"))
    p.add_argument("--out-dir", required=True, type=Path)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    r = run_neutral_sector_decomp(args.test_1_zones, args.sector_dir)
    md = write_neutral_sector_report(r, args.out_dir)
    print(f"NEUTRAL sector decomp complete: {md}")
    print(f"  n_neutral_days={r.n_neutral_days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
