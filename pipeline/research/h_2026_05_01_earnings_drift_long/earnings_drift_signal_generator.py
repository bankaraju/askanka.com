"""H-2026-05-01-earnings-drift-long-v1 — signal generator.

PURPOSE
-------
Pure function: given (universe, earnings_calendar, daily_bars) at a date T-1,
emit zero-or-more (symbol, event_date, side="LONG") qualified positions.

ENTRY RULE (FROZEN per spec §5)
-------------------------------
For every (symbol, event_date) in the calendar where:
  - symbol is in the frozen universe,
  - event_date - 1 trading day == today (i.e., today IS T-1),
  - volume_z_5d >= 0.52 measured at T-1 14:25 IST,
  - short_mom_5d > 0 (5-day stock log return) measured at T-1 14:25 IST,
emit a LONG candidate.

NO LOOK-AHEAD: all features computed from bars dated <= T-1.

This file matches the kill-switch regex (`*_signal_generator.py`); a registry
row in `docs/superpowers/hypothesis-registry.jsonl` MUST be present in the
same commit.

Spec: docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
Audit: docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
UNIVERSE_FROZEN = ROOT / "pipeline" / "research" / "h_2026_05_01_earnings_drift_long" / "universe_frozen.json"
CALENDAR_PATH = ROOT / "pipeline" / "data" / "earnings_calendar" / "history.parquet"
DAILY_DIR = ROOT / "pipeline" / "data" / "fno_historical"
REGIME_TAPE_PATH = ROOT / "pipeline" / "data" / "research" / "etf_v3" / "regime_tape_5y_pit.csv"
ALLOWED_REGIMES = frozenset({"NEUTRAL", "RISK-ON"})

# FROZEN per spec §5
VOL_Z_THRESHOLD = 0.52
SHORT_MOM_BPS_THRESHOLD = 0.0
REALIZED_VOL_21D_PCT_THRESHOLD = 29.0  # annualised %
VOL_LOOKBACK_RECENT = 5
VOL_LOOKBACK_BASELINE = 30
MOM_LOOKBACK = 5
ATR_LOOKBACK = 14
REALIZED_VOL_LOOKBACK = 21
STOP_ATR_MULT = 2.0
MIN_PRIOR_BARS = 35  # 5 recent vol + 30 baseline vol + 21 realized-vol margin


@dataclass
class SignalCandidate:
    symbol: str
    event_date: pd.Timestamp
    entry_date: pd.Timestamp  # T-1
    side: str  # always "LONG" at v1
    volume_z: float
    short_mom_bps: float
    realized_vol_21d_pct: float
    regime: str
    atr_14_pct: float
    entry_close_ref: float  # T-1 close, reference for stop levels at runtime


def _load_regime_tape_lookup() -> dict[pd.Timestamp, str]:
    if not REGIME_TAPE_PATH.exists():
        return {}
    rt = pd.read_csv(REGIME_TAPE_PATH)
    rt["date"] = pd.to_datetime(rt["date"])
    return dict(zip(rt["date"], rt["regime"]))


def load_universe() -> list[str]:
    with open(UNIVERSE_FROZEN, "r") as f:
        cfg = json.load(f)
    out: list[str] = []
    for sec, syms in cfg["universe"].items():
        out.extend(syms)
    return out


def load_calendar(window_start: date | None = None, window_end: date | None = None) -> pd.DataFrame:
    """Read the IndianAPI corporate-actions earnings calendar parquet."""
    df = pd.read_parquet(CALENDAR_PATH)
    df = df[df["kind"] == "EventKind.QUARTERLY_EARNINGS"].copy()
    df["event_date"] = pd.to_datetime(df["event_date"])
    if window_start is not None:
        df = df[df["event_date"] >= pd.Timestamp(window_start)]
    if window_end is not None:
        df = df[df["event_date"] <= pd.Timestamp(window_end)]
    return df.drop_duplicates(subset=["symbol", "event_date"]).reset_index(drop=True)


def _read_daily(symbol: str) -> pd.DataFrame | None:
    path = DAILY_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df.columns = [c.strip().capitalize() for c in df.columns]
    if "Date" not in df.columns or "Close" not in df.columns or "Volume" not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def _last_trading_day_strictly_before(daily: pd.DataFrame, ref: pd.Timestamp) -> pd.Timestamp | None:
    """Return the largest Date strictly less than ref, or None."""
    dts = daily["Date"]
    mask = dts < ref
    if not mask.any():
        return None
    return dts[mask].iloc[-1]


def _compute_features(daily: pd.DataFrame, t_minus_1: pd.Timestamp) -> dict | None:
    """Compute (volume_z_5d, short_mom_bps_5d, atr_14_pct) at T-1 close.

    Returns None if not enough prior bars.
    """
    sub = daily[daily["Date"] <= t_minus_1].copy()
    if len(sub) < MIN_PRIOR_BARS:
        return None

    last = sub.iloc[-1]
    if not (last["Date"] == t_minus_1):
        return None

    # 5-day average volume (T-5 .. T-1 inclusive)
    vol_recent = sub["Volume"].iloc[-VOL_LOOKBACK_RECENT:]
    if len(vol_recent) < VOL_LOOKBACK_RECENT:
        return None
    vol_5d_avg = float(vol_recent.mean())

    # 30-day baseline volume window (T-34 .. T-5)
    vol_30 = sub["Volume"].iloc[-(VOL_LOOKBACK_RECENT + VOL_LOOKBACK_BASELINE):-VOL_LOOKBACK_RECENT]
    if len(vol_30) < VOL_LOOKBACK_BASELINE:
        return None
    vol_30d_avg = float(vol_30.mean())
    vol_30d_std = float(vol_30.std(ddof=1))
    if vol_30d_std <= 0 or math.isnan(vol_30d_std):
        return None
    volume_z = (vol_5d_avg - vol_30d_avg) / vol_30d_std

    # 5-day momentum: ln(close[T-1] / close[T-6]) * 10000
    if len(sub) < MOM_LOOKBACK + 1:
        return None
    p_now = float(sub["Close"].iloc[-1])
    p_back = float(sub["Close"].iloc[-(MOM_LOOKBACK + 1)])
    if p_back <= 0 or p_now <= 0:
        return None
    short_mom_bps = math.log(p_now / p_back) * 10_000.0

    # ATR(14) percentage on T-1 — Wilder-style mean of true range over last 14 bars
    atr_window = sub.iloc[-(ATR_LOOKBACK + 1):]
    if len(atr_window) < ATR_LOOKBACK + 1:
        return None
    h = atr_window["High"].values
    l = atr_window["Low"].values
    c_prev = atr_window["Close"].shift(1).values
    tr = []
    for i in range(1, len(atr_window)):
        rng = max(h[i] - l[i], abs(h[i] - c_prev[i]), abs(l[i] - c_prev[i]))
        tr.append(rng)
    if len(tr) != ATR_LOOKBACK:
        return None
    atr_abs = float(sum(tr) / ATR_LOOKBACK)
    atr_14_pct = atr_abs / p_now

    # 21-day annualised realised volatility (FROZEN §5.4)
    rv_window = sub.iloc[-REALIZED_VOL_LOOKBACK:]
    if len(rv_window) < REALIZED_VOL_LOOKBACK:
        return None
    closes = rv_window["Close"].values
    log_returns = []
    for i in range(1, len(closes)):
        if closes[i] <= 0 or closes[i - 1] <= 0:
            return None
        log_returns.append(math.log(closes[i] / closes[i - 1]))
    if len(log_returns) < REALIZED_VOL_LOOKBACK - 1:
        return None
    n = len(log_returns)
    mean_lr = sum(log_returns) / n
    var_lr = sum((x - mean_lr) ** 2 for x in log_returns) / (n - 1)
    realized_vol_21d_pct = math.sqrt(var_lr) * math.sqrt(252) * 100.0

    return {
        "volume_z": volume_z,
        "short_mom_bps": short_mom_bps,
        "realized_vol_21d_pct": realized_vol_21d_pct,
        "atr_14_pct": atr_14_pct,
        "entry_close_ref": p_now,
    }


def generate_signals_for_entry_date(entry_date: date) -> list[SignalCandidate]:
    """Generate LONG candidates whose T-1 == entry_date.

    A candidate exists for a (symbol, event_date) iff:
      - symbol in frozen universe,
      - event_date is the first calendar event_date STRICTLY GREATER than entry_date
        for this symbol (i.e., entry_date is the last trading day before event_date),
      - features at entry_date pass the FROZEN entry rule.
    """
    universe = load_universe()
    cal = load_calendar()
    cal = cal[cal["symbol"].isin(universe)].copy()
    regime_lookup = _load_regime_tape_lookup()

    entry_ts = pd.Timestamp(entry_date)
    regime_at_entry = regime_lookup.get(entry_ts)
    if regime_at_entry is None:
        # No regime label for entry date — strict skip per single-touch discipline
        return []
    if regime_at_entry not in ALLOWED_REGIMES:
        return []

    candidates: list[SignalCandidate] = []

    for symbol, sub_cal in cal.groupby("symbol"):
        daily = _read_daily(symbol)
        if daily is None or daily.empty:
            continue

        # Find the next event_date strictly after entry_date for this symbol
        next_events = sub_cal[sub_cal["event_date"] > entry_ts].sort_values("event_date")
        if next_events.empty:
            continue
        next_event_date = next_events["event_date"].iloc[0]

        # Verify entry_date IS the last trading day strictly before next_event_date
        last_td = _last_trading_day_strictly_before(daily, next_event_date)
        if last_td is None or last_td != entry_ts:
            continue

        feats = _compute_features(daily, entry_ts)
        if feats is None:
            continue

        if (feats["volume_z"] >= VOL_Z_THRESHOLD) \
                and (feats["short_mom_bps"] > SHORT_MOM_BPS_THRESHOLD) \
                and (feats["realized_vol_21d_pct"] >= REALIZED_VOL_21D_PCT_THRESHOLD):
            candidates.append(SignalCandidate(
                symbol=symbol,
                event_date=next_event_date,
                entry_date=entry_ts,
                side="LONG",
                volume_z=float(feats["volume_z"]),
                short_mom_bps=float(feats["short_mom_bps"]),
                realized_vol_21d_pct=float(feats["realized_vol_21d_pct"]),
                regime=regime_at_entry,
                atr_14_pct=float(feats["atr_14_pct"]),
                entry_close_ref=float(feats["entry_close_ref"]),
            ))

    return candidates


def signal_summary_string(c: SignalCandidate) -> str:
    return (f"{c.symbol:14s} entry={c.entry_date.date()} event={c.event_date.date()} "
            f"vol_z={c.volume_z:+.2f} mom_bps={c.short_mom_bps:+.0f} "
            f"rv21={c.realized_vol_21d_pct:.1f}% regime={c.regime} "
            f"atr_pct={c.atr_14_pct*100:.2f}% close={c.entry_close_ref:.2f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ed = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        ed = date.today()
    cands = generate_signals_for_entry_date(ed)
    print(f"\nentry_date={ed}: {len(cands)} qualified LONG candidates\n")
    for c in cands:
        print("  " + signal_summary_string(c))
