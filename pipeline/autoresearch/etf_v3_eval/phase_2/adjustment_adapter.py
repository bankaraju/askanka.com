"""§10 single-convention adjustment adapter.

Phase 2 reads minute bars unadjusted (Kite default) and explicitly unadjusts the
EOD comparison series so reconciliation under §13 measures real divergence, not
mixed-convention ghosts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class AdjustmentEvent:
    symbol: str
    event_date: date
    kind: str
    ratio: float

    def __post_init__(self) -> None:
        if self.ratio <= 0:
            raise ValueError(f"AdjustmentEvent ratio must be > 0, got {self.ratio}")


def unadjust_eod_series(eod: pd.DataFrame, events: Iterable[AdjustmentEvent]) -> pd.DataFrame:
    """Convert auto-adjusted EOD closes to unadjusted by multiplying pre-event
    rows by the event ratio (cumulative if multiple events).
    """
    df = eod.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for ev in events:
        if ev.kind in ("split", "bonus"):
            mask = df["trade_date"] < ev.event_date
            df.loc[mask, "close"] = df.loc[mask, "close"] * ev.ratio
    return df
