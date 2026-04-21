"""V5.3 — NIFTY beta overlay. Same as V5.2 but always hedges with NIFTY."""
from __future__ import annotations

import pandas as pd

from pipeline.research.phase_c_v5.variants.v52_stock_vs_index import run as _v52_run


def run(signals: pd.DataFrame, symbol_bars: dict[str, pd.DataFrame],
        hold_days: int = 1) -> pd.DataFrame:
    """Override sector_index to NIFTY for every signal, then reuse V5.2."""
    if signals.empty:
        return signals.copy()
    overridden = signals.copy()
    overridden["sector_index"] = "NIFTY"
    ledger = _v52_run(signals=overridden, symbol_bars=symbol_bars, hold_days=hold_days)
    if not ledger.empty:
        ledger["variant"] = "v53"
    return ledger
