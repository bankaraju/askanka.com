"""
Phase 1 Workstream 3: Walk-Forward Validation
Rolling train/test splits to report hit-rate confidence intervals.
Addresses small sample concern for EUPHORIA (11 days) and RISK-OFF (20 days).
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from eodhd_client import fetch_eod_series

ARTIFACTS = Path(__file__).parent.parent / "artifacts" / "validation"
CHECKPOINTS = Path(__file__).parent.parent / "docs" / "checkpoints"


def load_data():
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
    return pd.DataFrame(all_data).dropna()


def run():
    print("=" * 60)
    print("PHASE 1.3: WALK-FORWARD VALIDATION")
    print("=" * 60)

    combined = load_data()
    feature_cols = [c for c in combined.columns if c != "nifty"]
    returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
    nifty_dir = (combined["nifty"].pct_change().shift(-1) > 0).astype(int)

    common = returns.index.intersection(nifty_dir.dropna().index)
    X = returns.loc[common]
    y_dir = nifty_dir.loc[common]

    weights = json.loads((Path(__file__).parent / "etf_optimal_weights.json").read_text())["optimal_weights"]

    # Rolling windows: train on N days, test on next M days, roll forward
    train_size = 300
    test_size = 60
    step = 30

    fold_results = []
    i = 0

    while i + train_size + test_size <= len(X):
        X_train = X.iloc[i:i + train_size]
        X_test = X.iloc[i + train_size:i + train_size + test_size]
        y_test = y_dir.iloc[i + train_size:i + train_size + test_size]

        # Compute signal with fixed weights
        signal = sum(X_test[col] * weights.get(col, 0) for col in feature_cols)
        pred = (signal > 0).astype(int)
        acc = (pred == y_test).mean() * 100

        period_start = str(X_test.index[0].date())
        period_end = str(X_test.index[-1].date())

        fold_results.append({
            "fold": len(fold_results) + 1,
            "train_end": str(X_train.index[-1].date()),
            "test_start": period_start,
            "test_end": period_end,
            "test_days": len(X_test),
            "accuracy": round(acc, 1),
        })

        i += step

    # Results
    accs = [f["accuracy"] for f in fold_results]
    print(f"\nFolds: {len(fold_results)}")
    print(f"{'Fold':>5s} {'Test Period':>25s} {'Days':>5s} {'Accuracy':>10s}")
    print("-" * 50)
    for f in fold_results:
        marker = " ✅" if f["accuracy"] > 55 else " 🔴" if f["accuracy"] < 45 else ""
        print(f"{f['fold']:>5d} {f['test_start']} → {f['test_end']} {f['test_days']:>5d} {f['accuracy']:>9.1f}%{marker}")

    mean_acc = np.mean(accs)
    std_acc = np.std(accs)
    ci_low = mean_acc - 1.96 * std_acc / np.sqrt(len(accs))
    ci_high = mean_acc + 1.96 * std_acc / np.sqrt(len(accs))
    min_acc = min(accs)
    max_acc = max(accs)
    pct_above_55 = sum(1 for a in accs if a > 55) / len(accs) * 100

    print(f"\n{'='*60}")
    print(f"WALK-FORWARD SUMMARY")
    print(f"{'='*60}")
    print(f"Mean accuracy: {mean_acc:.1f}% ± {std_acc:.1f}%")
    print(f"95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]")
    print(f"Min: {min_acc:.1f}% | Max: {max_acc:.1f}%")
    print(f"Folds > 55%: {pct_above_55:.0f}%")
    print(f"Baseline: 51.2%")

    # Verdict
    if ci_low > 51.2:
        verdict = "CONFIRMED"
        print(f"\nVERDICT: ✅ CONFIRMED — lower CI bound ({ci_low:.1f}%) above baseline (51.2%)")
    elif mean_acc > 55:
        verdict = "PROBABLE"
        print(f"\nVERDICT: 🟡 PROBABLE — mean ({mean_acc:.1f}%) above baseline but CI includes it")
    else:
        verdict = "NOT_CONFIRMED"
        print(f"\nVERDICT: 🔴 NOT CONFIRMED — walk-forward doesn't support the edge")

    # Save
    evidence = {
        "folds": fold_results,
        "mean_accuracy": round(mean_acc, 1),
        "std_accuracy": round(std_acc, 1),
        "ci_95_low": round(ci_low, 1),
        "ci_95_high": round(ci_high, 1),
        "min_accuracy": round(min_acc, 1),
        "max_accuracy": round(max_acc, 1),
        "pct_above_55": round(pct_above_55, 0),
        "verdict": verdict,
    }
    (ARTIFACTS / "walk_forward_results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    interpretation = f"""# Phase 1.3: Walk-Forward Validation — Interpretation

## Results
- {len(fold_results)} rolling folds (300-day train, 60-day test, 30-day step)
- Mean accuracy: {mean_acc:.1f}% ± {std_acc:.1f}%
- 95% CI: [{ci_low:.1f}%, {ci_high:.1f}%]
- Range: {min_acc:.1f}% to {max_acc:.1f}%
- {pct_above_55:.0f}% of folds above 55%

## Verdict: {verdict}

## Risk commentary
- If CI lower bound > baseline: edge is statistically robust across time periods
- If some folds < 50%: model has periods of failure — regime-dependent performance
- Fixed weights across all folds — in practice, weights should be re-optimised periodically
- Small zone samples within each fold amplify noise in zone-specific predictions
"""
    (CHECKPOINTS / "phase1-3-walk-forward.md").write_text(interpretation, encoding="utf-8")

    print(f"\nEvidence: artifacts/validation/walk_forward_results.json")
    print(f"Interpretation: docs/checkpoints/phase1-3-walk-forward.md")

    return evidence


if __name__ == "__main__":
    run()
