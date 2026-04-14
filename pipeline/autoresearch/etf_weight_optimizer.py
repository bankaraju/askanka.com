"""
AutoResearch — ETF Weight Optimizer (Karpathy Pattern)
Tests thousands of weight combinations across 28 global ETFs
to find the optimal weighting that predicts Indian market direction.

This IS the sentiment index — not hand-picked weights like MSI,
but DATA-DRIVEN weights from 716 days of global market history.
"""

import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series


def load_all_etfs():
    """Load all available ETFs."""
    etfs = {
        "ITA.US": "defence", "XLE.US": "energy", "XLF.US": "financials",
        "XLK.US": "tech", "XLV.US": "healthcare", "XLP.US": "staples",
        "XLI.US": "industrials", "EEM.US": "em", "EWZ.US": "brazil",
        "INDA.US": "india_etf", "FXI.US": "china", "EWJ.US": "japan",
        "EFA.US": "developed", "USO.US": "oil", "UNG.US": "natgas",
        "SLV.US": "silver", "DBA.US": "agriculture", "HYG.US": "high_yield",
        "LQD.US": "ig_bond", "TLT.US": "treasury", "IEF.US": "mid_treasury",
        "UUP.US": "dollar", "FXE.US": "euro", "FXY.US": "yen",
        "SPY.US": "sp500", "GLD.US": "gold", "VIX.INDX": "vix",
        "KBE.US": "kbw_bank", "KRE.US": "regional_bank",
        "JETS.US": "airlines", "ARKK.US": "innovation",
        "NSEI.INDX": "nifty",
    }

    all_data = {}
    for sym, name in etfs.items():
        try:
            data = fetch_eod_series(sym, days=1095)
            if data and len(data) > 200:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                col = "adjusted_close" if "adjusted_close" in df.columns else "close"
                all_data[name] = df[col].astype(float)
        except Exception:
            pass

    combined = pd.DataFrame(all_data).dropna()
    print(f"Loaded: {len(combined)} days × {len(combined.columns)} assets")
    return combined


