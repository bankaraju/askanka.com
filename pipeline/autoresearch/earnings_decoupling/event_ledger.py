"""Construct candidate-trade ledger from earnings events + features.

Gate order is intentional and preserves the FAIL-mode autopsy diagnostic:
PIT → sector → trigger_z → trigger_threshold → macro_filter. We compute
the z-score BEFORE the macro check so the funnel records "how many events
would have triggered in a quiet macro" — the runner reports this as a
contamination map per data-validation policy §14. Macro-first ordering
would optimise CPU but destroy the diagnostic; do not reorder.
"""
from __future__ import annotations

import pandas as pd

from .universe import is_in_fno
from .peer_residuals import compute_log_returns, compute_residual_panel
from .trigger import compute_trigger_z
from .macro_filter_adapter import compute_index_returns_panel, is_event_macro_excluded

TRIGGER_Z_THRESHOLD = 1.5


def build_event_ledger(
    *,
    events: pd.DataFrame,
    prices: pd.DataFrame,
    sector_idx: pd.DataFrame,
    vix: pd.Series,
    fno_history: list[dict],
    peers_map: dict[str, list[str]],
    sector_map: dict[str, str],
    trigger_z_threshold: float = TRIGGER_Z_THRESHOLD,
) -> pd.DataFrame:
    log_rets = compute_log_returns(prices)
    residual_panel = compute_residual_panel(log_rets, peers_map)
    sector_rets = compute_index_returns_panel(sector_idx)

    rows = []
    for _, ev in events.iterrows():
        sym = ev["symbol"]
        ev_date = ev["event_date"]
        row = {"ticker": sym, "event_date": ev_date}

        if not is_in_fno(fno_history, sym, ev_date):
            row["status"] = "DROPPED_PIT_MISS"
            rows.append(row); continue

        if sym not in sector_map:
            row["status"] = "DROPPED_NO_SECTOR_MAP"
            rows.append(row); continue
        sec_index = sector_map[sym]
        if sec_index not in sector_rets.columns:
            row["status"] = "DROPPED_NO_SECTOR_DATA"
            rows.append(row); continue

        z = compute_trigger_z(residual_panel, sym, ev_date)
        if z is None:
            row["status"] = "DROPPED_INSUFFICIENT_BASELINE"
            rows.append(row); continue
        row["trigger_z"] = z
        if abs(z) < trigger_z_threshold:
            row["status"] = "DROPPED_NO_TRIGGER"
            rows.append(row); continue

        excluded, reason = is_event_macro_excluded(
            event_date=ev_date,
            sector_index_returns=sector_rets[sec_index],
            india_vix=vix,
        )
        if excluded:
            row["status"] = "EXCLUDED_MACRO"
            row["exclusion_reason"] = reason
            rows.append(row); continue

        row["status"] = "CANDIDATE"
        row["direction"] = "LONG" if z > 0 else "SHORT"
        row["sector_index"] = sec_index
        rows.append(row)

    return pd.DataFrame(rows)
