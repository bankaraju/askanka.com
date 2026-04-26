"""§6.3 marker: zone change yesterday → today flag.

Rationale: regime transitions historically carry asymmetric P&L. Flag the day's
events as in-transition when the v3 zone differs from the previous trading day's.
"""
from __future__ import annotations

import pandas as pd


def flag_regime_transitions(zones: pd.DataFrame) -> pd.DataFrame:
    """Add ``transition`` bool column flagging dates where ``zone`` changed.

    Input: ``zones`` with cols [trade_date, zone].
    Output: same frame sorted by ``trade_date`` with a ``transition`` bool column.
    The first row has no prior to compare against and is always ``False``.
    """
    df = zones.sort_values("trade_date").reset_index(drop=True).copy()
    df["transition"] = df["zone"] != df["zone"].shift(1)
    if len(df) > 0:
        df.loc[0, "transition"] = False
    return df
