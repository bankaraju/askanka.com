"""Gap-and-fade diagnostic for the RISK-ON inversion.

After the alignment fix in regime_evaluation.py, RISK-ON still shows
70.4 percent down at n=27 (binomial p ~ 0.04). The user's working hypothesis:
overnight US strength gaps Indian markets up at open, then fades into
next-day close. Test: for each RISK-ON official day T, compute three legs:

  gap_pct        = (open[T+1] - close[T]) / close[T] * 100
  intraday_pct   = (close[T+1] - open[T+1]) / open[T+1] * 100
  c2c_pct        = (close[T+1] - close[T]) / close[T] * 100

Decision logic (from the user):
  - mean(gap) > 0  AND  mean(intraday) < 0  -> gap-and-fade is real,
    invert RISK-ON to a SHORT-fade signal at open.
  - mean(gap) < 0  -> RISK-ON predicts true India weakness regardless
    of horizon; inversion does not help, just skip.
  - mean(gap) ~ 0  -> noise, skip RISK-ON.

Same diagnostic also applied to the other 4 zones for context, so the
gap / intraday split for EUPHORIA / NEUTRAL / CAUTION / RISK-OFF is on the
record alongside RISK-ON.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ZONE_LABELS = ("EUPHORIA", "RISK-ON", "NEUTRAL", "CAUTION", "RISK-OFF")


def load_nifty_ohlc(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    needed = {"open", "close"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"NIFTY CSV missing columns: {missing}; got {list(df.columns)}")
    return df[["open", "close"]].astype(float)


def gap_fade_table(
    zone_csv: Path,
    nifty_ohlc: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-day-with-decomp DataFrame, per-zone-summary DataFrame)."""
    z = pd.read_csv(zone_csv, parse_dates=["date"]).sort_values("date")
    # `date` in zone CSV = panel index = decision day T (calendar).
    # Outcome window is the next trading day after T in the NIFTY calendar.
    # Build a date-aligned next-day open / close for each decision date.
    nifty_dates = nifty_ohlc.index
    rows = []
    for _, row in z.iterrows():
        T = row["date"]
        # Find decision close at T (NIFTY close on calendar T)
        if T not in nifty_dates:
            continue
        # Find next NIFTY trading day after T
        future = nifty_dates[nifty_dates > T]
        if len(future) == 0:
            continue
        next_day = future[0]
        close_T = float(nifty_ohlc.loc[T, "close"])
        open_next = float(nifty_ohlc.loc[next_day, "open"])
        close_next = float(nifty_ohlc.loc[next_day, "close"])
        if close_T == 0 or open_next == 0:
            continue
        gap_pct = (open_next - close_T) / close_T * 100.0
        intraday_pct = (close_next - open_next) / open_next * 100.0
        c2c_pct = (close_next - close_T) / close_T * 100.0
        rows.append({
            "decision_date": T,
            "outcome_date": next_day,
            "official_zone": row["official_zone"],
            "raw_zone": row.get("raw_zone", ""),
            "close_T": close_T,
            "open_next": open_next,
            "close_next": close_next,
            "gap_pct": round(gap_pct, 4),
            "intraday_pct": round(intraday_pct, 4),
            "c2c_pct": round(c2c_pct, 4),
        })
    per_day = pd.DataFrame(rows)
    if per_day.empty:
        raise ValueError("no rows in gap-fade decomposition; check date alignment")

    summary_rows = []
    for zone in ZONE_LABELS:
        sub = per_day[per_day["official_zone"] == zone]
        n = len(sub)
        if n == 0:
            summary_rows.append({"zone": zone, "n": 0,
                "gap_mean_pp": float("nan"), "gap_pct_pos": float("nan"),
                "intra_mean_pp": float("nan"), "intra_pct_neg": float("nan"),
                "c2c_mean_pp": float("nan"), "c2c_pct_neg": float("nan"),
                "verdict": "no data"})
            continue
        gm = float(sub["gap_pct"].mean())
        im = float(sub["intraday_pct"].mean())
        cm = float(sub["c2c_pct"].mean())
        gp = float((sub["gap_pct"] > 0).mean() * 100.0)
        in_ = float((sub["intraday_pct"] < 0).mean() * 100.0)
        cn = float((sub["c2c_pct"] < 0).mean() * 100.0)
        # Verdict only meaningful for RISK-ON / EUPHORIA test
        if gm > 0.05 and im < -0.05:
            v = "gap_and_fade"
        elif gm < -0.05:
            v = "true_weakness"
        elif abs(gm) <= 0.05 and abs(im) <= 0.05:
            v = "noise"
        else:
            v = "mixed"
        summary_rows.append({
            "zone": zone, "n": n,
            "gap_mean_pp": round(gm, 4),
            "gap_pct_pos": round(gp, 1),
            "intra_mean_pp": round(im, 4),
            "intra_pct_neg": round(in_, 1),
            "c2c_mean_pp": round(cm, 4),
            "c2c_pct_neg": round(cn, 1),
            "verdict": v,
        })
    summary = pd.DataFrame(summary_rows).set_index("zone")
    return per_day, summary


