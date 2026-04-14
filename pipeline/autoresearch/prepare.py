"""
AutoResearch — Immutable Evaluation Harness
Based on Karpathy's autoresearch pattern.

This file is NEVER modified by the experiment loop.
It provides data loading, train/test split, and evaluation.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    precision_recall_curve, classification_report,
)

# Add pipeline to path
PIPELINE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

RESULTS_DIR = Path(__file__).parent / "results"
BEST_MODEL_FILE = Path(__file__).parent / "best_model.json"
BASELINE_FILE = Path(__file__).parent / "baseline.json"
RESULTS_DIR.mkdir(exist_ok=True)


def load_data():
    """Load training data from correlation_regime module.
    Returns X (features DataFrame), y (binary labels Series)."""
    from correlation_regime import _build_training_data
    X, y = _build_training_data()
    if X.empty:
        raise ValueError("No training data available")
    return X, y


def split_data(X, y, train_ratio=0.8):
    """Walk-forward time-ordered split. No leakage."""
    split_idx = int(len(X) * train_ratio)
    return (
        X.iloc[:split_idx], X.iloc[split_idx:],
        y.iloc[:split_idx], y.iloc[split_idx:],
    )


def evaluate(y_true, y_pred, y_prob=None):
    """Compute all metrics. Returns dict."""
    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "n_test": len(y_true),
        "n_positive_test": int(y_true.sum()),
        "n_predicted_positive": int(y_pred.sum()),
        "true_positives": int(((y_pred == 1) & (y_true == 1)).sum()),
        "false_positives": int(((y_pred == 1) & (y_true == 0)).sum()),
    }

    # Optimal threshold search if probabilities provided
    if y_prob is not None:
        best_f1 = 0
        best_thresh = 0.5
        for thresh in np.arange(0.05, 0.95, 0.05):
            preds_t = (y_prob >= thresh).astype(int)
            f1_t = f1_score(y_true, preds_t, zero_division=0)
            if f1_t > best_f1:
                best_f1 = f1_t
                best_thresh = thresh
        metrics["optimal_threshold"] = round(float(best_thresh), 2)
        metrics["f1_at_optimal"] = round(float(best_f1), 4)

        # Metrics at optimal threshold
        opt_pred = (y_prob >= best_thresh).astype(int)
        metrics["precision_at_optimal"] = round(float(precision_score(y_true, opt_pred, zero_division=0)), 4)
        metrics["recall_at_optimal"] = round(float(recall_score(y_true, opt_pred, zero_division=0)), 4)

    return metrics


def get_current_best():
    """Load current best metrics."""
    if BEST_MODEL_FILE.exists():
        return json.loads(BEST_MODEL_FILE.read_text(encoding="utf-8"))
    return None


def save_result(experiment_num, description, metrics, model_config, is_new_best=False):
    """Save experiment result to results directory."""
    result = {
        "experiment": experiment_num,
        "timestamp": datetime.now().isoformat(),
        "description": description,
        "metrics": metrics,
        "model_config": model_config,
        "is_new_best": is_new_best,
    }
    fname = RESULTS_DIR / f"experiment-{experiment_num:03d}.json"
    fname.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if is_new_best:
        BEST_MODEL_FILE.write_text(json.dumps({
            "experiment": experiment_num,
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "metrics": metrics,
            "model_config": model_config,
        }, indent=2), encoding="utf-8")

    return result


def save_baseline(metrics):
    """Save baseline metrics (run once)."""
    baseline = {
        "timestamp": datetime.now().isoformat(),
        "description": "Original XGBoost model — baseline before AutoResearch",
        "metrics": metrics,
    }
    BASELINE_FILE.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return baseline


def load_baseline():
    """Load baseline metrics."""
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return None
