"""Residual-reversion backtest for Phase C overshoot breaks.

Hypothesis under test
---------------------
When a stock's daily return deviates by |zσ| from its sector-cohort mean
(residual = r_stock − r_cohort_mean), does the NEXT-day residual
mean-revert? Stratify by:
  * magnitude bucket (|z| ∈ [2,3), [3,4), [4,∞))
  * direction (overshoot UP vs DOWN)
  * broad sector
  * VIX-proxy regime (ETF-style: cross-sectional dispersion today)

Walk-forward
------------
Split 4-yr history into N contiguous folds; for each fold report hit rate
and mean next-day reversion. Also run a randomised permutation test
where we shuffle the (stock, date) → next_day_return mapping within each
fold to get a null distribution.

Data
----
  * pipeline/data/fno_historical/*.csv  — 5-yr daily OHLC per F&O ticker
  * opus/artifacts/*/indianapi_stock.json — ticker → industry

Outputs
-------
  * stdout table: hit rate + mean reversion by (σ-bucket × direction × sector)
  * pipeline/autoresearch/results/overshoot_reversion_<stamp>.json
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_FNO_DIR = _REPO / "pipeline" / "data" / "fno_historical"
_OPUS_DIR = _REPO / "opus" / "artifacts"
_RESULTS_DIR = _REPO / "pipeline" / "autoresearch" / "results"

# Fine industry → broad sector
BROAD_SECTOR = {
    "Software & Programming": "IT",
    "Computer Services": "IT",
    "Biotechnology & Drugs": "Pharma",
    "Healthcare Facilities": "Pharma",
    "Regional Banks": "Banks",
    "Consumer Financial Services": "NBFC",
    "Investment Services": "FinSvc",
    "Insurance (Life)": "Insurance",
    "Misc. Financial Services": "FinSvc",
    "Electric Utilities": "Utilities",
    "Oil & Gas Operations": "Energy",
    "Coal": "Energy",
    "Auto & Truck Manufacturers": "Autos",
    "Auto & Truck Parts": "Autos",
    "Iron & Steel": "Metals",
    "Metal Mining": "Metals",
    "Chemical Manufacturing": "Chemicals",
    "Construction Services": "Capital_Goods",
    "Misc. Capital Goods": "Capital_Goods",
    "Construction - Raw Materials": "Cement_Building",
    "Electronic Instr. & Controls": "Electrical",
    "Aerospace & Defense": "Defence",
    "Personal & Household Prods.": "FMCG",
    "Food Processing": "FMCG",
    "Recreational Products": "Consumer_Disc",
    "Misc. Fabricated Products": "Capital_Goods",
    "Misc. Transportation": "Logistics",
    "Fabricated Plastic & Rubber": "Chemicals",
    "Communications Services": "Telecom",
    "Retail (Specialty)": "Consumer_Disc",
    "Retail (Apparel)": "Consumer_Disc",
    "Media": "Media",
    "Hotels & Motels": "Consumer_Disc",
    "Restaurants": "Consumer_Disc",
    "Casinos & Gaming": "Consumer_Disc",
    "Tobacco": "FMCG",
    "Beverages (Non-Alcoholic)": "FMCG",
    "Real Estate Operations": "Real_Estate",
    "Airline": "Logistics",
    "Railroads": "Logistics",
    "Trucking": "Logistics",
    "": "Unmapped",
}

MIN_COHORT_SIZE = 4  # need ≥ 4 peers to call a cohort mean meaningful
ROLL_STD_WINDOW = 20  # days of residuals used to compute σ
SIGMA_BUCKETS = [(2.0, 3.0), (3.0, 4.0), (4.0, 99.0)]


def load_sector_map() -> dict[str, str]:
    """ticker → broad sector, collapsed from the fine indianapi industry."""
    mapping = {}
    for p in _OPUS_DIR.glob("*/indianapi_stock.json"):
        ticker = p.parent.name
        try:
            with p.open(encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        industry = (d.get("industry") or "").strip()
        mapping[ticker] = BROAD_SECTOR.get(industry, f"Other:{industry}" if industry else "Unmapped")
    return mapping


def load_price_panel(tickers: Iterable[str]) -> pd.DataFrame:
    """Wide frame: rows = dates, cols = tickers, values = close."""
    series = {}
    for t in tickers:
        p = _FNO_DIR / f"{t}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["Date"])
        df = df.sort_values("Date").drop_duplicates("Date", keep="last").set_index("Date")
        series[t] = df["Close"]
    return pd.concat(series, axis=1).sort_index()


def compute_residuals(
    closes: pd.DataFrame,
    sector_of: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (returns, residuals, rolling_z) panels, all aligned on date×ticker."""
    rets = closes.pct_change() * 100  # percent daily return

    cohort_mean = pd.DataFrame(index=rets.index, columns=rets.columns, dtype=float)
    sectors = defaultdict(list)
    for t, s in sector_of.items():
        if t in rets.columns:
            sectors[s].append(t)

    for sec, members in sectors.items():
        if len(members) < MIN_COHORT_SIZE:
            continue
        sec_frame = rets[members]
        # leave-one-out mean so a stock doesn't get averaged against itself
        n = sec_frame.notna().sum(axis=1)
        total = sec_frame.sum(axis=1, min_count=MIN_COHORT_SIZE)
        for t in members:
            own = sec_frame[t]
            loo = (total - own.fillna(0)) / (n - own.notna().astype(int))
            # mask where there was no own-return today OR cohort too thin
            valid = own.notna() & (n - own.notna().astype(int) >= MIN_COHORT_SIZE - 1)
            cohort_mean.loc[valid, t] = loo.loc[valid]

    residual = rets - cohort_mean
    # trailing residual σ per ticker (lagged by 1 to avoid look-ahead)
    z = residual / residual.rolling(ROLL_STD_WINDOW, min_periods=10).std().shift(1)
    return rets, residual, z


