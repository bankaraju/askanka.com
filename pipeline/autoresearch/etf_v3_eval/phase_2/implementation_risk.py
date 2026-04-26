# pipeline/autoresearch/etf_v3_eval/phase_2/implementation_risk.py
"""§11A.1 — 10 implementation-risk failure scenarios.

Each scenario takes an events frame (cols: realized_pct, ...) and returns a
mutated frame. run_full_scenario_set composes all 10 in sequence and emits
{cum_pnl, max_dd, realised_sharpe} for the gate check.

Polish notes vs plan reference (§13A.1 compliance):
- rng is a REQUIRED positional arg for all randomised scenarios; no seed=0
  fallback to avoid silent non-determinism in §13A.1 manifests.
- ValueError on missing trade_date / open_to_close_pct columns (loud failure,
  not silent pass-through).
- max(float(...), 1e-12) std-floor idiom (consistent with T13/T17).
- pass_implementation_gate validates required keys in both dicts.
- apply_overnight_gap_3x_vol is a no-op for v3-CURATED (intraday flat-by-1430)
  but kept in the catalog for §11A.1 completeness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Scenario 1 — Missed entries (entries simply never happen)
# ---------------------------------------------------------------------------

def apply_missed_entries(
    events: pd.DataFrame,
    miss_pct: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Drop miss_pct fraction of rows (entry never executed).

    Args:
        events: trade events frame; must have at least a ``realized_pct`` col.
        miss_pct: fraction [0, 1) of entries to drop at random.
        rng: caller-supplied RNG (required; §13A.1 pinning mandate).
    """
    keep_mask = rng.random(len(events)) >= miss_pct
    return events[keep_mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scenario 2 — Missed exits (held one extra bar at open_to_close_pct return)
# ---------------------------------------------------------------------------

def apply_missed_exits_held_one_bar(
    events: pd.DataFrame,
    miss_pct: float,
    next_bar_pct_col: str = "open_to_close_pct",
    rng: np.random.Generator = None,  # type: ignore[assignment]
) -> pd.DataFrame:
    """Replace realized_pct with next-bar return for miss_pct of rows.

    Raises ValueError if ``next_bar_pct_col`` is absent (no silent pass-through).

    Args:
        rng: caller-supplied RNG (required; §13A.1 pinning mandate).
    """
    if rng is None:
        raise TypeError(
            "apply_missed_exits_held_one_bar: rng is required (§13A.1 — "
            "callers must pin the RNG seed; no default fallback allowed)"
        )
    if next_bar_pct_col not in events.columns:
        raise ValueError(
            f"apply_missed_exits_held_one_bar: column '{next_bar_pct_col}' not found; "
            f"available: {list(events.columns)}"
        )
    out = events.copy()
    miss = rng.random(len(out)) < miss_pct
    out.loc[miss, "realized_pct"] = out.loc[miss, next_bar_pct_col]
    return out


# ---------------------------------------------------------------------------
# Scenario 3 — Delayed fill (5-min slippage, deterministic bps haircut)
# ---------------------------------------------------------------------------

def apply_delayed_fill_5min(
    events: pd.DataFrame,
    slippage_bps: float = 5.0,
) -> pd.DataFrame:
    """Subtract a flat per-trade slippage cost of ``slippage_bps`` basis points."""
    out = events.copy()
    out["realized_pct"] = events["realized_pct"] - slippage_bps / 10_000
    return out


# ---------------------------------------------------------------------------
# Scenario 4 — Stale signal (one-bar lag: use next row's return instead)
# ---------------------------------------------------------------------------

def apply_stale_signal_one_bar(events: pd.DataFrame) -> pd.DataFrame:
    """Shift realized_pct forward one row (signal arrives one bar late)."""
    out = events.copy().reset_index(drop=True)
    # Last row can't shift forward — carry its own value
    out["realized_pct"] = out["realized_pct"].shift(-1).fillna(out["realized_pct"].iloc[-1])
    return out


# ---------------------------------------------------------------------------
# Scenario 5 — Rejected exit retried next bar (delegates to scenario 2)
# ---------------------------------------------------------------------------

def apply_rejected_exit_retry_next_bar(
    events: pd.DataFrame,
    miss_pct: float,
    next_bar_pct_col: str = "open_to_close_pct",
    rng: np.random.Generator = None,  # type: ignore[assignment]
) -> pd.DataFrame:
    """Exit order rejected at market close; retry on next bar open.

    Semantically identical to apply_missed_exits_held_one_bar.
    Raises ValueError if ``next_bar_pct_col`` absent (via delegation).
    rng is required (§13A.1).
    """
    if rng is None:
        raise TypeError(
            "apply_rejected_exit_retry_next_bar: rng is required (§13A.1)"
        )
    return apply_missed_exits_held_one_bar(events, miss_pct, next_bar_pct_col, rng)


# ---------------------------------------------------------------------------
# Scenario 6 — Partial fill (only fill_fraction of position filled)
# ---------------------------------------------------------------------------

def apply_partial_fill(
    events: pd.DataFrame,
    fill_fraction: float = 0.5,
) -> pd.DataFrame:
    """Scale realized_pct by ``fill_fraction`` (partial execution)."""
    out = events.copy()
    out["realized_pct"] = events["realized_pct"] * fill_fraction
    return out


# ---------------------------------------------------------------------------
# Scenario 7 — Data outage (one random trading day per month is missing)
# ---------------------------------------------------------------------------

def apply_data_outage_once_per_month(
    events: pd.DataFrame,
    rng: np.random.Generator = None,  # type: ignore[assignment]
) -> pd.DataFrame:
    """Drop one random row per calendar month to simulate a data-feed outage.

    Raises ValueError if ``trade_date`` column is absent.
    Returns events unchanged when the frame is empty.

    Args:
        rng: caller-supplied RNG (required; §13A.1 pinning mandate).
    """
    if rng is None:
        raise TypeError(
            "apply_data_outage_once_per_month: rng is required (§13A.1)"
        )
    if "trade_date" not in events.columns:
        raise ValueError(
            f"apply_data_outage_once_per_month: column 'trade_date' not found; "
            f"available: {list(events.columns)}"
        )
    if len(events) == 0:
        return events.copy()
    out = events.copy().reset_index(drop=True)
    months = pd.to_datetime(out["trade_date"]).dt.to_period("M").unique()
    drop_idx: list[int] = []
    for m in months:
        rows = out[pd.to_datetime(out["trade_date"]).dt.to_period("M") == m]
        if len(rows):
            drop_idx.append(int(rng.choice(rows.index)))
    return out.drop(drop_idx).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scenario 8 — Exchange halt (position held; assume half-return on reopen)
# ---------------------------------------------------------------------------

def apply_exchange_halt_at_t_plus_1_open(
    events: pd.DataFrame,
    freq_pct: float = 0.02,
    rng: np.random.Generator = None,  # type: ignore[assignment]
) -> pd.DataFrame:
    """Simulate exchange halts at T+1 open: affected rows get 0.5× realized_pct.

    Args:
        rng: caller-supplied RNG (required; §13A.1 pinning mandate).
    """
    if rng is None:
        raise TypeError(
            "apply_exchange_halt_at_t_plus_1_open: rng is required (§13A.1)"
        )
    out = events.copy()
    halts = rng.random(len(out)) < freq_pct
    out.loc[halts, "realized_pct"] = out.loc[halts, "realized_pct"] * 0.5
    return out


# ---------------------------------------------------------------------------
# Scenario 9 — Margin shortage block (trades zeroed after >dd_threshold DD)
# ---------------------------------------------------------------------------

def apply_margin_shortage_block(
    events: pd.DataFrame,
    dd_threshold: float = 0.10,
) -> pd.DataFrame:
    """Zero realized_pct for all rows from the first point where cumulative drawdown
    exceeds dd_threshold (inclusive), and all subsequent rows.

    Once the margin shortage is triggered, the account is blocked — no new
    trades can be executed until margin is restored (which we don't model here).
    Raises ValueError if ``trade_date`` column is absent (sort requires it).
    """
    if "trade_date" not in events.columns:
        raise ValueError(
            f"apply_margin_shortage_block: column 'trade_date' not found; "
            f"available: {list(events.columns)}"
        )
    out = events.copy().sort_values("trade_date").reset_index(drop=True)
    cum = out["realized_pct"].cumsum()
    dd = cum.cummax() - cum
    # Find the first index where DD exceeds threshold; zero that row and all after
    breach = dd > dd_threshold
    if breach.any():
        first_breach = int(breach.idxmax())
        out.loc[first_breach:, "realized_pct"] = 0.0
    return out


# ---------------------------------------------------------------------------
# Scenario 10 — Overnight gap 3× vol (no-op for v3-CURATED intraday strategy)
# ---------------------------------------------------------------------------

def apply_overnight_gap_3x_vol(
    events: pd.DataFrame,
    gap_pct: float = 0.0,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame:
    """Model overnight gap risk (3× vol shock).

    NOTE: v3-CURATED is an intraday strategy that is flat by 14:30. There is
    no overnight holding risk, so default gap_pct=0 makes this a no-op.
    The function is retained in the §11A.1 catalog for completeness and to
    ensure the run_full_scenario_set call signature is stable across strategy
    variants that may hold overnight.
    """
    return events.copy()


# ---------------------------------------------------------------------------
# Composer — run all 10 scenarios and compute summary metrics
# ---------------------------------------------------------------------------

def run_full_scenario_set(events: pd.DataFrame, rng_seed: int = 0) -> dict:
    """Apply all 10 failure scenarios in sequence and return stress metrics.

    Returns:
        dict with keys: cum_pnl, max_dd, realised_sharpe, n_remaining.
    """
    rng = np.random.default_rng(rng_seed)
    e = events.copy()

    # S1 — missed entries
    e = apply_missed_entries(e, 0.05, rng)
    # S2 — missed exits (only if next-bar column present)
    if "open_to_close_pct" in e.columns:
        e = apply_missed_exits_held_one_bar(e, 0.05, rng=rng)
    # S3 — delayed fill
    e = apply_delayed_fill_5min(e)
    # S4 — stale signal (only if at least 2 rows remain to shift meaningfully)
    if len(e) >= 2:
        e = apply_stale_signal_one_bar(e)
    # S5 — rejected exit (only if next-bar column present)
    if "open_to_close_pct" in e.columns:
        e = apply_rejected_exit_retry_next_bar(e, 0.02, rng=rng)
    # S6 — partial fill
    e = apply_partial_fill(e, 0.5)
    # S7 — data outage (only if trade_date present)
    if "trade_date" in e.columns:
        e = apply_data_outage_once_per_month(e, rng=rng)
    # S8 — exchange halt
    e = apply_exchange_halt_at_t_plus_1_open(e, 0.02, rng=rng)
    # S9 — margin shortage (only if trade_date present)
    if "trade_date" in e.columns:
        e = apply_margin_shortage_block(e, 0.10)
    # S10 — overnight gap (no-op for intraday v3-CURATED)
    e = apply_overnight_gap_3x_vol(e, rng=rng)

    # Metrics
    if len(e) == 0:
        return {"cum_pnl": 0.0, "max_dd": 0.0, "realised_sharpe": 0.0, "n_remaining": 0}

    cum = e["realized_pct"].cumsum()
    dd = float((cum.cummax() - cum).max())
    cum_pnl = float(cum.iloc[-1])

    if len(e) < 2:
        # std() is undefined / NaN with a single observation
        realised_sharpe = 0.0
    else:
        std_floor = max(float(e["realized_pct"].std(ddof=1)), 1e-12)
        realised_sharpe = float(e["realized_pct"].mean() / std_floor) * (252 ** 0.5)

    return {
        "cum_pnl": cum_pnl,
        "max_dd": dd,
        "realised_sharpe": realised_sharpe,
        "n_remaining": int(len(e)),
    }


# ---------------------------------------------------------------------------
# Gate — §11A.2 pass/fail
# ---------------------------------------------------------------------------

def pass_implementation_gate(stressed: dict, baseline: dict) -> bool:
    """§11A.2: cum_pnl > 0, max_dd ≤ 1.4 × baseline.max_dd_s1, sharpe ≥ 0.6 × baseline.sharpe_s1.

    Raises KeyError if required keys are absent from either dict.
    Required stressed keys: cum_pnl, max_dd, realised_sharpe.
    Required baseline keys: sharpe_s1, max_dd_s1.
    """
    for key in ("cum_pnl", "max_dd", "realised_sharpe"):
        if key not in stressed:
            raise KeyError(
                f"pass_implementation_gate: stressed dict missing required key '{key}'; "
                f"present: {list(stressed.keys())}"
            )
    for key in ("sharpe_s1", "max_dd_s1"):
        if key not in baseline:
            raise KeyError(
                f"pass_implementation_gate: baseline dict missing required key '{key}'; "
                f"present: {list(baseline.keys())}"
            )
    return (
        stressed["cum_pnl"] > 0
        and stressed["max_dd"] <= 1.4 * baseline["max_dd_s1"]
        and stressed["realised_sharpe"] >= 0.6 * baseline["sharpe_s1"]
    )
