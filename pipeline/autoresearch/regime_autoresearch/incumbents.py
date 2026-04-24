"""strategy_results_10 loader + per-regime hurdle + scarcity fallback."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.autoresearch.regime_autoresearch.constants import (
    INCUMBENT_SCARCITY_MIN, DATA_DIR,
)

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


def hurdle_sharpe_for_regime(table: dict, regime: str,
                              buy_hold_sharpe_fn) -> tuple[float, str]:
    """Returns (hurdle_sharpe, source)."""
    clean = clean_incumbents_for_regime(table, regime)
    if len(clean) >= INCUMBENT_SCARCITY_MIN:
        best = max(clean, key=lambda r: r["cell"]["sharpe_point"])
        return float(best["cell"]["sharpe_point"]), f"incumbent:{best['strategy_id']}"
    return buy_hold_sharpe_fn(regime), "scarcity_fallback:buy_and_hold"
