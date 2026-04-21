"""Cross-variant Sharpe / hit-rate / Bonferroni comparison."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline.research.phase_c_backtest import stats as v4_stats


def compute_comparison(ledger_map: dict[str, pd.DataFrame],
                        n_tests: int = 12,
                        alpha_family: float = 0.01) -> pd.DataFrame:
    """Compute cross-variant comparison stats (Sharpe, hit rate, binomial p, Bonferroni).

    Args:
        ledger_map: dict of variant_name -> ledger DataFrame with columns:
                    'notional_total_inr', 'pnl_net_inr'
        n_tests: number of tests for Bonferroni family correction
        alpha_family: family-wise error rate (e.g., 0.01)

    Returns:
        DataFrame with one row per variant, columns:
        variant, n_trades, wins, hit_rate, sharpe_point, sharpe_lo, sharpe_hi,
        binomial_p, alpha_per_test, passes
    """
    alpha_per = v4_stats.bonferroni_alpha_per(alpha_family, n_tests)
    rows: list[dict] = []
    for variant, ledger in ledger_map.items():
        if ledger.empty:
            rows.append({"variant": variant, "n_trades": 0, "passes": False,
                         "reason": "empty ledger"})
            continue
        returns = (ledger["pnl_net_inr"] / ledger["notional_total_inr"]).values
        wins = int((returns > 0).sum())
        n = int(len(returns))
        point, lo, hi = v4_stats.bootstrap_sharpe_ci(returns, seed=7)
        p_value = v4_stats.binomial_p(wins, n)
        rows.append({
            "variant": variant, "n_trades": n, "wins": wins,
            "hit_rate": wins / n, "sharpe_point": point,
            "sharpe_lo": lo, "sharpe_hi": hi, "binomial_p": p_value,
            "alpha_per_test": alpha_per,
            "passes": lo > 0 and p_value < alpha_per,
        })
    return pd.DataFrame(rows)


def load_ledgers_from_dir(path: Path) -> dict[str, pd.DataFrame]:
    """Load all parquet ledgers from directory, keyed by stem."""
    out: dict[str, pd.DataFrame] = {}
    for f in sorted(Path(path).glob("*.parquet")):
        out[f.stem] = pd.read_parquet(f)
    return out
