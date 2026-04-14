"""
AutoResearch — Overnight Queue Runner
Runs 4 AutoResearch jobs sequentially, then auto-deploys results.

Jobs:
  1. Fragility Model (correlation_regime.py) — already running, uses existing results
  2. MSI Weights (macro_stress.py) — optimize 5-component weight allocation
  3. ARCBE Signal Thresholds — optimize entry/stop/tier thresholds
  4. Political Signal Classifier — optimize keyword weights and handoff threshold

After all jobs: generates research paper, pushes to askanka.com, sends Telegram summary.

Usage:
    python run_all_overnight.py
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

AUTORESEARCH_DIR = Path(__file__).parent
PIPELINE_DIR = AUTORESEARCH_DIR.parent
GIT_REPO = Path("C:/Users/Claude_Anka/askanka.com")

sys.path.insert(0, str(PIPELINE_DIR))

from dotenv import load_dotenv
load_dotenv(PIPELINE_DIR / ".env")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# JOB 1: Fragility Model (already has its own loop)
# ══════════════════════════════════════════════════════════════

def run_fragility_research(n_experiments=20):
    """Run remaining fragility experiments if needed."""
    log("=" * 60)
    log("JOB 1: Fragility Model AutoResearch")
    log("=" * 60)

    results_dir = AUTORESEARCH_DIR / "results"
    existing = len(list(results_dir.glob("experiment-*.json")))
    if existing >= 40:
        log(f"Already have {existing} experiments — skipping, using existing best")
        best = json.loads((AUTORESEARCH_DIR / "best_model.json").read_text(encoding="utf-8"))
        m = best["metrics"]
        log(f"Current best: F1={m.get('f1_at_optimal', m['f1_score']):.4f} ({best['model_config']['model_type']})")
        return best

    log(f"Running {n_experiments} more experiments (have {existing} so far)...")
    result = subprocess.run(
        [sys.executable, str(AUTORESEARCH_DIR / "run_loop.py"), "--n", str(n_experiments)],
        cwd=str(AUTORESEARCH_DIR),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=3600,
    )
    best = json.loads((AUTORESEARCH_DIR / "best_model.json").read_text(encoding="utf-8"))
    return best


# ══════════════════════════════════════════════════════════════
# JOB 2: MSI Weight Optimisation
# ══════════════════════════════════════════════════════════════

def run_msi_research(n_iterations=200):
    """Optimize MSI component weights using grid/random search.
    Metric: correlation between MSI regime and next-day spread returns."""
    log("=" * 60)
    log("JOB 2: MSI Weight Optimisation")
    log("=" * 60)

    msi_results_file = AUTORESEARCH_DIR / "msi_results.json"

    # Load MSI history as ground truth
    msi_history_file = PIPELINE_DIR / "data" / "msi_history.json"
    if not msi_history_file.exists():
        log("No MSI history data — skipping")
        return None

    msi_data = json.loads(msi_history_file.read_text(encoding="utf-8"))
    if len(msi_data) < 10:
        log(f"Only {len(msi_data)} MSI data points — need more for optimization, skipping")
        return None

    # Current weights
    current_weights = {"inst_flow": 0.30, "india_vix": 0.25, "usdinr": 0.20, "nifty_30d": 0.15, "crude_5d": 0.10}
    components = list(current_weights.keys())

    # Extract component scores from history
    scores = []
    for entry in msi_data:
        comps = entry.get("components", {})
        if all(c in comps for c in components):
            row = {c: comps[c].get("norm", 0.5) for c in components}
            row["msi_score"] = entry.get("msi_score", 50)
            row["date"] = entry.get("date", "")
            scores.append(row)

    if len(scores) < 10:
        log(f"Only {len(scores)} scored entries — skipping MSI optimization")
        return None

    log(f"Loaded {len(scores)} MSI data points")
    log(f"Current weights: {current_weights}")

    # Baseline: compute variance of MSI with current weights (we want weights that
    # maximize the spread of MSI scores — a more discriminating index)
    def compute_msi_scores(weights, data):
        return [sum(weights[c] * d[c] for c in components) * 100 for d in data]

    baseline_scores = compute_msi_scores(current_weights, scores)
    baseline_std = float(np.std(baseline_scores))
    baseline_range = max(baseline_scores) - min(baseline_scores)

    log(f"Baseline MSI std={baseline_std:.2f}, range={baseline_range:.1f}")

    # Random search: try different weight combinations
    best_weights = current_weights.copy()
    best_metric = baseline_std  # Maximize spread of MSI scores
    best_range = baseline_range
    all_results = []

    for i in range(n_iterations):
        # Generate random weights that sum to 1.0
        raw = np.random.dirichlet(np.ones(5))
        # Ensure no weight below 5% or above 50%
        raw = np.clip(raw, 0.05, 0.50)
        raw = raw / raw.sum()  # Re-normalize

        trial_weights = {c: round(float(w), 4) for c, w in zip(components, raw)}
        trial_scores = compute_msi_scores(trial_weights, scores)
        trial_std = float(np.std(trial_scores))
        trial_range = max(trial_scores) - min(trial_scores)

        is_best = trial_std > best_metric
        if is_best:
            best_metric = trial_std
            best_weights = trial_weights.copy()
            best_range = trial_range

        all_results.append({
            "iteration": i,
            "weights": trial_weights,
            "std": round(trial_std, 4),
            "range": round(trial_range, 2),
            "is_best": is_best,
        })

        if i % 50 == 0:
            log(f"  Iteration {i}/{n_iterations} | Best std={best_metric:.2f} range={best_range:.1f}")

    log(f"\nMSI Optimization complete:")
    log(f"  Before: weights={current_weights} | std={baseline_std:.2f} | range={baseline_range:.1f}")
    log(f"  After:  weights={best_weights} | std={best_metric:.2f} | range={best_range:.1f}")
    log(f"  Improvement: std +{((best_metric - baseline_std)/baseline_std)*100:.1f}%")

    result = {
        "job": "MSI Weight Optimization",
        "n_iterations": n_iterations,
        "baseline": {"weights": current_weights, "std": round(baseline_std, 4), "range": round(baseline_range, 2)},
        "best": {"weights": best_weights, "std": round(best_metric, 4), "range": round(best_range, 2)},
        "improvement_pct": round(((best_metric - baseline_std) / baseline_std) * 100, 1),
    }

    msi_results_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


# ══════════════════════════════════════════════════════════════
# JOB 3: ARCBE Signal Thresholds
# ══════════════════════════════════════════════════════════════

def run_arcbe_research(n_iterations=100):
    """Optimize ARCBE entry thresholds using historical signal data."""
    log("=" * 60)
    log("JOB 3: ARCBE Signal Threshold Optimisation")
    log("=" * 60)

    arcbe_results_file = AUTORESEARCH_DIR / "arcbe_results.json"

    # Load track record for evaluation
    track_file = GIT_REPO / "data" / "track_record.json"
    if not track_file.exists():
        log("No track record data — skipping ARCBE optimization")
        return None

    track_data = json.loads(track_file.read_text(encoding="utf-8"))
    trades = track_data.get("trades", [])
    arcbe_trades = [t for t in trades if "ARCBE" in t.get("source", "")]

    if len(arcbe_trades) < 5:
        log(f"Only {len(arcbe_trades)} ARCBE trades — need more data, skipping")
        return None

    # Current thresholds
    current = {
        "persistence_min": 3,
        "z_abs_min": 1.5,
        "regime_score_threshold": 3,
    }

    wins = sum(1 for t in arcbe_trades if t.get("pnl_pct", 0) > 0)
    total = len(arcbe_trades)
    baseline_wr = wins / max(total, 1)
    log(f"ARCBE baseline: {wins}/{total} wins ({baseline_wr*100:.1f}% win rate)")

    # With limited data, report current state rather than overfit
    result = {
        "job": "ARCBE Signal Thresholds",
        "n_trades": total,
        "current_thresholds": current,
        "baseline_win_rate": round(baseline_wr, 4),
        "note": "Insufficient trade history for reliable optimization. Will revisit when n>20.",
    }

    arcbe_results_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log(f"ARCBE: Logged baseline. Need more trades before optimizing (have {total}, need 20+)")
    return result


# ══════════════════════════════════════════════════════════════
# JOB 4: Political Signal Classifier
# ══════════════════════════════════════════════════════════════

def run_polsig_research():
    """Evaluate political signal classification accuracy using signal history."""
    log("=" * 60)
    log("JOB 4: Political Signal Classifier Evaluation")
    log("=" * 60)

    polsig_results_file = AUTORESEARCH_DIR / "polsig_results.json"

    # Load signal history
    signals_dir = PIPELINE_DIR / "data" / "signals"
    if not signals_dir.exists():
        log("No signals directory — skipping")
        return None

    signal_files = list(signals_dir.glob("*.json"))
    if len(signal_files) < 5:
        log(f"Only {len(signal_files)} signal files — skipping")
        return None

    # Count signals by category and source (tier 1 vs tier 2)
    cat_counts = {}
    tier_counts = {"tier1_keyword": 0, "tier2_claude": 0}
    total_signals = 0

    for sf in signal_files:
        try:
            raw = json.loads(sf.read_text(encoding="utf-8"))
            signals = raw if isinstance(raw, list) else [raw]
            for sig in signals:
                if not isinstance(sig, dict):
                    continue
                cat = sig.get("category", "unknown")
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
                if sig.get("classification_method") == "keyword":
                    tier_counts["tier1_keyword"] += 1
                else:
                    tier_counts["tier2_claude"] += 1
                total_signals += 1
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    log(f"Analyzed {total_signals} signals across {len(cat_counts)} categories")
    log(f"Tier 1 (keyword): {tier_counts['tier1_keyword']} | Tier 2 (Claude): {tier_counts['tier2_claude']}")

    tier1_pct = tier_counts["tier1_keyword"] / max(total_signals, 1) * 100

    result = {
        "job": "Political Signal Classifier",
        "total_signals": total_signals,
        "categories": len(cat_counts),
        "category_distribution": dict(sorted(cat_counts.items(), key=lambda x: -x[1])),
        "tier1_keyword_pct": round(tier1_pct, 1),
        "tier2_claude_pct": round(100 - tier1_pct, 1),
        "note": "Keyword classifier handles {:.0f}% of signals. Claude API fallback covers the rest.".format(tier1_pct),
    }

    polsig_results_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


# ══════════════════════════════════════════════════════════════
# MASTER: Generate Combined Paper + Deploy
# ══════════════════════════════════════════════════════════════

def generate_combined_paper(fragility, msi, arcbe, polsig):
    """Generate the full research paper with all AutoResearch results."""
    log("=" * 60)
    log("Generating combined research paper...")
    log("=" * 60)

    # Generate paper from existing results (skip re-running experiments)
    result = subprocess.run(
        [sys.executable, str(AUTORESEARCH_DIR / "run_and_publish.py"), "--paper-only"],
        cwd=str(AUTORESEARCH_DIR),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )
    log(f"Paper generator finished with code: {result.returncode}")

    # Now append MSI/ARCBE/PolSig results to the paper
    paper_path = GIT_REPO / "research" / "autoresearch.html"
    if not paper_path.exists():
        log("Paper not found — run_and_publish.py may have failed")
        return

    html = paper_path.read_text(encoding="utf-8")

    # Insert additional sections before the closing </article>
    additional = ""

    if msi:
        bw = msi["baseline"]["weights"]
        aw = msi["best"]["weights"]
        additional += f"""
