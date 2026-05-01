"""Qualifier diagnostic — gate-of-investment for the path-(a) Karpathy build.

Joins explorer_trades.csv (entry features) with horizon_trades.csv filtered
to (variant=VWAP_TOUCH, horizon_D=0) so we evaluate features against the
RIGHT exit family — the VWAP-touch / force-close logic that produced the
+46 bps gross / 0.42 Sharpe net touched arm — not the original ATR-stopped
exit.

Asks: do any pre-entry features have univariate predictive power on the
new exit's bps_gross AND on the binary touch outcome (touched vs not)?

If max |correlation| < 0.05 across all features for both targets, the
family is dead — no multi-feature qualifier can rescue it. Pivot to path
(b) options leverage or path (c) spec amendment.

If max |correlation| in 0.05-0.15, marginal — focused 2-3 feature gate.

If > 0.15, full walk-forward Karpathy is justified.

Outputs printed to stdout; no files written. ~60s runtime.
"""
from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRADES_CSV = HERE / "explorer_trades.csv"
HORIZON_CSV = HERE / "horizon_trades.csv"

NUMERIC_FEATURES = ("vwap_dev_z", "hour_balance_dev_z", "range_pctile", "atr_14")


def _parse_float(s: str) -> float | None:
    try:
        v = float(s)
        if v != v:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _minutes_since_open(snap_t: str) -> float:
    h, m, *_ = snap_t.split(":")
    return (int(h) - 9) * 60 + int(m) - 15


def _day_of_week(date_str: str) -> int:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday()


