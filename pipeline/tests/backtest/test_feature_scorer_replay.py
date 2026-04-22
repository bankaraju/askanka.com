"""Full-universe fit against live historical data. Emits CSV summary.

Success criterion from spec §14:
  - >=70% of F&O universe has GREEN or AMBER model
  - remaining RED/UNAVAILABLE tickers are documented

NOTE: FNO historical data as of 2026-04-22 only spans ~1 year; walk_forward
requires 2 years. Coverage assertion is CONDITIONAL — it skips gracefully
when the available history is too thin to fairly judge the model. Rerun
after `python -m pipeline.download_fno_history --days 1825` restores 5y
history.
"""
import csv
import json
from pathlib import Path
import pandas as pd
import pytest


def _median_history_rows() -> int:
    """Median number of rows per ticker CSV in fno_historical/. Informs the skip gate."""
    hist_dir = Path("pipeline/data/fno_historical")
    if not hist_dir.exists():
        return 0
    counts = []
    for p in hist_dir.glob("*.csv"):
        try:
            counts.append(sum(1 for _ in p.open("r", encoding="utf-8")) - 1)
        except Exception:
            continue
    if not counts:
        return 0
    counts.sort()
    return counts[len(counts) // 2]


@pytest.mark.slow
def test_feature_scorer_universe_fit_coverage():
    from pipeline.feature_scorer.fit_universe import main as fit_main
    exit_code = fit_main()
    assert exit_code == 0

    models_file = Path("pipeline/data/ticker_feature_models.json")
    assert models_file.exists()
    data = json.loads(models_file.read_text(encoding="utf-8"))
    models = data["models"]
    n_total = len(models)
    n_green = sum(1 for m in models.values() if m.get("health") == "GREEN")
    n_amber = sum(1 for m in models.values() if m.get("health") == "AMBER")
    n_red = sum(1 for m in models.values() if m.get("health") == "RED")
    n_unav = sum(1 for m in models.values() if m.get("health") == "UNAVAILABLE")

    # Emit per-ticker CSV (always — useful even when the assertion skips)
    out_csv = Path(f"backtest_results/feature_scorer_fit_{data['fitted_at'][:10]}.csv")
    out_csv.parent.mkdir(exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "health", "source", "mean_auc", "min_fold_auc",
                    "n_folds", "fallback_cohort"])
        for t, m in models.items():
            w.writerow([
                t, m.get("health"), m.get("source"),
                m.get("mean_auc"), m.get("min_fold_auc"),
                len(m.get("folds", [])),
                m.get("fallback_cohort"),
            ])

    coverage = (n_green + n_amber) / max(n_total, 1)
    print(f"\nUNIVERSE SIZE: {n_total}")
    print(f"GREEN: {n_green} | AMBER: {n_amber} | RED: {n_red} | UNAVAILABLE: {n_unav}")
    print(f"COVERAGE (GREEN+AMBER): {coverage:.1%}")
    print(f"CSV: {out_csv}")

    median_rows = _median_history_rows()
    if median_rows < 500:
        pytest.skip(
            f"fno_historical median depth {median_rows} rows < 500 minimum for "
            f"walk_forward. Rerun after `python -m pipeline.download_fno_history "
            f"--days 1825` extends history to 5y. Coverage snapshot still in CSV."
        )

    if n_total < 50:
        pytest.skip(f"universe too small ({n_total}) to judge coverage")
    assert coverage >= 0.70, f"coverage {coverage:.1%} below 70% target"
