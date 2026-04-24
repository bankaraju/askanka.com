"""strategy_results_10 loader + per-regime incumbent mean Sharpe helper.

v2: scarcity-fallback removed. Every proposal now gets a
construction-matched null-basket hurdle via `load_null_basket_hurdle`
at the proposal call-site (run_pilot._compute_hurdle). This module
retains `hurdle_sharpe_for_regime` only for incumbent-audit scripts
that still want to report the per-regime incumbent mean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import DATA_DIR

TABLE_PATH = DATA_DIR / "strategy_results_10.json"


def load_table(path: Path = TABLE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_incumbents_for_regime(table: dict, regime: str) -> list[dict]:
    """Incumbents with a clean Sharpe CI in this regime."""
    rows = []
    for inc in table.get("incumbents", []):
        cell = inc.get("per_regime", {}).get(regime, {})
        if (cell.get("status_flag") != "INSUFFICIENT_POWER"
                and cell.get("sharpe_ci_low") is not None
                and cell["sharpe_ci_low"] > 0):
            rows.append({**inc, "cell": cell})
    return rows


def hurdle_sharpe_for_regime(table: dict, regime: str) -> tuple[float, str]:
    """v2: return mean-of-clean-incumbents Sharpe; scarcity fallback removed.

    Every proposal now gets a construction-matched null-basket hurdle via
    `load_null_basket_hurdle` at the proposal call-site. This helper is
    retained only for incumbent-audit scripts that still want to report
    the per-regime incumbent mean.
    """
    clean = clean_incumbents_for_regime(table, regime)
    if not clean:
        return (0.0, "no_incumbent")
    return (float(sum(r["cell"]["sharpe_point"] for r in clean) / len(clean)),
            "mean_of_incumbents")