def classify_events(
    returns: pd.DataFrame,
    residuals: pd.DataFrame,
    zs: pd.DataFrame,
) -> list[dict]:
    """Enumerate every (ticker, date) break ≥ 2σ. Attach next-day residual."""
    events = []
    dates = returns.index
    next_resid = residuals.shift(-1)
    next_ret = returns.shift(-1)

    for col in zs.columns:
        z_col = zs[col]
        hits = z_col[z_col.abs() >= 2.0].dropna()
        for dt, z in hits.items():
            r_next = next_resid.loc[dt, col] if dt in next_resid.index else None
            ret_next = next_ret.loc[dt, col] if dt in next_ret.index else None
            if pd.isna(r_next) or pd.isna(ret_next):
                continue
            events.append({
                "ticker": col,
                "date": dt.strftime("%Y-%m-%d"),
                "z": float(z),
                "today_resid": float(residuals.loc[dt, col]),
                "today_ret": float(returns.loc[dt, col]),
                "next_resid": float(r_next),
                "next_ret": float(ret_next),
            })
    return events


def sigma_bucket(z: float) -> str | None:
    az = abs(z)
    for lo, hi in SIGMA_BUCKETS:
        if lo <= az < hi:
            return f"{lo:.0f}-{hi:.0f}σ" if hi < 90 else f"{lo:.0f}σ+"
    return None


def summarise(
    events: list[dict],
    sector_of: dict[str, str],
    fold_label: str = "ALL",
) -> list[dict]:
    """Group by sector × σ-bucket × direction, report reversion stats."""
    rows = []
    groups = defaultdict(list)
    for ev in events:
        sec = sector_of.get(ev["ticker"], "Unmapped")
        bucket = sigma_bucket(ev["z"])
        if bucket is None:
            continue
        direction = "UP" if ev["z"] > 0 else "DOWN"
        groups[(sec, bucket, direction)].append(ev)
    for (sec, bucket, direction), evs in groups.items():
        next_resids = [e["next_resid"] for e in evs]
        # reversion = next-day residual opposite sign to today's overshoot residual
        if direction == "UP":
            wins = sum(1 for r in next_resids if r < 0)
        else:
            wins = sum(1 for r in next_resids if r > 0)
        n = len(evs)
        hit = wins / n
        mean_next = sum(next_resids) / n
        # "reversion" metric is signed so longs on UP overshoots are negative mean_next
        signed_reversion = (-1 if direction == "UP" else 1) * mean_next
        rows.append({
            "fold": fold_label,
            "sector": sec,
            "bucket": bucket,
            "direction": direction,
            "n": n,
            "hit_rate": round(hit, 3),
            "mean_next_resid_pct": round(mean_next, 3),
            "mean_reversion_pct": round(signed_reversion, 3),
        })
    rows.sort(key=lambda r: (r["sector"], r["bucket"], r["direction"]))
    return rows


def walk_forward_folds(events: list[dict], n_folds: int = 4) -> dict[str, list[dict]]:
    """Split events into n_folds chronological slices."""
    ordered = sorted(events, key=lambda e: e["date"])
    if not ordered:
        return {}
    dates = [e["date"] for e in ordered]
    first, last = dates[0], dates[-1]
    # slice by date quartile, not by event count, so each fold covers a
    # real calendar period (fair walk-forward).
    min_dt = datetime.fromisoformat(first)
    max_dt = datetime.fromisoformat(last)
    total_days = (max_dt - min_dt).days
    if total_days <= 0:
        return {"FOLD_0": ordered}
    folds: dict[str, list[dict]] = {}
    step = total_days / n_folds
    for i in range(n_folds):
        lo = min_dt.timestamp() + i * step * 86400
        hi = min_dt.timestamp() + (i + 1) * step * 86400
        label = f"FOLD_{i}"
        folds[label] = [
            e for e in ordered
            if lo <= datetime.fromisoformat(e["date"]).timestamp() <= hi
        ]
    return folds


