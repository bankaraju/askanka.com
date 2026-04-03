"""
Anka Research Pipeline — Fragility Score CLI Runner

Usage:
    python run_fragility.py              # train + score + save
    python run_fragility.py --score-only # score using cached model
    python run_fragility.py --history    # compute + save correlation history only
"""

import sys
import argparse
import logging
from pathlib import Path

# Packages live in pipeline/lib/
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from correlation_regime import (
    compute_all_pair_correlations,
    save_correlation_history,
    train_fragility_model,
    score_current_fragility,
    save_fragility_scores,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anka.run_fragility")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_training_results(result: dict) -> None:
    """Print model training metrics."""
    print("\n" + "=" * 64)
    print("  XGBoost Fragility Model — Training Results")
    print("=" * 64)
    print(f"  Trained at:       {result['trained_at']}")
    print(f"  Samples:          {result['n_samples']} ({result['n_train']} train / {result['n_test']} test)")
    bal = result["class_balance"]
    print(f"  Class balance:    {bal['stable']} stable / {bal['break_events']} break events")
    print(f"  scale_pos_weight: {result['scale_pos_weight']}")
    print()
    print(f"  Accuracy:   {result['accuracy']:.4f}")
    print(f"  Precision:  {result['precision']:.4f}")
    print(f"  Recall:     {result['recall']:.4f}")
    print(f"  F1 Score:   {result['f1_score']:.4f}")
    print()
    print("  Top 10 Features by Importance:")
    for i, (feat, imp) in enumerate(list(result["feature_importance"].items())[:10], 1):
        bar = "#" * int(imp * 100)
        print(f"    {i:2d}. {feat:<25s} {imp:.4f}  {bar}")
    print()


def print_fragility_table(scores: dict) -> None:
    """Print fragility score summary table."""
    print("=" * 74)
    print("  Pair Fragility Scores — Current Assessment")
    print("=" * 74)
    print(f"  {'Pair':<25s} {'Score':>6s}  {'Corr':>6s}  {'Prob':>6s}  {'Bar':<20s}")
    print("  " + "-" * 70)

    # Sort by fragility score descending
    sorted_pairs = sorted(scores.items(), key=lambda x: x[1]["fragility_score"], reverse=True)

    for name, data in sorted_pairs:
        score = data["fragility_score"]
        corr = data.get("current_corr_21")
        prob = data["probability"]

        # Visual bar: 20 chars wide
        filled = int(score / 5)  # 0-100 mapped to 0-20
        bar = "|" + "X" * filled + "." * (20 - filled) + "|"

        # Color hint via text
        if score >= 70:
            level = "!!!"
        elif score >= 40:
            level = " ! "
        else:
            level = "   "

        corr_str = f"{corr:.3f}" if corr is not None else "  N/A"
        print(f"  {name:<25s} {score:5.1f}%  {corr_str:>6s}  {prob:5.3f}  {bar} {level}")

    print()

    # Print top drivers for highest-fragility pair
    if sorted_pairs:
        top_name, top_data = sorted_pairs[0]
        print(f"  Top drivers for {top_name}:")
        for d in top_data.get("top_drivers", [])[:5]:
            print(f"    - {d['feature']}: {d['contribution']:.4f}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Anka Research — Correlation Regime Fragility Scorer"
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Score using cached model (skip training)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Compute and save correlation history only",
    )
    args = parser.parse_args()

    # --history mode
    if args.history:
        print("\n[1/2] Computing correlation history for all pairs...")
        results = compute_all_pair_correlations()
        print(f"       Processed {len(results)} pairs")

        print("[2/2] Saving correlation history...")
        save_correlation_history(results)

        for name, data in results.items():
            lc = data["label_counts"]
            corr = data["current_corr"]
            n_breaks = len(data["breaks"])
            print(f"  {name:<25s}  corr={corr:+.3f}  breaks={n_breaks}  "
                  f"stable={lc['stable']}  pre_break={lc['pre_break']}  break={lc['break']}")

        print("\nDone. Correlation history saved.")
        return

    # --score-only mode
    if args.score_only:
        print("\n[1/2] Scoring current fragility (cached model)...")
        try:
            scores = score_current_fragility()
        except RuntimeError as e:
            print(f"\nERROR: {e}")
            print("Run without --score-only first to train the model.")
            sys.exit(1)

        print("[2/2] Saving fragility scores...")
        save_fragility_scores(scores)
        print_fragility_table(scores)
        print("Done. Scores saved to data/fragility_scores.json")
        return

    # Full pipeline: train + score + save
    print("\n[1/4] Training XGBoost fragility model...")
    result = train_fragility_model()
    print_training_results(result)

    print("[2/4] Scoring current fragility for all pairs...")
    scores = score_current_fragility()

    print("[3/4] Saving fragility scores...")
    save_fragility_scores(scores)

    print("[4/4] Computing + saving correlation history...")
    corr_results = compute_all_pair_correlations()
    save_correlation_history(corr_results)

    print_fragility_table(scores)
    print("Done. Outputs saved:")
    print("  - data/fragility_scores.json")
    print("  - data/fragility_model.json")
    print("  - data/correlation_history.json")


if __name__ == "__main__":
    main()
