"""
AutoResearch — Experiment Loop Controller
Inspired by Karpathy's autoresearch.

Runs N experiments autonomously:
1. Reads program.md for research directions
2. Uses Claude API to modify train.py
3. Executes train.py, captures metrics
4. Keeps improvements, reverts failures
5. Logs everything

Usage:
    python run_loop.py                    # run 50 experiments
    python run_loop.py --n 20             # run 20 experiments
    python run_loop.py --baseline-only    # just capture baseline
"""

import argparse
import json
import os
import subprocess
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

AUTORESEARCH_DIR = Path(__file__).parent
PIPELINE_DIR = AUTORESEARCH_DIR.parent
TRAIN_FILE = AUTORESEARCH_DIR / "train.py"
PROGRAM_FILE = AUTORESEARCH_DIR / "program.md"
RESULTS_DIR = AUTORESEARCH_DIR / "results"
BEST_MODEL_FILE = AUTORESEARCH_DIR / "best_model.json"
BASELINE_FILE = AUTORESEARCH_DIR / "baseline.json"

load_dotenv(PIPELINE_DIR / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def run_train_script():
    """Execute train.py and capture output."""
    try:
        result = subprocess.run(
            [sys.executable, str(TRAIN_FILE)],
            capture_output=True, text=True, timeout=300,
            cwd=str(AUTORESEARCH_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode != 0:
            return None, result.stderr[:1000]
        # Parse JSON output
        output = result.stdout.strip()
        # Find last JSON block in output
        for line in reversed(output.split("\n")):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line), None
                except json.JSONDecodeError:
                    pass
        # Try parsing entire output
        return json.loads(output), None
    except subprocess.TimeoutExpired:
        return None, "Experiment timed out (>300s)"
    except Exception as e:
        return None, str(e)


def call_claude(prompt):
    """Call Claude API to generate new train.py code."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def build_prompt(experiment_num, current_best, history_summary, program_md, current_train_py):
    """Build the prompt for Claude to generate the next experiment."""
    return f"""You are an ML researcher running autonomous experiments to improve a correlation break detection model.

## Research Program
{program_md}

## Current Best Results
{json.dumps(current_best, indent=2) if current_best else "No results yet — this is the first experiment."}

## Experiment History Summary
{history_summary}

## Current train.py
```python
{current_train_py}
```

## Your Task
This is experiment #{experiment_num}. Modify train.py to try a DIFFERENT approach that might improve F1 score.

Rules:
1. You MUST keep the same function signature: `def run_experiment() -> dict` returning {{"metrics": ..., "model_config": ...}}
2. You MUST use `from prepare import load_data, split_data, evaluate` — do NOT modify the data loading or evaluation
3. You MUST call `evaluate(y_test, y_pred, y_prob)` for metrics (y_prob can be None for non-probabilistic models)
4. Try ONE specific change per experiment — don't combine too many changes
5. Update the "notes" field in model_config to describe what you tried
6. Import any sklearn/xgboost/lightgbm/imblearn modules you need at the top

Return ONLY the complete train.py file content. No explanation, no markdown fences, just the Python code."""


def get_history_summary():
    """Build a concise summary of past experiments."""
    results = sorted(RESULTS_DIR.glob("experiment-*.json"))
    if not results:
        return "No experiments run yet."

    lines = []
    for r in results[-10:]:  # Last 10
        data = json.loads(r.read_text(encoding="utf-8"))
        m = data.get("metrics", {})
        desc = data.get("description", "")[:60]
        best_marker = " *** NEW BEST ***" if data.get("is_new_best") else ""
        f1 = m.get("f1_score", 0)
        prec = m.get("precision", 0)
        rec = m.get("recall", 0)
        f1_opt = m.get("f1_at_optimal", f1)
        lines.append(
            f"  #{data.get('experiment', 0):03d}: F1={f1:.4f} F1@opt={f1_opt:.4f} "
            f"Prec={prec:.4f} Rec={rec:.4f} "
            f"| {desc}{best_marker}"
        )

    return f"Last {len(lines)} experiments:\n" + "\n".join(lines)


def run_baseline():
    """Run baseline experiment and save it."""
    print("=" * 60)
    print("BASELINE: Running original model...")
    print("=" * 60)

    result, error = run_train_script()
    if error:
        print(f"ERROR: {error}")
        return None

    metrics = result["metrics"]
    config = result["model_config"]

    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1 Score:  {metrics['f1_score']:.4f}")

    if metrics.get("f1_at_optimal"):
        print(f"  F1 @ optimal threshold ({metrics['optimal_threshold']}): {metrics['f1_at_optimal']:.4f}")

    # Save baseline
    from prepare import save_baseline, save_result
    save_baseline(metrics)
    save_result(0, "Baseline — original XGBoost", metrics, config, is_new_best=True)

    return {"metrics": metrics, "model_config": config}


def run_loop(n_experiments=50):
    """Run the full AutoResearch experiment loop."""
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return

    program_md = PROGRAM_FILE.read_text(encoding="utf-8")

    # Step 1: Run baseline
    if not BASELINE_FILE.exists():
        baseline = run_baseline()
        if not baseline:
            return
        current_best = baseline
        start_exp = 1
    else:
        from prepare import get_current_best, load_baseline
        current_best = get_current_best()
        baseline_data = load_baseline()
        # Find last experiment number
        existing = sorted(RESULTS_DIR.glob("experiment-*.json"))
        start_exp = len(existing)

    best_f1 = current_best["metrics"]["f1_score"]
    if current_best["metrics"].get("f1_at_optimal"):
        best_f1 = max(best_f1, current_best["metrics"]["f1_at_optimal"])

    print(f"\nStarting AutoResearch loop: {n_experiments} experiments")
    print(f"Current best F1: {best_f1:.4f}")
    print("=" * 60)

    # Backup original train.py
    original_train = TRAIN_FILE.read_text(encoding="utf-8")

    for i in range(start_exp, start_exp + n_experiments):
        print(f"\n--- Experiment #{i:03d} ---")

        # Build prompt
        current_train = TRAIN_FILE.read_text(encoding="utf-8")
        history = get_history_summary()
        prompt = build_prompt(i, current_best, history, program_md, current_train)

        # Get new train.py from Claude
        try:
            new_code = call_claude(prompt)
            # Clean up: remove markdown fences if present
            if new_code.startswith("```"):
                lines = new_code.split("\n")
                new_code = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        except Exception as e:
            print(f"  Claude API error: {e}")
            time.sleep(5)
            continue

        # Save backup and write new code
        backup = current_train
        TRAIN_FILE.write_text(new_code, encoding="utf-8")

        # Run experiment
        result, error = run_train_script()

        if error:
            print(f"  FAILED: {error[:200]}")
            TRAIN_FILE.write_text(backup, encoding="utf-8")
            from prepare import save_result
            save_result(i, f"FAILED: {error[:100]}", {"f1_score": 0}, {"error": error[:500]})
            continue

        metrics = result["metrics"]
        config = result["model_config"]
        desc = config.get("notes", "No description")

        # Compare F1 (use optimal threshold F1 if available)
        exp_f1 = metrics.get("f1_at_optimal", metrics["f1_score"])

        is_new_best = exp_f1 > best_f1

        print(f"  {desc[:60]}")
        print(f"  F1={metrics['f1_score']:.4f} Prec={metrics['precision']:.4f} Rec={metrics['recall']:.4f}", end="")
        if metrics.get("f1_at_optimal"):
            print(f" | F1@opt={metrics['f1_at_optimal']:.4f} (thresh={metrics['optimal_threshold']})", end="")

        if is_new_best:
            print(f"  *** NEW BEST (was {best_f1:.4f}) ***")
            best_f1 = exp_f1
            current_best = {"metrics": metrics, "model_config": config}
        else:
            print(f"  (no improvement over {best_f1:.4f})")
            # Revert train.py to last best version
            TRAIN_FILE.write_text(backup, encoding="utf-8")

        from prepare import save_result
        save_result(i, desc, metrics, config, is_new_best=is_new_best)

        # Brief pause to avoid API rate limits
        time.sleep(2)

    # Final summary
    from prepare import load_baseline
    baseline_data = load_baseline()
    print("\n" + "=" * 60)
    print("AUTORESEARCH COMPLETE")
    print("=" * 60)
    print(f"Experiments run: {n_experiments}")
    print(f"\nBASELINE (before):")
    bm = baseline_data["metrics"]
    print(f"  F1={bm['f1_score']:.4f} Prec={bm['precision']:.4f} Rec={bm['recall']:.4f} Acc={bm['accuracy']:.4f}")
    print(f"\nBEST (after):")
    cm = current_best["metrics"]
    print(f"  F1={cm.get('f1_at_optimal', cm['f1_score']):.4f} Prec={cm.get('precision_at_optimal', cm['precision']):.4f} Rec={cm.get('recall_at_optimal', cm['recall']):.4f} Acc={cm['accuracy']:.4f}")
    print(f"  Config: {current_best['model_config'].get('notes', '')}")

    improvement = ((cm.get("f1_at_optimal", cm["f1_score"]) - bm["f1_score"]) / max(bm["f1_score"], 0.001)) * 100
    print(f"\n  F1 improvement: {improvement:+.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoResearch Experiment Loop")
    parser.add_argument("--n", type=int, default=50, help="Number of experiments")
    parser.add_argument("--baseline-only", action="store_true", help="Only run baseline")
    args = parser.parse_args()

    if args.baseline_only:
        run_baseline()
    else:
        run_loop(n_experiments=args.n)
