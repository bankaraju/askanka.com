"""Candidate loader for the Karpathy search.

Reads the existing 5y minute-resolution replay output and returns the in-sample
POSSIBLE_OPPORTUNITY events that pass the regime gate + event-day skip. These
are the events the Karpathy 6-of-8 qualifier sees in the §8 grid search.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .event_day_skip import is_event_day

REPO = Path(__file__).resolve().parents[3]
DEFAULT_REPLAY_CSV = REPO / "pipeline" / "data" / "research" / "phase_c" / "minute_replay_2021-05-01_2026-04-30.csv"

TRAIN_OPEN = "2021-05-01"
TRAIN_CLOSE = "2024-04-30"
ALLOWED_REGIMES = frozenset({"RISK-ON", "CAUTION"})


@dataclass(frozen=True)
class Candidate:
    """One in-sample POSSIBLE_OPPORTUNITY event for the Karpathy fit."""
    date: str
    snap_t: str
    ticker: str
    regime: str
    sector: str
    z_score: float
    intraday_ret_pct: float
    expected_ret_pct: float
    snap_px: float
    pnl_pct_net: float       # gross P&L net of replay's 5 bps single-side cost
    atr_14: float | None


def _to_float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_candidates(
    csv_path: Path = DEFAULT_REPLAY_CSV,
    *,
    window_open: str = TRAIN_OPEN,
    window_close: str = TRAIN_CLOSE,
) -> list[Candidate]:
    """Read the replay CSV and return the in-sample candidates after gate filters."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"replay CSV not found: {csv_path}")

    out: list[Candidate] = []
    with csv_path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            d = row.get("date")
            if not d or not (window_open <= d <= window_close):
                continue
            if row.get("route_slice") != "POSSIBLE_OPPORTUNITY":
                continue
            if row.get("regime") not in ALLOWED_REGIMES:
                continue
            if is_event_day(d):
                continue
            pnl = _to_float(row.get("pnl_pct_net"))
            if pnl is None:
                continue
            z = _to_float(row.get("z_score"))
            ir = _to_float(row.get("intraday_ret"))
            er = _to_float(row.get("expected_ret"))
            entry_px = _to_float(row.get("entry_px"))
            atr = _to_float(row.get("atr_14"))
            if z is None or ir is None or er is None or entry_px is None:
                continue
            out.append(Candidate(
                date=d,
                snap_t=row["snap_time_ist"],
                ticker=row["ticker"],
                regime=row["regime"],
                sector=row.get("sector") or "",
                z_score=z,
                intraday_ret_pct=ir * 100.0,
                expected_ret_pct=er * 100.0,
                snap_px=entry_px,
                pnl_pct_net=pnl,
                atr_14=atr,
            ))
    return out


def split_by_half(candidates: list[Candidate], split_date: str) -> tuple[list[Candidate], list[Candidate]]:
    """Split candidates into two halves around `split_date` for fragility check."""
    first = [c for c in candidates if c.date <= split_date]
    second = [c for c in candidates if c.date > split_date]
    return first, second
