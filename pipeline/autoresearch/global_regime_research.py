"""
AutoResearch — Global Regime Predictor
Uses 3 years of global market data to find which variables predict
Indian market direction. Then Karpathy-style: test thousands of
variable combinations to find optimal weights.

Data: 757 days of US defence, oil, gold, VIX, S&P, treasuries, Nifty
War context: Russia-Ukraine (1200+ days), Gaza (3+ years), Iran-US (38 days)

The agent experiments with:
  - Which global assets predict Nifty next-day direction?
  - What return lookback (1d, 3d, 5d)?
  - What combination rules (linear, threshold, tree)?
  - What predicts our SPREAD outcomes (not just Nifty)?
"""

import json
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eodhd_client import fetch_eod_series


def load_global_data() -> pd.DataFrame:
    """Load 3 years of aligned global asset data."""
    assets = {
        "LMT.US": "us_defence_lmt",
        "NOC.US": "us_defence_noc",
        "RTX.US": "us_defence_rtx",
        "ITA.US": "us_defence_etf",
        "SPY.US": "sp500",
        "VIX.INDX": "vix",
        "GSPC.INDX": "sp500_idx",
        "GLD.US": "gold",
        "XLE.US": "energy_etf",
        "TLT.US": "treasury_20y",
        "NSEI.INDX": "nifty",
    }

    all_data = {}
    for sym, name in assets.items():
        try:
            data = fetch_eod_series(sym, days=1095)
            if data and len(data) > 100:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                all_data[name] = df["adjusted_close"] if "adjusted_close" in df.columns else df["close"]
                print(f"  Loaded {name}: {len(df)} days")
        except Exception as e:
            print(f"  Failed {name}: {e}")

    # Align all data on common dates
    combined = pd.DataFrame(all_data).dropna()
    print(f"\nAligned dataset: {len(combined)} days × {len(combined.columns)} assets")
    return combined


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute return features at multiple lookbacks."""
    features = pd.DataFrame(index=df.index)

    for col in df.columns:
        if col == "nifty":
            continue  # Target, not feature
        for lookback in [1, 3, 5, 10]:
            features[f"{col}_ret_{lookback}d"] = df[col].pct_change(lookback) * 100

    # Cross-asset features
    if "gold" in df.columns and "sp500" in df.columns:
        features["gold_sp500_ratio"] = df["gold"] / df["sp500"]
        features["gold_sp500_ratio_5d"] = features["gold_sp500_ratio"].pct_change(5) * 100

    if "vix" in df.columns:
        features["vix_level"] = df["vix"]
        features["vix_change_1d"] = df["vix"].diff()
        features["vix_change_5d"] = df["vix"].diff(5)

    if "us_defence_etf" in df.columns and "sp500" in df.columns:
        features["defence_vs_sp500_1d"] = (df["us_defence_etf"].pct_change() - df["sp500"].pct_change()) * 100
        features["defence_vs_sp500_5d"] = (df["us_defence_etf"].pct_change(5) - df["sp500"].pct_change(5)) * 100

    if "energy_etf" in df.columns and "sp500" in df.columns:
        features["energy_vs_sp500_1d"] = (df["energy_etf"].pct_change() - df["sp500"].pct_change()) * 100

    if "treasury_20y" in df.columns:
        features["tlt_ret_5d"] = df["treasury_20y"].pct_change(5) * 100

    return features.dropna()


def compute_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Nifty next-day and next-5-day returns as targets."""
    targets = pd.DataFrame(index=df.index)
    targets["nifty_next_1d"] = df["nifty"].pct_change().shift(-1) * 100
    targets["nifty_next_5d"] = df["nifty"].pct_change(5).shift(-5) * 100
    targets["nifty_direction_1d"] = (targets["nifty_next_1d"] > 0).astype(int)
    targets["nifty_direction_5d"] = (targets["nifty_next_5d"] > 0).astype(int)
    return targets.dropna()


