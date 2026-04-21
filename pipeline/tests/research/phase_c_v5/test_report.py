from __future__ import annotations
import pandas as pd
import pytest
from pipeline.research.phase_c_v5 import report


def test_report_markdown_has_all_12_sections(tmp_path):
    ablation_df = pd.DataFrame([
        {"variant": "v50_a", "n_trades": 100, "wins": 60, "hit_rate": 0.60,
         "sharpe_point": 1.5, "sharpe_lo": 1.0, "sharpe_hi": 2.0,
         "binomial_p": 0.001, "alpha_per_test": 0.00083, "passes": False},
    ])
    ledger_map = {"v50_a": pd.DataFrame({"pnl_net_inr": [100, -50, 200],
                                          "notional_total_inr": [50_000, 50_000, 50_000]})}
    md = report.build_markdown(ablation=ablation_df, ledger_map=ledger_map)
    for section in ("# Phase C V5", "## 1. Executive summary", "## 2. Strategy",
                    "## 3. Methodology", "## 4. Results — V5.0",
                    "## 5. Results — V5.1", "## 12. Verdict"):
        assert section in md, f"missing section: {section}"


def test_report_writes_file(tmp_path):
    ablation_df = pd.DataFrame([{"variant": "v50_a", "n_trades": 10, "wins": 6,
                                   "hit_rate": 0.6, "sharpe_point": 1.0,
                                   "sharpe_lo": 0.5, "sharpe_hi": 1.5,
                                   "binomial_p": 0.05, "alpha_per_test": 0.00083,
                                   "passes": False}])
    ledger_map = {"v50_a": pd.DataFrame({"pnl_net_inr": [1.0] * 10,
                                          "notional_total_inr": [50_000] * 10})}
    out = tmp_path / "report.md"
    report.write_report(out, ablation=ablation_df, ledger_map=ledger_map)
    assert out.is_file()
    assert "Verdict" in out.read_text(encoding="utf-8")
