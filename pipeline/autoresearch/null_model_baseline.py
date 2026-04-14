"""
Phase 1 Workstream 1: Null-Model Baseline
URE must outperform random weights AND simple baselines (VIX-only, SPY-only).
1,000 random simulations + 3 simple baselines.

Evidence: JSON results + markdown interpretation.
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
ARTIFACTS.mkdir(parents=True, exist_ok=True)
CHECKPOINTS.mkdir(parents=True, exist_ok=True)


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
    print("PHASE 1.1: NULL-MODEL BASELINE")
    print("=" * 60)

    combined = load_data()
    feature_cols = [c for c in combined.columns if c != "nifty"]
    returns = pd.DataFrame({c: combined[c].pct_change() * 100 for c in feature_cols}).dropna()
    nifty_dir = (combined["nifty"].pct_change().shift(-1) > 0).astype(int)
    nifty_ret = combined["nifty"].pct_change().shift(-1) * 100

    common = returns.index.intersection(nifty_dir.dropna().index)
    X = returns.loc[common]
    y_dir = nifty_dir.loc[common]
    y_ret = nifty_ret.loc[common]

    split = int(len(X) * 0.7)
    X_test = X.iloc[split:]
    y_test_dir = y_dir.iloc[split:]
    y_test_ret = y_ret.iloc[split:]

    baseline_always_up = y_test_dir.mean() * 100
    print(f"Test set: {len(X_test)} days | Baseline (always up): {baseline_always_up:.1f}%")

    # Load URE optimal weights
    weights = json.loads((Path(__file__).parent / "etf_optimal_weights.json").read_text())["optimal_weights"]

    # URE signal
    ure_signal = sum(X_test[col] * weights.get(col, 0) for col in feature_cols)
    ure_pred = (ure_signal > 0).astype(int)
    ure_acc = (ure_pred == y_test_dir).mean() * 100
    ure_rets = y_test_ret.copy()
    ure_rets[ure_signal < 0] *= -1
    ure_sharpe = ure_rets.mean() / max(ure_rets.std(), 0.01) * np.sqrt(252)

    print(f"\nURE: acc={ure_acc:.1f}% | Sharpe={ure_sharpe:.2f}")

    # ── BASELINE 1: VIX-only ──
    vix_signal = -X_test["vix"]  # Negative = VIX up → Nifty down
    vix_pred = (vix_signal > 0).astype(int)
    vix_acc = (vix_pred == y_test_dir).mean() * 100
    vix_rets = y_test_ret.copy()
    vix_rets[vix_signal < 0] *= -1
    vix_sharpe = vix_rets.mean() / max(vix_rets.std(), 0.01) * np.sqrt(252)
    print(f"VIX-only: acc={vix_acc:.1f}% | Sharpe={vix_sharpe:.2f}")

    # ── BASELINE 2: SPY-only ──
    spy_signal = X_test["sp500"]
    spy_pred = (spy_signal > 0).astype(int)
    spy_acc = (spy_pred == y_test_dir).mean() * 100
    spy_rets = y_test_ret.copy()
    spy_rets[spy_signal < 0] *= -1
    spy_sharpe = spy_rets.mean() / max(spy_rets.std(), 0.01) * np.sqrt(252)
    print(f"SPY-only: acc={spy_acc:.1f}% | Sharpe={spy_sharpe:.2f}")

    # ── BASELINE 3: HYG-only (top correlated) ──
    hyg_signal = X_test["high_yield"]
    hyg_pred = (hyg_signal > 0).astype(int)
    hyg_acc = (hyg_pred == y_test_dir).mean() * 100
    hyg_rets = y_test_ret.copy()
    hyg_rets[hyg_signal < 0] *= -1
    hyg_sharpe = hyg_rets.mean() / max(hyg_rets.std(), 0.01) * np.sqrt(252)
    print(f"HYG-only: acc={hyg_acc:.1f}% | Sharpe={hyg_sharpe:.2f}")

    # ── NULL MODEL: 1,000 random weight simulations ──
    print(f"\nRunning 1,000 random weight simulations...")
    random_accs = []
    random_sharpes = []

    for _ in range(1000):
        rand_weights = {col: np.random.normal(0, 0.2) for col in feature_cols}
        rand_signal = sum(X_test[col] * rand_weights[col] for col in feature_cols)
        rand_pred = (rand_signal > 0).astype(int)
        rand_acc = (rand_pred == y_test_dir).mean() * 100
        rand_rets = y_test_ret.copy()
        rand_rets[rand_signal < 0] *= -1
        rand_sharpe = rand_rets.mean() / max(rand_rets.std(), 0.01) * np.sqrt(252)
        random_accs.append(rand_acc)
        random_sharpes.append(rand_sharpe)

    random_accs = np.array(random_accs)
    random_sharpes = np.array(random_sharpes)

    ure_acc_pctile = (random_accs < ure_acc).mean() * 100
    ure_sharpe_pctile = (random_sharpes < ure_sharpe).mean() * 100

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"{'Model':20s} {'Accuracy':>10s} {'Sharpe':>10s}")
    print("-" * 42)
    print(f"{'Always Up':20s} {baseline_always_up:>9.1f}% {'N/A':>10s}")
    print(f"{'VIX-only':20s} {vix_acc:>9.1f}% {vix_sharpe:>10.2f}")
    print(f"{'SPY-only':20s} {spy_acc:>9.1f}% {spy_sharpe:>10.2f}")
    print(f"{'HYG-only':20s} {hyg_acc:>9.1f}% {hyg_sharpe:>10.2f}")
    print(f"{'URE (optimised)':20s} {ure_acc:>9.1f}% {ure_sharpe:>10.2f}")
    print(f"{'Random (median)':20s} {np.median(random_accs):>9.1f}% {np.median(random_sharpes):>10.2f}")
    print(f"{'Random (95th)':20s} {np.percentile(random_accs, 95):>9.1f}% {np.percentile(random_sharpes, 95):>10.2f}")

    print(f"\nURE vs Random: acc at {ure_acc_pctile:.0f}th pctile | Sharpe at {ure_sharpe_pctile:.0f}th pctile")

    # Verdict
    print(f"\n{'='*60}")
    if ure_acc_pctile >= 95 and ure_sharpe_pctile >= 95:
        verdict = "STRONG_EDGE"
        print("VERDICT: ✅ STRONG EDGE — URE significantly outperforms random AND simple baselines")
    elif ure_acc_pctile >= 75 and ure_sharpe_pctile >= 75:
        verdict = "MODERATE_EDGE"
        print("VERDICT: 🟡 MODERATE EDGE — URE outperforms most random configs but not overwhelmingly")
    else:
        verdict = "NOT_SIGNIFICANT"
        print("VERDICT: 🔴 NOT SIGNIFICANT — URE does not convincingly outperform random weights")

    if ure_acc > vix_acc and ure_acc > spy_acc and ure_acc > hyg_acc:
        print("URE beats ALL simple baselines ✅")
    else:
        best_simple = max([("VIX", vix_acc), ("SPY", spy_acc), ("HYG", hyg_acc)], key=lambda x: x[1])
        print(f"WARNING: {best_simple[0]} ({best_simple[1]:.1f}%) is competitive with URE ({ure_acc:.1f}%)")

    # Save evidence
    evidence = {
        "ure_accuracy": round(ure_acc, 1),
        "ure_sharpe": round(ure_sharpe, 2),
        "ure_acc_percentile": round(ure_acc_pctile, 0),
        "ure_sharpe_percentile": round(ure_sharpe_pctile, 0),
        "baselines": {
            "always_up": round(baseline_always_up, 1),
            "vix_only": {"acc": round(vix_acc, 1), "sharpe": round(vix_sharpe, 2)},
            "spy_only": {"acc": round(spy_acc, 1), "sharpe": round(spy_sharpe, 2)},
            "hyg_only": {"acc": round(hyg_acc, 1), "sharpe": round(hyg_sharpe, 2)},
        },
        "random_distribution": {
            "n": 1000,
            "acc_median": round(float(np.median(random_accs)), 1),
            "acc_95th": round(float(np.percentile(random_accs, 95)), 1),
            "sharpe_median": round(float(np.median(random_sharpes)), 2),
            "sharpe_95th": round(float(np.percentile(random_sharpes, 95)), 2),
        },
        "verdict": verdict,
    }
    (ARTIFACTS / "null_model_results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    # Save interpretation
    interpretation = f"""# Phase 1.1: Null-Model Baseline — Interpretation

