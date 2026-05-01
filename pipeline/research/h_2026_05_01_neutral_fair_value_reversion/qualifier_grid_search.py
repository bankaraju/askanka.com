"""Qualifier grid search — exploration-grade test of whether a multi-feature
gate can lift unconditional mean above the +25 bps net spec threshold.

This is exploration, NOT registration. No BH-FDR, no permutation null. The
goal is to find the empirical ceiling on a multi-feature linear gate, then
inform whether a new hypothesis spec is worth writing.

Two passes:
  1. Single-feature percentile gates to confirm diagnostic findings on the
     joined dataset (entry features + VWAP-touch exit P&L)
  2. Two-feature combined gates over the top features, measuring OOS mean
     after walk-forward CV (train 2021-05 to 2023-04, test 2023-05 to
     2024-04)

For each gate we report n_selected, mean_bps_gross, mean_bps_net_s1,
hit rate, Sharpe per trade, and bootstrap 95% CI on OOS mean.

Decision rule:
  - If best 2-feature gate's OOS net mean lower CI ≥ 0 AND mean ≥ +5 bps
    net AND Sharpe per-trade ≥ 0.20 → spec design worth doing
  - Otherwise → family is dead, pivot to options leverage or kill
"""
from __future__ import annotations

import csv
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRADES_CSV = HERE / "explorer_trades.csv"
HORIZON_CSV = HERE / "horizon_trades.csv"
OUT_JSON = HERE / "qualifier_grid_summary.json"

NUMERIC_FEATURES = ("vwap_dev_z", "hour_balance_dev_z", "range_pctile", "atr_14")
COST_BPS_S1 = 30.0
TRAIN_END = "2023-05-01"
N_BOOTSTRAP = 2000
RANDOM_SEED = 20260501


def _parse_float(s: str) -> float | None:
    try:
        v = float(s)
        if v != v:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _minutes_since_open(snap_t: str) -> float:
    h, m, *_ = snap_t.split(":")
    return (int(h) - 9) * 60 + int(m) - 15


def _load_rows() -> list[dict]:
    horizon = {}
    with HORIZON_CSV.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
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
            horizon[key] = (bps, 1 if r["outcome"] == "VWAP_TOUCH" else 0)

    rows = []
    with TRADES_CSV.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["date"], r["snap_t"], r["ticker"], r["side"])
            if key not in horizon:
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
            bps, touched = horizon[key]
            features["pnl_bps_gross"] = bps
            features["touched"] = touched
            features["abs_vwap_dev_z"] = abs(features["vwap_dev_z"])
            features["abs_hour_balance_dev_z"] = abs(features["hour_balance_dev_z"])
            features["abs_vwap_over_atr"] = (
                abs(features["vwap_dev_z"] / features["atr_14"])
                if features["atr_14"] > 0 else 0.0
            )
            features["minutes_since_open"] = _minutes_since_open(r["snap_t"])
            features["sector"] = r.get("sector", "")
            features["side"] = r.get("side", "")
            features["date"] = r["date"]
            features["snap_t"] = r["snap_t"]
            rows.append(features)
    return rows


def _stats(rows: list[dict]) -> dict:
    if not rows:
        return dict(n=0)
    n = len(rows)
    gross = [r["pnl_bps_gross"] for r in rows]
    net = [v - COST_BPS_S1 for v in gross]
    mu_g = statistics.mean(gross)
    mu_n = statistics.mean(net)
    sd_g = statistics.pstdev(gross) if n > 1 else 0.0
    sd_n = statistics.pstdev(net) if n > 1 else 0.0
    sharpe_g = (mu_g / sd_g) if sd_g > 0 else 0.0
    sharpe_n = (mu_n / sd_n) if sd_n > 0 else 0.0
    return dict(
        n=n,
        mean_bps_gross=round(mu_g, 3),
        mean_bps_net_s1=round(mu_n, 3),
        hit_gross=round(sum(1 for v in gross if v > 0) / n, 4),
        hit_net=round(sum(1 for v in net if v > 0) / n, 4),
        sharpe_per_trade_gross=round(sharpe_g, 4),
        sharpe_per_trade_net_s1=round(sharpe_n, 4),
    )


def _bootstrap_ci_mean(values: list[float], iters: int, alpha: float = 0.05) -> tuple[float, float]:
    if len(values) < 5:
        return (float("nan"), float("nan"))
    rng = random.Random(RANDOM_SEED)
    n = len(values)
    means = []
    for _ in range(iters):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()
    lo_idx = max(0, int(iters * alpha / 2))
    hi_idx = min(iters - 1, int(iters * (1 - alpha / 2)))
    return (round(means[lo_idx], 3), round(means[hi_idx], 3))