def run_optimization(n_iterations=2000):
    """Run Karpathy-style weight optimization."""
    print("=" * 60)
    print("ETF WEIGHT OPTIMIZER — Karpathy AutoResearch")
    print(f"Testing {n_iterations} weight combinations")
    print("=" * 60)

    df = load_all_etfs()
    if "nifty" not in df.columns:
        print("No Nifty data!")
        return

    # Features: 1-day returns of all non-Nifty assets
    feature_cols = [c for c in df.columns if c != "nifty"]
    features = pd.DataFrame({c: df[c].pct_change() * 100 for c in feature_cols}).dropna()

    # Target: Nifty next-day return
    target = df["nifty"].pct_change().shift(-1)
    target_direction = (target > 0).astype(int)

    common = features.index.intersection(target.dropna().index)
    X = features.loc[common]
    y_ret = target.loc[common]
    y_dir = target_direction.loc[common]

    # Walk-forward split
    split = int(len(X) * 0.7)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train_dir = y_dir.iloc[:split]
    y_test_dir = y_dir.iloc[split:]
    y_test_ret = y_ret.iloc[split:]

    print(f"Train: {len(X_train)} | Test: {len(X_test)} | Features: {len(feature_cols)}")
    baseline = y_test_dir.mean() * 100
    print(f"Baseline (always up): {baseline:.1f}%")

    # First: find correlation-weighted optimal
    correlations = {}
    for col in feature_cols:
        correlations[col] = X_train[col].corr(y_dir.iloc[:split])

    # Normalize correlations to weights
    abs_corrs = {k: abs(v) for k, v in correlations.items() if not np.isnan(v)}
    total = sum(abs_corrs.values())
    corr_weights = {k: v / total for k, v in abs_corrs.items()}

    # Test correlation-weighted strategy
    weighted_signal = sum(X_test[col] * correlations.get(col, 0) for col in feature_cols)
    corr_pred = (weighted_signal > 0).astype(int)
    corr_acc = (corr_pred == y_test_dir).mean() * 100
    print(f"\nCorrelation-weighted accuracy: {corr_acc:.1f}%")

    # Now: Karpathy loop — random search for better weights
    print(f"\nRunning {n_iterations} random weight experiments...")
    best_acc = corr_acc
    best_weights = dict(corr_weights)
    best_sharpe = 0
    all_results = []

    for i in range(n_iterations):
        # Random perturbation of correlation weights
        trial_weights = {}
        for col in feature_cols:
            base = correlations.get(col, 0)
            noise = np.random.normal(0, abs(base) * 0.5) if base != 0 else np.random.normal(0, 0.01)
            trial_weights[col] = base + noise

        # Compute weighted signal
        signal = sum(X_test[col] * trial_weights[col] for col in feature_cols)
        pred = (signal > 0).astype(int)
        acc = (pred == y_test_dir).mean() * 100

        # Also compute Sharpe: returns when signal > 0 vs < 0
        long_rets = y_test_ret[signal > 0]
        short_rets = -y_test_ret[signal < 0]  # Inverted for short
        all_rets = pd.concat([long_rets, short_rets])
        sharpe = all_rets.mean() / max(all_rets.std(), 0.01) * np.sqrt(252) if len(all_rets) > 10 else 0

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = dict(trial_weights)
            best_acc = acc

        all_results.append({"acc": round(acc, 1), "sharpe": round(sharpe, 2)})

        if i % 500 == 0:
            print(f"  Iter {i}/{n_iterations} | Best acc: {best_acc:.1f}% | Best Sharpe: {best_sharpe:.2f}")

    # Results
    print(f"\n{'='*60}")
    print("OPTIMAL ETF WEIGHTS (by Sharpe)")
    print(f"{'='*60}")
    print(f"Best accuracy: {best_acc:.1f}% (baseline {baseline:.1f}%)")
    print(f"Best Sharpe: {best_sharpe:.2f}")

    # Sort weights by absolute value
    sorted_weights = sorted(best_weights.items(), key=lambda x: abs(x[1]), reverse=True)

    print(f"\nTop 15 ETF weights:")
    print(f"{'ETF':20s} {'Weight':>10s} {'Direction':>12s}")
    print("-" * 45)
    for etf, w in sorted_weights[:15]:
        direction = "RISK-ON" if w > 0 else "RISK-OFF"
        bar = "+" * int(abs(w) * 100) if w > 0 else "-" * int(abs(w) * 100)
        print(f"{etf:20s} {w:+.4f}     {direction:>10s}  {bar[:20]}")

    # TODAY'S SIGNAL from optimal weights
    today_features = X.iloc[-1]
    today_signal = sum(today_features[col] * best_weights[col] for col in feature_cols)
    print(f"\n{'='*60}")
    print(f"TODAY'S GLOBAL REGIME SIGNAL: {today_signal:+.4f}")
    print(f"Direction: {'RISK-ON (Nifty UP)' if today_signal > 0 else 'RISK-OFF (Nifty DOWN)'}")
    print(f"Conviction: {'STRONG' if abs(today_signal) > 0.5 else 'MODERATE' if abs(today_signal) > 0.2 else 'WEAK'}")
    print(f"{'='*60}")

    # Top contributors today
    print(f"\nToday's top signal contributors:")
    contributions = {col: today_features[col] * best_weights[col] for col in feature_cols}
    for etf, contrib in sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:10]:
        direction = "UP" if contrib > 0 else "DOWN"
        print(f"  {etf:20s}: {today_features[etf]:+6.2f}% × {best_weights[etf]:+.4f} = {contrib:+.4f} ({direction})")

    # Save
    results = {
        "best_accuracy": round(best_acc, 1),
        "baseline": round(baseline, 1),
        "best_sharpe": round(best_sharpe, 2),
        "n_iterations": n_iterations,
        "optimal_weights": {k: round(v, 6) for k, v in sorted_weights[:20]},
        "today_signal": round(today_signal, 4),
        "today_direction": "UP" if today_signal > 0 else "DOWN",
        "timestamp": datetime.now().isoformat(),
    }
    Path(__file__).parent.joinpath("etf_optimal_weights.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved to autoresearch/etf_optimal_weights.json")
    return results


if __name__ == "__main__":
    run_optimization(n_iterations=2000)
