"""Phase C minute-resolution replay — pure logic.

See `docs/superpowers/specs/2026-04-30-phase-c-minute-replay-design.md` for
scope, decision matrix, and pre-registration status.

Inputs (per call site)
----------------------
- Per-ticker minute bars: dict[date_str -> list[bar dict]] from
  `pipeline/data/fno_intraday_1m/<TICKER>.csv` parsed by `replay_runner.py`.
- Per-ticker daily OHLC: list[dict] (with date/high/low/close) for ATR(14)
  PIT computation.
- PIT regime tape: dict[date_str -> regime_label].
- Profile: dict[ticker -> dict[regime -> {expected_return, std_return}]]
  from `pipeline.research.phase_c_backtest.profile.train_profile`.

Snapshot cadence
---------------
09:30, 09:45, 10:00, 10:15, ..., 13:45, 14:00 IST inclusive
(matches live `AnkaCorrelationBreaks_HHMM` scheduled tasks).

Each snapshot computes:
    intraday_ret = (snap_px - prev_close) / prev_close
    z = (intraday_ret - profile.expected_return) / profile.std_return

Note that the profile was fitted on DAILY close-to-close returns; using
intraday partial-day returns inflates z magnitudes since variance scales
sublinearly in time. We accept this approximation v0 — the live signal
behaves the same way (it computes z against the daily profile too) so the
replay is faithful TO THE LIVE LOGIC, not to ideal statistical theory.
This is documented in §2 of the design spec.

De-dup rule (matches live)
-------------------------
First valid (LAG, non-null trade_rec) signal per (date, ticker) wins.
Subsequent signals on the same (date, ticker) get
``status=DUPLICATE_DAY_TICKER`` and excluded from PnL aggregation.

Public API
----------
- ``snapshot_times()`` -> list of "HH:MM:SS" snap times.
- ``compute_signal_at_snapshot(...)`` -> Signal | None.
- ``simulate_exit(...)`` -> (exit_px, exit_reason).
- ``replay_one_day(...)`` -> list[Signal].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Matches break_signal_generator.py post-2026-04-23 logic.
_ACTIONABLE_DIRECTIONS = ("LONG", "SHORT")
_ACTIONABLE_CLASSIFICATIONS = ("OPPORTUNITY_LAG",)
_Z_THRESHOLD = 4.0  # |z| >= 4 to fire (matches live engine)
ATR_MULT = 2.0
EXIT_TIME = "14:30:00"
SNAP_START_MINUTES_FROM_OPEN = 15  # 09:30 IST
SNAP_INTERVAL_MINUTES = 15
SNAP_END_TIME = "14:00:00"


@dataclass(frozen=True)
class Signal:
    """One Phase C signal candidate at a particular snapshot."""

    date: str
    snap_time_ist: str
    ticker: str
    regime: str
    sector: str | None
    z_score: float
    classification: str
    trade_rec: str | None
    intraday_ret: float
    expected_ret: float
    std_ret: float
    status: str   # "OPEN", "DUPLICATE_DAY_TICKER", or "INFORMATIONAL"


def snapshot_times() -> list[str]:
    """Return the live engine's 15-min snapshot grid as HH:MM:SS strings."""
    times = []
    h, m = 9, 30
    while True:
        times.append(f"{h:02d}:{m:02d}:00")
        if (h, m) == (14, 0):
            break
        m += SNAP_INTERVAL_MINUTES
        if m >= 60:
            h += m // 60
            m = m % 60
    return times


def _z_score(actual: float, expected: float, std: float) -> float:
    if std <= 0.001:
        return 0.0
    return (actual - expected) / std


def _direction_from_expected(expected_return_pct: float) -> str | None:
    """LAG: trade in expected direction (positive expected -> LONG)."""
    if expected_return_pct > 0:
        return "LONG"
    if expected_return_pct < 0:
        return "SHORT"
    return None


