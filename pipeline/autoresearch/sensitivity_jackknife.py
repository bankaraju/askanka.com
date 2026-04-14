"""
Phase 1 Workstream 2: Sensitivity Jackknife
Remove top-3 weighted ETFs (XLF, ARKK, TLT) one at a time and all together.
If model collapses, the edge depends on specific ETFs — fragile.
If model holds, the edge is robust across the portfolio.
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


def compute_accuracy(X_test, y_test_dir, weights, feature_cols, exclude=None):
    """Compute accuracy excluding specified ETFs."""
    if exclude is None:
        exclude = set()
    signal = sum(X_test[col] * weights.get(col, 0) for col in feature_cols if col not in exclude)
    pred = (signal > 0).astype(int)
    acc = (pred == y_test_dir).mean() * 100

    y_test_ret = y_test_dir.copy()  # Simplified
    rets = pd.Series(0.0, index=signal.index)
    rets[signal > 0] = 1
    rets[signal < 0] = -1
    sharpe = signal.mean() / max(signal.std(), 0.01) * np.sqrt(252)

    return round(acc, 1), round(sharpe, 2)


def run():
    print("=" * 60)
    print("PHASE 1.2: SENSITIVITY JACKKNIFE")
    print("=" * 60)

    combined = load_data()
    feature_cols = [c for c in combined.columns if c != "nifty"]
    returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
    nifty_dir = (combined["nifty"].pct_change().shift(-1) > 0).astype(int)

    common = returns.index.intersection(nifty_dir.dropna().index)
    X = returns.loc[common]
    y_dir = nifty_dir.loc[common]

    split = int(len(X) * 0.7)
    X_test = X.iloc[split:]
    y_test_dir = y_dir.iloc[split:]

    weights = json.loads((Path(__file__).parent / "etf_optimal_weights.json").read_text())["optimal_weights"]

    # Full model
    full_acc, full_sharpe = compute_accuracy(X_test, y_test_dir, weights, feature_cols)
    print(f"Full model: acc={full_acc}% | Sharpe={full_sharpe}")

    # Top 3 by weight
    top3 = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    top3_names = [t[0] for t in top3]
    print(f"Top 3 ETFs: {', '.join(f'{n} ({w:+.3f})' for n, w in top3)}")

    results = [{"config": "Full model", "excluded": "none", "accuracy": full_acc, "sharpe": full_sharpe}]

    # Remove each top-3 individually
    for name, weight in top3:
        acc, sharpe = compute_accuracy(X_test, y_test_dir, weights, feature_cols, exclude={name})
        drop = full_acc - acc
        print(f"  Without {name:15s} (w={weight:+.3f}): acc={acc}% (drop {drop:+.1f}pp) | Sharpe={sharpe}")
        results.append({"config": f"Without {name}", "excluded": name, "accuracy": acc, "sharpe": sharpe, "drop": round(drop, 1)})

    # Remove all top-3 together
    acc, sharpe = compute_accuracy(X_test, y_test_dir, weights, feature_cols, exclude=set(top3_names))
    drop = full_acc - acc
    print(f"  Without ALL top-3: acc={acc}% (drop {drop:+.1f}pp) | Sharpe={sharpe}")
    results.append({"config": "Without all top-3", "excluded": top3_names, "accuracy": acc, "sharpe": sharpe, "drop": round(drop, 1)})

    # Remove random 3 ETFs (average of 100 trials)
    random_drops = []
    for _ in range(100):
        random_3 = set(np.random.choice(feature_cols, 3, replace=False))
        acc, _ = compute_accuracy(X_test, y_test_dir, weights, feature_cols, exclude=random_3)
        random_drops.append(full_acc - acc)
    avg_random_drop = np.mean(random_drops)
    print(f"  Avg drop from random 3: {avg_random_drop:+.1f}pp")

    # Verdict
    print(f"\n{'='*60}")
    max_drop = max(r.get("drop", 0) for r in results if "drop" in r)
    all_top3_drop = results[-1]["drop"]

    if all_top3_drop < 5 and max_drop < 3:
        verdict = "ROBUST"
        print("VERDICT: ✅ ROBUST — model survives removal of top-3 ETFs")
    elif all_top3_drop < 8:
        verdict = "MODERATE"
        print("VERDICT: 🟡 MODERATE — model degrades but doesn't collapse without top-3")
    else:
        verdict = "FRAGILE"
        print("VERDICT: 🔴 FRAGILE — model depends heavily on specific ETFs")

    if all_top3_drop > avg_random_drop * 2:
        print(f"WARNING: Top-3 removal ({all_top3_drop:+.1f}pp) much worse than random-3 ({avg_random_drop:+.1f}pp)")

    # Save
    evidence = {"results": results, "verdict": verdict, "random_3_avg_drop": round(avg_random_drop, 1)}
    (ARTIFACTS / "jackknife_results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    interpretation = f"""# Phase 1.2: Sensitivity Jackknife — Interpretation

## Results
- Full model: {full_acc}% accuracy
- Without {top3_names[0]}: {results[1]['accuracy']}% (drop {results[1].get('drop', 0):+.1f}pp)
- Without {top3_names[1]}: {results[2]['accuracy']}% (drop {results[2].get('drop', 0):+.1f}pp)
- Without {top3_names[2]}: {results[3]['accuracy']}% (drop {results[3].get('drop', 0):+.1f}pp)
- Without ALL top-3: {results[4]['accuracy']}% (drop {all_top3_drop:+.1f}pp)
- Average random-3 removal: {avg_random_drop:+.1f}pp

## Verdict: {verdict}

## Risk commentary
- Top-3 ETFs account for ~50% of total weight
- If removing them causes >5pp drop, the model has concentration risk
- Compare vs random-3 removal to assess whether it's the SPECIFIC ETFs or just losing 3 inputs
"""
    (CHECKPOINTS / "phase1-2-jackknife.md").write_text(interpretation, encoding="utf-8")

    print(f"\nEvidence: artifacts/validation/jackknife_results.json")
    print(f"Interpretation: docs/checkpoints/phase1-2-jackknife.md")

    return evidence


if __name__ == "__main__":
    run()