def _percentile_thresholds(rows: list[dict], feature: str, deciles: tuple[int, ...]) -> list[float]:
    vals = sorted([r[feature] for r in rows])
    n = len(vals)
    return [vals[max(0, min(n - 1, int(n * d / 100)))] for d in deciles]


def _apply_gate(rows: list[dict], conditions: list[tuple[str, str, float]]) -> list[dict]:
    out = []
    for r in rows:
        ok = True
        for feature, op, threshold in conditions:
            v = r.get(feature)
            if v is None:
                ok = False
                break
            if op == "<=":
                if not (v <= threshold):
                    ok = False
                    break
            elif op == ">=":
                if not (v >= threshold):
                    ok = False
                    break
        if ok:
            out.append(r)
    return out


def _stats_with_ci(rows: list[dict], iters: int = N_BOOTSTRAP) -> dict:
    s = _stats(rows)
    if rows:
        net = [r["pnl_bps_gross"] - COST_BPS_S1 for r in rows]
        lo, hi = _bootstrap_ci_mean(net, iters)
        s["net_mean_ci_95"] = [lo, hi]
    return s


def main() -> None:
    rows = _load_rows()
    print(f"loaded {len(rows)} rows (joined trades + horizon D0 VWAP_TOUCH)")
    train = [r for r in rows if r["date"] < TRAIN_END]
    test = [r for r in rows if r["date"] >= TRAIN_END]
    print(f"train n={len(train)}, test n={len(test)}, baseline test net mean={_stats(test)['mean_bps_net_s1']}")
    print()

    summary = dict(
        baseline=dict(
            train=_stats(train),
            test=_stats_with_ci(test),
        ),
        single_feature_gates=[],
        two_feature_gates=[],
        meta=dict(
            n_total=len(rows),
            n_train=len(train),
            n_test=len(test),
            train_end=TRAIN_END,
            cost_bps_s1=COST_BPS_S1,
            n_bootstrap=N_BOOTSTRAP,
        ),
    )

    # ---- Pass 1: single-feature percentile gates ----
    single_feature_gates = []
    feature_directions = (
        ("minutes_since_open", "<="),
        ("abs_hour_balance_dev_z", ">="),
        ("range_pctile", "<="),
        ("abs_vwap_over_atr", "<="),
        ("atr_14", "<="),
        ("abs_vwap_dev_z", "<="),
    )
    deciles = (10, 20, 30, 40, 50, 60, 70, 80)
    for feature, op in feature_directions:
        train_thresholds = _percentile_thresholds(train, feature, deciles)
        for d, thr in zip(deciles, train_thresholds):
            train_subset = _apply_gate(train, [(feature, op, thr)])
            test_subset = _apply_gate(test, [(feature, op, thr)])
            if not train_subset or not test_subset or len(test_subset) < 20:
                continue
            single_feature_gates.append(dict(
                feature=feature,
                op=op,
                train_decile=d,
                train_threshold=round(thr, 3),
                train=_stats(train_subset),
                test=_stats_with_ci(test_subset),
            ))

    # rank by test net Sharpe
    ranked_single = sorted(
        single_feature_gates,
        key=lambda g: g["test"].get("sharpe_per_trade_net_s1", -999),
        reverse=True,
    )
    summary["single_feature_gates"] = ranked_single
    print(f"=== top 5 single-feature gates by test net Sharpe ===")
    for g in ranked_single[:5]:
        print(
            f"  {g['feature']:25s} {g['op']} {g['train_threshold']:>8.2f}  "
            f"test n={g['test']['n']:4d}  net mean={g['test']['mean_bps_net_s1']:+7.2f} "
            f"(95% CI {g['test']['net_mean_ci_95']})  hit={g['test']['hit_net']:.3f}  "
            f"Sharpe_pt={g['test']['sharpe_per_trade_net_s1']:+.3f}"
        )
    print()

    # ---- Pass 2: two-feature combined gates ----
    # Use top 4 single features by train Sharpe, exhaustively combine
    train_ranked = sorted(
        single_feature_gates,
        key=lambda g: g["train"].get("sharpe_per_trade_net_s1", -999),
        reverse=True,
    )
    seen_feature_op = []
    for g in train_ranked:
        key = (g["feature"], g["op"])
        if key not in seen_feature_op:
            seen_feature_op.append(key)
        if len(seen_feature_op) >= 4:
            break
    print(f"top 4 features by train Sharpe (used for 2-feature search): {seen_feature_op}")

    # Build conditions per feature using train deciles
    feature_conditions = {}
    for feature, op in seen_feature_op:
        thresholds = _percentile_thresholds(train, feature, (20, 30, 40, 50, 60, 70))
        feature_conditions[(feature, op)] = list(zip((20, 30, 40, 50, 60, 70), thresholds))

    two_feature_gates = []
    for i in range(len(seen_feature_op)):
        for j in range(i + 1, len(seen_feature_op)):
            f1_key = seen_feature_op[i]
            f2_key = seen_feature_op[j]
            for d1, t1 in feature_conditions[f1_key]:
                for d2, t2 in feature_conditions[f2_key]:
                    conds = [
                        (f1_key[0], f1_key[1], t1),
                        (f2_key[0], f2_key[1], t2),
                    ]
                    train_subset = _apply_gate(train, conds)
                    test_subset = _apply_gate(test, conds)
                    if len(train_subset) < 30 or len(test_subset) < 15:
                        continue
                    two_feature_gates.append(dict(
                        feature_1=f1_key[0], op_1=f1_key[1], decile_1=d1, threshold_1=round(t1, 3),
                        feature_2=f2_key[0], op_2=f2_key[1], decile_2=d2, threshold_2=round(t2, 3),
                        train=_stats(train_subset),
                        test=_stats_with_ci(test_subset),
                    ))

    ranked_two = sorted(
        two_feature_gates,
        key=lambda g: g["test"].get("sharpe_per_trade_net_s1", -999),
        reverse=True,
    )
    summary["two_feature_gates"] = ranked_two
    print(f"\n=== top 10 two-feature gates by test net Sharpe ===")
    for g in ranked_two[:10]:
        f1 = f"{g['feature_1']}{g['op_1']}{g['threshold_1']:.2f}"
        f2 = f"{g['feature_2']}{g['op_2']}{g['threshold_2']:.2f}"
        print(
            f"  {f1:35s} & {f2:35s}  test n={g['test']['n']:4d}  "
            f"net mean={g['test']['mean_bps_net_s1']:+7.2f} (CI {g['test']['net_mean_ci_95']})  "
            f"hit={g['test']['hit_net']:.3f}  Sharpe_pt={g['test']['sharpe_per_trade_net_s1']:+.3f}"
        )

    # Find best gate where test net mean lower CI > 0
    profitable_gates = [
        g for g in ranked_two
        if isinstance(g["test"].get("net_mean_ci_95"), list)
        and g["test"]["net_mean_ci_95"][0] > 0
    ]
    summary["profitable_gates_count"] = len(profitable_gates)

    print(f"\n=== gates with test net mean lower CI > 0: {len(profitable_gates)} ===")
    if profitable_gates:
        for g in profitable_gates[:5]:
            f1 = f"{g['feature_1']}{g['op_1']}{g['threshold_1']:.2f}"
            f2 = f"{g['feature_2']}{g['op_2']}{g['threshold_2']:.2f}"
            print(
                f"  {f1:35s} & {f2:35s}  test n={g['test']['n']:4d}  "
                f"net mean={g['test']['mean_bps_net_s1']:+7.2f} (CI {g['test']['net_mean_ci_95']})  "
                f"hit={g['test']['hit_net']:.3f}  Sharpe_pt={g['test']['sharpe_per_trade_net_s1']:+.3f}"
            )

    print("\n=== verdict ===")
    if profitable_gates:
        best = profitable_gates[0]
        net_mean = best["test"]["mean_bps_net_s1"]
        sharpe = best["test"]["sharpe_per_trade_net_s1"]
        n = best["test"]["n"]
        if net_mean >= 5 and sharpe >= 0.2:
            print(f"  SIGNAL CONFIRMED: best gate yields net mean +{net_mean:.2f} bps at "
                  f"Sharpe per-trade {sharpe:+.3f} on n={n} test rows.")
            print(f"  Worth designing a new hypothesis spec around this gate.")
        else:
            print(f"  WEAK SIGNAL: best gate at net mean +{net_mean:.2f} bps, Sharpe {sharpe:+.3f}.")
            print(f"  Below working threshold for a new spec. Consider options pivot.")
    else:
        print(f"  NO PROFITABLE GATE: zero gates with test net mean lower CI > 0.")
        print(f"  Family is dead at S1 cost. Pivot to options leverage or kill.")

    OUT_JSON.write_text(__import__("json").dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote -> {OUT_JSON.name}")


if __name__ == "__main__":
    main()