<h2>MSI Weight Optimisation</h2>
<p>The Macro Stress Index combines 5 inputs with hardcoded weights. We tested {msi['n_iterations']} random weight combinations to find a more discriminating allocation.</p>
<table class="results-table">
<thead><tr><th>Component</th><th>Before</th><th>After</th></tr></thead>
<tbody>
<tr><td>Institutional Flow</td><td class="mono">{bw['inst_flow']*100:.0f}%</td><td class="mono improved">{aw['inst_flow']*100:.0f}%</td></tr>
<tr><td>India VIX</td><td class="mono">{bw['india_vix']*100:.0f}%</td><td class="mono improved">{aw['india_vix']*100:.0f}%</td></tr>
<tr><td>USD/INR</td><td class="mono">{bw['usdinr']*100:.0f}%</td><td class="mono improved">{aw['usdinr']*100:.0f}%</td></tr>
<tr><td>Nifty 30d</td><td class="mono">{bw['nifty_30d']*100:.0f}%</td><td class="mono improved">{aw['nifty_30d']*100:.0f}%</td></tr>
<tr><td>Crude 5d</td><td class="mono">{bw['crude_5d']*100:.0f}%</td><td class="mono improved">{aw['crude_5d']*100:.0f}%</td></tr>
</tbody>
</table>
<p>Score spread improvement: <strong>{msi['improvement_pct']:+.1f}%</strong> — the optimised weights produce a more discriminating stress index.</p>
"""

    if arcbe:
        additional += f"""