def main() -> None:
    horizon_d0_pnl = {}
    horizon_d0_outcome = {}
    with HORIZON_CSV.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get("variant") != "VWAP_TOUCH":
                continue
            try:
                if int(r.get("horizon_D", "-1")) != 0:
                    continue
            except ValueError:
                continue
            key = (r["date"], r["snap_t"], r["ticker"], r["side"])
            bps = _parse_float(r.get("bps_gross", ""))
            if bps is None:
                continue
            horizon_d0_pnl[key] = bps
            horizon_d0_outcome[key] = 1 if r["outcome"] == "VWAP_TOUCH" else 0
    print(f"horizon CSV loaded: {len(horizon_d0_pnl)} D0 VWAP_TOUCH rows")

    rows = []
    matched = 0
    with TRADES_CSV.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            key = (r["date"], r["snap_t"], r["ticker"], r["side"])
            if key not in horizon_d0_pnl:
                continue
            features = {}
            ok = True
            for f in NUMERIC_FEATURES:
                v = _parse_float(r.get(f, ""))
                if v is None:
                    ok = False
                    break
                features[f] = v
            if not ok:
                continue
            features["pnl_bps_gross"] = horizon_d0_pnl[key]
            features["touched"] = horizon_d0_outcome[key]
            features["abs_vwap_dev_z"] = abs(features["vwap_dev_z"])
            features["abs_hour_balance_dev_z"] = abs(features["hour_balance_dev_z"])
            features["zscore_product_signed"] = (
                features["vwap_dev_z"] * features["hour_balance_dev_z"]
            )
            features["zscore_product_abs"] = abs(features["zscore_product_signed"])
            features["vwap_dev_over_atr"] = (
                features["vwap_dev_z"] / features["atr_14"]
                if features["atr_14"] > 0
                else 0.0
            )
            features["abs_vwap_over_atr"] = abs(features["vwap_dev_over_atr"])
            features["minutes_since_open"] = _minutes_since_open(r["snap_t"])
            features["day_of_week"] = _day_of_week(r["date"])
            features["sector"] = r.get("sector", "")
            features["side"] = r.get("side", "")
            features["date"] = r["date"]
            features["snap_t"] = r["snap_t"]
            rows.append(features)
            matched += 1
    print(f"explorer trades joined to horizon: {matched} rows matched")

    if not rows:
        return

    pnls = [r["pnl_bps_gross"] for r in rows]
    touched = [r["touched"] for r in rows]
    n_touched = sum(touched)
    print(f"\nfull sample VWAP-touch exit pnl_bps_gross: mean={statistics.mean(pnls):.2f}, "
          f"stdev={statistics.pstdev(pnls):.2f}, "
          f"hit={sum(1 for v in pnls if v > 0)/len(pnls):.3f}")
    print(f"touched: {n_touched}/{len(rows)} ({n_touched/len(rows):.3f})")

    feature_names = [
        "vwap_dev_z",
        "hour_balance_dev_z",
        "range_pctile",
        "atr_14",
        "abs_vwap_dev_z",
        "abs_hour_balance_dev_z",
        "zscore_product_signed",
        "zscore_product_abs",
        "vwap_dev_over_atr",
        "abs_vwap_over_atr",
        "minutes_since_open",
        "day_of_week",
    ]

    print("\n--- univariate Pearson correlation: P&L bps gross (full sample, VWAP-touch exit) ---")
    corrs_pnl = []
    for name in feature_names:
        xs = [r[name] for r in rows]
        c = _pearson(xs, pnls)
        corrs_pnl.append((name, c))
    corrs_pnl.sort(key=lambda x: abs(x[1]), reverse=True)
    for name, c in corrs_pnl:
        marker = "  ***" if abs(c) > 0.15 else ("  *" if abs(c) > 0.05 else "")
        print(f"  {name:30s} {c:+.4f}{marker}")

    print("\n--- univariate Pearson correlation: TOUCHED (binary 0/1) ---")
    corrs_touched = []
    for name in feature_names:
        xs = [r[name] for r in rows]
        c = _pearson(xs, [float(t) for t in touched])
        corrs_touched.append((name, c))
    corrs_touched.sort(key=lambda x: abs(x[1]), reverse=True)
    for name, c in corrs_touched:
        marker = "  ***" if abs(c) > 0.15 else ("  *" if abs(c) > 0.05 else "")
        print(f"  {name:30s} {c:+.4f}{marker}")

    touched_rows = [r for r in rows if r["touched"] == 1]
    if touched_rows:
        touched_pnls = [r["pnl_bps_gross"] for r in touched_rows]
        print(f"\n--- univariate Pearson correlation: P&L bps gross WITHIN touched arm (n={len(touched_rows)}) ---")
        print(f"    touched arm pnl: mean={statistics.mean(touched_pnls):+.2f} bps, "
              f"stdev={statistics.pstdev(touched_pnls):.2f}, "
              f"hit={sum(1 for v in touched_pnls if v > 0)/len(touched_pnls):.3f}")
        corrs_touched_pnl = []
        for name in feature_names:
            xs = [r[name] for r in touched_rows]
            c = _pearson(xs, touched_pnls)
            corrs_touched_pnl.append((name, c))
        corrs_touched_pnl.sort(key=lambda x: abs(x[1]), reverse=True)
        for name, c in corrs_touched_pnl:
            marker = "  ***" if abs(c) > 0.15 else ("  *" if abs(c) > 0.05 else "")
            print(f"  {name:30s} {c:+.4f}{marker}")

    print("\n--- train (2021-05 to 2023-10) // test (2023-11 to 2024-04) walk-forward ---")
    train_rows = [r for r in rows if r["date"] < "2023-11-01"]
    test_rows = [r for r in rows if r["date"] >= "2023-11-01"]
    print(f"  train n={len(train_rows)}, test n={len(test_rows)}")
    if test_rows:
        train_pnls = [r["pnl_bps_gross"] for r in train_rows]
        test_pnls = [r["pnl_bps_gross"] for r in test_rows]
        print(f"  train pnl: mean={statistics.mean(train_pnls):+.2f} bps, "
              f"hit={sum(1 for v in train_pnls if v > 0)/len(train_pnls):.3f}")
        print(f"  test  pnl: mean={statistics.mean(test_pnls):+.2f} bps, "
              f"hit={sum(1 for v in test_pnls if v > 0)/len(test_pnls):.3f}")

        print("\n  univariate train-test stability (top 6 by |train corr| on TOUCH binary):")
        train_corrs = []
        train_touched = [float(r["touched"]) for r in train_rows]
        for name in feature_names:
            xs = [r[name] for r in train_rows]
            c = _pearson(xs, train_touched)
            train_corrs.append((name, c))
        train_corrs.sort(key=lambda x: abs(x[1]), reverse=True)
        test_touched = [float(r["touched"]) for r in test_rows]
        print(f"    {'feature':30s} {'train_r':>10s} {'test_r':>10s} {'sign_match':>12s}")
        for name, train_c in train_corrs[:6]:
            xs_test = [r[name] for r in test_rows]
            test_c = _pearson(xs_test, test_touched)
            match = "yes" if (train_c >= 0) == (test_c >= 0) else "FLIP"
            print(f"    {name:30s} {train_c:+10.4f} {test_c:+10.4f} {match:>12s}")

    print("\n--- categorical features: mean pnl by group (n>=20) ---")
    for cat_name in ("sector", "side"):
        groups = defaultdict(list)
        for r in rows:
            groups[r[cat_name]].append(r["pnl_bps_gross"])
        print(f"  by {cat_name}:")
        for g, vs in sorted(groups.items(), key=lambda kv: statistics.mean(kv[1]) if len(kv[1]) >= 20 else -999, reverse=True):
            if len(vs) < 20:
                continue
            mu = statistics.mean(vs)
            hit = sum(1 for v in vs if v > 0) / len(vs)
            sd = statistics.pstdev(vs) if len(vs) > 1 else 0.0
            sharpe = mu / sd if sd > 0 else 0.0
            print(f"    {g:25s} n={len(vs):4d}  mean={mu:+7.2f}  hit={hit:.3f}  sharpe_pt={sharpe:+.4f}")

    print("\n=== verdict ===")
    max_abs_corr_pnl = max(abs(c) for _, c in corrs_pnl)
    max_abs_corr_touch = max(abs(c) for _, c in corrs_touched)
    max_abs_corr_within_touch = (
        max(abs(c) for _, c in corrs_touched_pnl) if touched_rows else 0.0
    )
    print(f"  max |corr| vs P&L (full):           {max_abs_corr_pnl:.4f}")
    print(f"  max |corr| vs TOUCH binary:         {max_abs_corr_touch:.4f}")
    print(f"  max |corr| vs P&L within touched:   {max_abs_corr_within_touch:.4f}")
    best = max(max_abs_corr_pnl, max_abs_corr_touch, max_abs_corr_within_touch)
    if best < 0.05:
        print("\n  FAMILY DEAD. No qualifier can rescue — every feature is below 5%")
        print("  correlation on every target. Pivot to options or spec amendment.")
    elif best < 0.15:
        print("\n  MARGINAL. A focused 2-3 feature gate may produce small lift.")
        print("  Decide whether marginal lift can plausibly clear +25 bps net.")
    else:
        print("\n  SIGNAL PRESENT. Full walk-forward Karpathy is justified.")


if __name__ == "__main__":
    main()
