"""§9 cleanliness gates for minute-bar parquet."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import pandas as pd

EXPECTED_MINUTES_PER_SESSION = 375  # 09:15 to 15:30 IST = 6h15m
MISSING_PCT_THRESHOLD = 0.05  # §9.2 acceptance threshold
SESSION_START = time(9, 15)
SESSION_END = time(15, 30)


@dataclass
class GateResult:
    passed: bool
    missing_pct: float
    failures: list[str] = field(default_factory=list)


def run_cleanliness_gates(df: pd.DataFrame) -> GateResult:
    """Apply §9.2 acceptance thresholds. Returns GateResult."""
    failures: list[str] = []

    n_dates = df["trade_date"].nunique()
    expected_total = n_dates * EXPECTED_MINUTES_PER_SESSION
    actual_total = len(df)
    missing_pct = max(0.0, (expected_total - actual_total) / expected_total) if expected_total else 0.0

    if missing_pct > MISSING_PCT_THRESHOLD:
        failures.append(
            f"missing-bar % = {missing_pct:.4f} exceeds threshold {MISSING_PCT_THRESHOLD}"
        )

    times = df["timestamp"].dt.time
    after_hours = ((times < SESSION_START) | (times > SESSION_END)).sum()
    if after_hours > 0:
        failures.append(f"after-hours bars present: {after_hours}")

    return GateResult(passed=len(failures) == 0, missing_pct=missing_pct, failures=failures)