def randomised_null(
    events: list[dict],
    sector_of: dict[str, str],
    n_shuffles: int = 200,
    seed: int = 42,
) -> dict[str, dict]:
    """Shuffle (event → next_resid) and measure how often the real mean-
    reversion exceeds the shuffled. Reports per-bucket one-sided p-value.
    """
    rng = random.Random(seed)
    real_rows = summarise(events, sector_of)
    baseline = {
        (r["sector"], r["bucket"], r["direction"]): r["mean_reversion_pct"]
        for r in real_rows
    }
    exceed = defaultdict(int)
    sample_sizes = defaultdict(lambda: 0)

    next_resids = [e["next_resid"] for e in events]
    for _ in range(n_shuffles):
        shuffled = list(next_resids)
        rng.shuffle(shuffled)
        fake = [dict(e, next_resid=shuffled[i]) for i, e in enumerate(events)]
        fake_rows = summarise(fake, sector_of)
        for r in fake_rows:
            key = (r["sector"], r["bucket"], r["direction"])
            if key in baseline and r["mean_reversion_pct"] >= baseline[key]:
                exceed[key] += 1
            sample_sizes[key] += 1

    pvals = {}
    for key, real_val in baseline.items():
        n = sample_sizes.get(key, 0)
        if n == 0:
            continue
        p = exceed[key] / n
        pvals[" | ".join(key)] = {
            "real_reversion_pct": real_val,
            "p_value_one_sided": round(p, 4),
            "n_shuffles": n,
        }
    return pvals


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    min_z = 2.0
    n_folds = 4
    n_shuffles = 200
    if "--folds" in argv:
        n_folds = int(argv[argv.index("--folds") + 1])
    if "--shuffles" in argv:
        n_shuffles = int(argv[argv.index("--shuffles") + 1])

    print("loading sector map...", flush=True)
    sector_of = load_sector_map()
    print(f"  {len(sector_of)} tickers mapped")

    print("loading price panel...", flush=True)
    closes = load_price_panel(sector_of.keys())
    print(f"  {closes.shape[0]} days x {closes.shape[1]} tickers "
          f"({closes.index.min().date()} → {closes.index.max().date()})")

    print("computing residuals + rolling z...", flush=True)
    rets, resids, zs = compute_residuals(closes, sector_of)
    n_events_2sigma = int((zs.abs() >= min_z).sum().sum())
    print(f"  raw ≥2σ events (before next-day filter): {n_events_2sigma}")

    print("classifying events...", flush=True)
    events = classify_events(rets, resids, zs)
    print(f"  events with valid next-day: {len(events)}")

    print("\n=== POOLED (all folds) ===")
    pooled_rows = summarise(events, sector_of, fold_label="ALL")
    _print_table(pooled_rows)

    print(f"\n=== WALK-FORWARD ({n_folds} folds) ===")
    folds = walk_forward_folds(events, n_folds=n_folds)
    fold_rows = []
    for label, ev_slice in folds.items():
        if not ev_slice:
            continue
        dates = [e["date"] for e in ev_slice]
        print(f"\n-- {label}  {dates[0]} → {dates[-1]}  n={len(ev_slice)}")
        rows = summarise(ev_slice, sector_of, fold_label=label)
        _print_table(rows, top=10)
        fold_rows.extend(rows)

    print(f"\n=== RANDOMISED NULL ({n_shuffles} shuffles) ===")
    pvals = randomised_null(events, sector_of, n_shuffles=n_shuffles)
    # show the most-significant buckets
    ranked = sorted(pvals.items(), key=lambda kv: kv[1]["p_value_one_sided"])
    print(f"{'group':<45} {'reversion%':>12} {'p-value':>10}")
    for key, v in ranked[:25]:
        print(f"{key:<45} {v['real_reversion_pct']:>12.3f} {v['p_value_one_sided']:>10.4f}")

    # persist
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = _RESULTS_DIR / f"overshoot_reversion_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "min_z": min_z,
            "n_folds": n_folds,
            "n_shuffles": n_shuffles,
            "roll_std_window": ROLL_STD_WINDOW,
            "min_cohort_size": MIN_COHORT_SIZE,
            "price_dates": [closes.index.min().strftime("%Y-%m-%d"),
                            closes.index.max().strftime("%Y-%m-%d")],
            "n_tickers": int(closes.shape[1]),
            "n_events_valid": len(events),
        },
        "pooled": pooled_rows,
        "folds": fold_rows,
        "randomised_null_top": ranked[:50],
    }
    with out.open("w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    print(f"\nSaved: {out.relative_to(_REPO)}")
    return 0


def _print_table(rows: list[dict], top: int | None = None) -> None:
    if not rows:
        print("  (empty)")
        return
    rows = sorted(rows, key=lambda r: (-r["n"], -abs(r["mean_reversion_pct"])))
    if top:
        rows = rows[:top]
    hdr = f"  {'sector':<16} {'bucket':<8} {'dir':<5} {'n':>5} {'hit%':>6} {'rev%':>8}"
    print(hdr)
    for r in rows:
        print(f"  {r['sector']:<16} {r['bucket']:<8} {r['direction']:<5} "
              f"{r['n']:>5} {r['hit_rate']*100:>5.1f} {r['mean_reversion_pct']:>8.3f}")


if __name__ == "__main__":
    raise SystemExit(main())