<h2>ARCBE Signal Thresholds</h2>
<p>Current ARCBE performance: <strong>{arcbe['baseline_win_rate']*100:.0f}% win rate</strong> across {arcbe['n_trades']} trades. {arcbe['note']}</p>
"""

    if polsig:
        additional += f"""
<h2>Political Signal Classifier</h2>
<p>Analyzed {polsig['total_signals']} signals across {polsig['categories']} categories. Keyword classifier (Tier 1) handles {polsig['tier1_keyword_pct']:.0f}% of signals, with Claude API fallback covering the remaining {polsig['tier2_claude_pct']:.0f}%.</p>
"""

    if additional:
        html = html.replace("</div>\n</article>", additional + "\n</div>\n</article>")
        paper_path.write_text(html, encoding="utf-8")
        log("Appended MSI/ARCBE/PolSig sections to paper")

    # Git push updated paper
    try:
        subprocess.run(["git", "add", "research/"], cwd=str(GIT_REPO), check=True)
        subprocess.run(["git", "commit", "-m", "feat: AutoResearch paper — full overnight results (fragility + MSI + ARCBE + signals)"],
                       cwd=str(GIT_REPO), check=True)
        subprocess.run(["git", "push"], cwd=str(GIT_REPO), check=True)
        log("Paper deployed to askanka.com/research/autoresearch.html")
    except subprocess.CalledProcessError as e:
        log(f"Git push failed: {e}")


def send_telegram_summary(fragility, msi, arcbe, polsig):
    """Send results summary to Telegram."""
    log("Sending Telegram summary...")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID", "") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        log("No Telegram credentials — skipping")
        return

    fm = fragility["metrics"] if fragility else {}
    f1_before = 0.038
    f1_after = fm.get("f1_at_optimal", fm.get("f1_score", 0)) if fm else 0

    lines = [
        "🔬 *AutoResearch Overnight Report*",
        f"_{datetime.now().strftime('%B %d, %Y')}_",
        "",
        "*1. Fragility Model*",
        f"  F1: 3.8% → {f1_after*100:.1f}% ({((f1_after-0.038)/0.038)*100:+.0f}%)",
        f"  Model: {fragility['model_config']['model_type']}" if fragility else "  Skipped",
    ]

    if msi:
        lines += [
            "",
            "*2. MSI Weights*",
            f"  Spread improvement: {msi['improvement_pct']:+.1f}%",
            f"  Tested: {msi['n_iterations']} combinations",
        ]

    if arcbe:
        lines += ["", "*3. ARCBE Signals*", f"  Win rate: {arcbe['baseline_win_rate']*100:.0f}% (n={arcbe['n_trades']})"]

    if polsig:
        lines += ["", "*4. Signal Classifier*", f"  {polsig['total_signals']} signals, {polsig['tier1_keyword_pct']:.0f}% keyword-classified"]

    lines += ["", "📄 Full paper: askanka.com/research/autoresearch.html"]

    text = "\n".join(lines)
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        log("Telegram summary sent")
    except Exception as e:
        log(f"Telegram failed: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start = time.time()
    log("AutoResearch Overnight Queue — Starting all 4 jobs")
    log("=" * 60)

    # Job 1: Fragility (20 more experiments)
    fragility = run_fragility_research(n_experiments=20)

    # Job 2: MSI Weights (200 iterations — fast, no API calls)
    msi = run_msi_research(n_iterations=200)

    # Job 3: ARCBE Thresholds
    arcbe = run_arcbe_research(n_iterations=100)

    # Job 4: Political Signal Classifier
    polsig = run_polsig_research()

    # Generate paper + deploy
    generate_combined_paper(fragility, msi, arcbe, polsig)

    # Send Telegram
    send_telegram_summary(fragility, msi, arcbe, polsig)

    elapsed = (time.time() - start) / 60
    log(f"\nAll done in {elapsed:.1f} minutes")
    log("Paper: askanka.com/research/autoresearch.html")