def _classify(z: float, expected: float, actual: float) -> str:
    """Lightweight classifier mirroring the LAG-vs-OVERSHOOT split.

    LAG: |z| >= threshold AND actual on the SAME side of zero as expected
         (same-sign agreement) AND |actual| < |expected| (under-shooting).
    OVERSHOOT: |z| >= threshold AND actual same-sign as expected but
         |actual| > |expected|.
    Otherwise: NOT_A_BREAK.

    Closely mirrors the geometric split in
    `pipeline.autoresearch.reverse_regime_breaks.classify_event_geometry`,
    simplified for this descriptive replay: PCR + OI gates collapse to
    NEUTRAL (we don't have minute-level PCR/OI in the cache), so the only
    label that downstream actually treats as actionable is OPPORTUNITY_LAG.
    """
    if abs(z) < _Z_THRESHOLD:
        return "NOT_A_BREAK"
    if expected == 0 or actual == 0:
        return "UNCERTAIN"
    same_sign = (expected > 0 and actual > 0) or (expected < 0 and actual < 0)
    if not same_sign:
        return "POSSIBLE_OPPORTUNITY"
    if abs(actual) <= abs(expected):
        return "OPPORTUNITY_LAG"
    return "OPPORTUNITY_OVERSHOOT"


def compute_signal_at_snapshot(
    *,
    date: str,
    snap_time_ist: str,
    ticker: str,
    regime: str,
    sector: str | None,
    snap_px: float,
    prev_close: float,
    profile_expected: float,
    profile_std: float,
    seen_today: set[str],
) -> Signal | None:
    """Return a Signal if the snapshot triggers; None otherwise.

    `seen_today` is mutated when a signal is recorded — caller passes the
    same set across all snapshots for the same date.
    """
    if prev_close <= 0:
        return None
    intraday_ret = (snap_px - prev_close) / prev_close
    z = _z_score(intraday_ret, profile_expected, profile_std)
    classification = _classify(z, profile_expected, intraday_ret)

    trade_rec: str | None = None
    if classification == "OPPORTUNITY_LAG":
        trade_rec = _direction_from_expected(profile_expected * 100)

    if classification == "NOT_A_BREAK":
        return None

    if trade_rec is None and classification != "OPPORTUNITY_OVERSHOOT":
        # Informational — record but no trade
        status = "INFORMATIONAL"
    elif ticker in seen_today:
        status = "DUPLICATE_DAY_TICKER"
    else:
        status = "OPEN"
        seen_today.add(ticker)

    return Signal(
        date=date, snap_time_ist=snap_time_ist, ticker=ticker, regime=regime,
        sector=sector, z_score=z, classification=classification,
        trade_rec=trade_rec, intraday_ret=intraday_ret,
        expected_ret=profile_expected, std_ret=profile_std, status=status,
    )


def simulate_exit(
    bars: Iterable[dict],
    snap_time_ist: str,
    side: str,
    entry_px: float,
    atr: float | None,
) -> tuple[float, str, str]:
    """Walk minute bars from `snap_time_ist` (inclusive) to 14:30 IST.

    Returns (exit_px, exit_reason, exit_time_ist). exit_reason in
    {ATR_STOP, TIME_STOP, NO_DATA}.
    """
    bars_after = [b for b in bars
                  if snap_time_ist <= b.get("time", "") <= EXIT_TIME]
    if not bars_after:
        return entry_px, "NO_DATA", snap_time_ist

    if atr is not None and atr > 0:
        stop_distance = ATR_MULT * atr
        if side == "LONG":
            stop_px = entry_px - stop_distance
            for b in bars_after[1:]:
                lo = b.get("low")
                if lo is not None and lo <= stop_px:
                    return stop_px, "ATR_STOP", b["time"]
        else:
            stop_px = entry_px + stop_distance
            for b in bars_after[1:]:
                hi = b.get("high")
                if hi is not None and hi >= stop_px:
                    return stop_px, "ATR_STOP", b["time"]

    last = bars_after[-1]
    return float(last["close"]), "TIME_STOP", last["time"]


def realize_pnl(side: str, entry_px: float, exit_px: float) -> float:
    """Per-leg pct P&L (gross — cost-model applied at the runner level)."""
    if side == "LONG":
        return (exit_px - entry_px) / entry_px
    return (entry_px - exit_px) / entry_px