## Results
- URE accuracy: {ure_acc:.1f}% (vs {baseline_always_up:.1f}% always-up baseline)
- URE Sharpe: {ure_sharpe:.2f}
- URE vs random weights: {ure_acc_pctile:.0f}th percentile accuracy, {ure_sharpe_pctile:.0f}th percentile Sharpe

## Simple baselines
- VIX-only: {vix_acc:.1f}% accuracy, {vix_sharpe:.2f} Sharpe
- SPY-only: {spy_acc:.1f}% accuracy, {spy_sharpe:.2f} Sharpe
- HYG-only: {hyg_acc:.1f}% accuracy, {hyg_sharpe:.2f} Sharpe

## Verdict: {verdict}

## Risk commentary
- Random distribution: median {np.median(random_accs):.1f}% accuracy, 95th {np.percentile(random_accs, 95):.1f}%
- If URE < 95th percentile of random, the edge may be partially from luck/overfitting
- Small zone samples (EUPHORIA 11 days, RISK-OFF 20 days) inflate zone-specific claims
- Walk-forward validation needed to confirm out-of-sample persistence
"""
    (CHECKPOINTS / "phase1-1-null-model.md").write_text(interpretation, encoding="utf-8")

    print(f"\nEvidence: artifacts/validation/null_model_results.json")
    print(f"Interpretation: docs/checkpoints/phase1-1-null-model.md")

    return evidence


if __name__ == "__main__":
    run()