def write_report(per_day: pd.DataFrame, summary: pd.DataFrame, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_lines = [
        "# Gap-and-fade diagnostic on RISK-ON inversion",
        "",
        "Source: official-zone series from Test 1 (post-alignment-fix); ",
        "NIFTY OHLC from `pipeline/data/india_historical/indices/NIFTY_daily.csv`.",
        "",
        "## Decomposition rules",
        "",
        "For each decision day T:",
        "- gap_pct      = (open[T+1] - close[T]) / close[T] x 100",
        "- intraday_pct = (close[T+1] - open[T+1]) / open[T+1] x 100",
        "- c2c_pct      = (close[T+1] - close[T]) / close[T] x 100",
        "",
        "Gap-and-fade is confirmed if mean(gap) > 0 AND mean(intraday) < 0. ",
        "True weakness if mean(gap) < 0. ",
        "Noise if both means are within +/- 0.05 pp.",
        "",
        "## Per-zone decomposition",
        "",
        "| Zone | n | gap mean pp | gap pct >0 | intra mean pp | intra pct <0 | c2c mean pp | c2c pct <0 | verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for zone in ZONE_LABELS:
        if zone not in summary.index:
            continue
        r = summary.loc[zone]
        n = int(r["n"])
        if n == 0:
            md_lines.append(f"| {zone} | 0 | -- | -- | -- | -- | -- | -- | no data |")
            continue
        md_lines.append(
            f"| {zone} | {n} | {r['gap_mean_pp']:+.4f} | {r['gap_pct_pos']:.1f}% | "
            f"{r['intra_mean_pp']:+.4f} | {r['intra_pct_neg']:.1f}% | "
            f"{r['c2c_mean_pp']:+.4f} | {r['c2c_pct_neg']:.1f}% | {r['verdict']} |"
        )
    md_lines += [
        "",
        "## RISK-ON per-event detail (n=27)",
        "",
        "| decision date | outcome date | gap pp | intra pp | c2c pp |",
        "|---|---|---:|---:|---:|",
    ]
    ro = per_day[per_day["official_zone"] == "RISK-ON"].sort_values("decision_date")
    for _, r in ro.iterrows():
        md_lines.append(
            f"| {pd.Timestamp(r['decision_date']).date()} | "
            f"{pd.Timestamp(r['outcome_date']).date()} | "
            f"{r['gap_pct']:+.4f} | {r['intraday_pct']:+.4f} | {r['c2c_pct']:+.4f} |"
        )
    md_lines += [
        "",
        "## Decision logic",
        "",
        "Apply the verdict from the RISK-ON row:",
        "  - `gap_and_fade`   -> invert RISK-ON: SHORT at open[T+1], cover at close[T+1]",
        "                       (or skip if you want OOS confirmation first)",
        "  - `true_weakness`  -> RISK-ON correctly flags weakness; do not invert,",
        "                       just hold the original SHORT direction (matches catalog)",
        "  - `noise` / `mixed`-> skip RISK-ON, focus on 4 working regimes",
    ]
    md = "\n".join(md_lines)
    md_path = out_dir / "test_1c_gap_fade_diagnostic.md"
    md_path.write_text(md, encoding="utf-8")
    summary.reset_index().to_csv(out_dir / "test_1c_gap_fade_summary.csv", index=False)
    per_day.to_csv(out_dir / "test_1c_gap_fade_per_day.csv", index=False)
    return md_path


def _main() -> int:
    p = argparse.ArgumentParser(description="Gap-and-fade diagnostic")
    p.add_argument("--zones-csv", required=True, type=Path)
    p.add_argument("--nifty-ohlc", type=Path,
                   default=Path("pipeline/data/india_historical/indices/NIFTY_daily.csv"))
    p.add_argument("--out-dir", required=True, type=Path)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    nifty = load_nifty_ohlc(args.nifty_ohlc)
    per_day, summary = gap_fade_table(args.zones_csv, nifty)
    md = write_report(per_day, summary, args.out_dir)
    print(f"Gap-fade diagnostic complete: {md}")
    print()
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