def run_research():
    """Run the full research pipeline."""
    print("=" * 60)
    print("GLOBAL REGIME PREDICTOR — AutoResearch")
    print("Finding which global variables predict Indian market direction")
    print("=" * 60)

    # Load data
    print("\nLoading global data (3 years)...")
    df = load_global_data()
    if df.empty:
        print("No data available")
        return

    # Compute features and targets
    print("\nComputing features...")
    features = compute_features(df)
    targets = compute_targets(df)

    # Align
    common = features.index.intersection(targets.index)
    X = features.loc[common]
    y = targets.loc[common]

    print(f"Feature matrix: {X.shape[0]} days × {X.shape[1]} features")
    print(f"Features: {list(X.columns)}")

    # Walk-forward split
    split = int(len(X) * 0.7)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    print(f"Train: {len(X_train)} days | Test: {len(X_test)} days")

    # ── EXPERIMENT 1: Correlation analysis — which features predict Nifty? ──
    print(f"\n{'='*60}")
    print("EXPERIMENT 1: Feature correlations with Nifty next-day return")
    print(f"{'='*60}")

    target_col = "nifty_next_1d"
    correlations = {}
    for col in X.columns:
        corr = X[col].corr(y[target_col])
        correlations[col] = round(corr, 4)

    sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
    print(f"\nTop predictive features (by absolute correlation):")
    for feat, corr in sorted_corr[:15]:
        direction = "→ Nifty UP" if corr > 0 else "→ Nifty DOWN"
        strength = "STRONG" if abs(corr) > 0.15 else "MODERATE" if abs(corr) > 0.08 else "WEAK"
        print(f"  {corr:+.4f} | {strength:8s} | {feat:40s} | {direction}")

    # ── EXPERIMENT 2: Simple threshold strategy ──
    print(f"\n{'='*60}")
    print("EXPERIMENT 2: Simple threshold strategies")
    print(f"{'='*60}")

    best_strategy = None
    best_accuracy = 0

    for feat, corr in sorted_corr[:10]:
        # Try different thresholds
        for threshold_pctile in [20, 30, 40, 50, 60, 70, 80]:
            threshold = np.percentile(X_train[feat].dropna(), threshold_pctile)

            if corr > 0:
                # Positive correlation: when feature > threshold, predict Nifty UP
                predictions = (X_test[feat] > threshold).astype(int)
            else:
                # Negative correlation: when feature > threshold, predict Nifty DOWN
                predictions = (X_test[feat] < threshold).astype(int)

            actual = y_test["nifty_direction_1d"]
            common_idx = predictions.index.intersection(actual.index)
            if len(common_idx) < 20:
                continue

            accuracy = (predictions.loc[common_idx] == actual.loc[common_idx]).mean() * 100
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_strategy = {
                    "feature": feat,
                    "correlation": corr,
                    "threshold_pctile": threshold_pctile,
                    "threshold_value": round(threshold, 4),
                    "accuracy": round(accuracy, 1),
                    "n_test": len(common_idx),
                }

    if best_strategy:
        print(f"\nBest single-feature strategy:")
        print(f"  Feature: {best_strategy['feature']}")
        print(f"  Correlation: {best_strategy['correlation']:+.4f}")
        print(f"  Rule: {'>' if best_strategy['correlation'] > 0 else '<'} {best_strategy['threshold_value']:.4f} (percentile {best_strategy['threshold_pctile']})")
        print(f"  Test accuracy: {best_strategy['accuracy']}% ({best_strategy['n_test']} days)")

    # ── EXPERIMENT 3: Multi-feature model ──
    print(f"\n{'='*60}")
    print("EXPERIMENT 3: Multi-feature model (XGBoost)")
    print(f"{'='*60}")

    try:
        import xgboost as xgb
        from sklearn.metrics import accuracy_score, classification_report

        # Use top 10 features by correlation
        top_features = [f for f, _ in sorted_corr[:10]]
        X_train_top = X_train[top_features].dropna()
        X_test_top = X_test[top_features].dropna()
        y_train_aligned = y_train.loc[X_train_top.index]["nifty_direction_1d"]
        y_test_aligned = y_test.loc[X_test_top.index]["nifty_direction_1d"]

        model = xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1,
                                  eval_metric="logloss", verbosity=0)
        model.fit(X_train_top, y_train_aligned)

        y_pred = model.predict(X_test_top)
        accuracy = accuracy_score(y_test_aligned, y_pred) * 100

        print(f"  Accuracy: {accuracy:.1f}% ({len(y_test_aligned)} test days)")
        print(f"  Baseline (always up): {y_test_aligned.mean()*100:.1f}%")
        print(f"  Edge over baseline: {accuracy - y_test_aligned.mean()*100:+.1f}pp")

        # Feature importance
        importances = dict(zip(top_features, model.feature_importances_))
        print(f"\n  Feature importance:")
        for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
            bar = "█" * int(imp * 50)
            print(f"    {imp:.3f} | {bar} | {feat}")

        # Today's prediction
        print(f"\n  TODAY'S PREDICTION:")
        latest = X[top_features].iloc[-1:]
        if not latest.isna().any().any():
            pred = model.predict(latest)[0]
            prob = model.predict_proba(latest)[0]
            print(f"    Direction: {'UP' if pred == 1 else 'DOWN'}")
            print(f"    Confidence: {max(prob)*100:.0f}%")
            print(f"    Based on: {dict(zip(top_features, [f'{v:.2f}' for v in latest.values[0]]))}")

    except Exception as e:
        print(f"  XGBoost failed: {e}")

    # ── EXPERIMENT 4: War regime analysis ──
    print(f"\n{'='*60}")
    print("EXPERIMENT 4: War period analysis")
    print(f"{'='*60}")

    # Russia-Ukraine started Feb 2022, Iran-US started ~March 2026
    war_start = pd.Timestamp("2022-02-24")
    gaza_escalation = pd.Timestamp("2023-10-07")
    iran_war = pd.Timestamp("2026-03-01")

    for label, start, end in [
        ("Pre-war (2023)", pd.Timestamp("2023-04-01"), pd.Timestamp("2023-09-30")),
        ("Gaza escalation", gaza_escalation, pd.Timestamp("2024-03-01")),
        ("Pre-Iran (2025)", pd.Timestamp("2025-06-01"), pd.Timestamp("2025-12-31")),
        ("Iran war", iran_war, pd.Timestamp("2026-04-08")),
    ]:
        mask = (df.index >= start) & (df.index <= end)
        period = df[mask]
        if len(period) < 10:
            continue

        nifty_ret = (period["nifty"].iloc[-1] / period["nifty"].iloc[0] - 1) * 100
        defence_ret = (period["us_defence_etf"].iloc[-1] / period["us_defence_etf"].iloc[0] - 1) * 100 if "us_defence_etf" in period else 0
        gold_ret = (period["gold"].iloc[-1] / period["gold"].iloc[0] - 1) * 100 if "gold" in period else 0
        energy_ret = (period["energy_etf"].iloc[-1] / period["energy_etf"].iloc[0] - 1) * 100 if "energy_etf" in period else 0

        print(f"\n  {label} ({len(period)} days):")
        print(f"    Nifty: {nifty_ret:+.1f}% | US Defence: {defence_ret:+.1f}% | Gold: {gold_ret:+.1f}% | Energy: {energy_ret:+.1f}%")

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "data_days": len(X),
        "features": len(X.columns),
        "top_correlations": sorted_corr[:15],
        "best_single_strategy": best_strategy,
    }
    Path(__file__).parent.joinpath("global_regime_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nResults saved to autoresearch/global_regime_results.json")


if __name__ == "__main__":
    run_research()
