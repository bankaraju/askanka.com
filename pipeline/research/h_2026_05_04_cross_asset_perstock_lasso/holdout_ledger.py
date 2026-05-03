"""09:15 IST OPEN / 14:25 IST CLOSE engine for H-2026-05-04 holdout ledger."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "pipeline" / "research" / "h_2026_05_04_cross_asset_perstock_lasso"
LEDGER_PATH = OUT_DIR / "recommendations.csv"

POSITION_INR = 50_000.0
ATR_MULT = 2.0
P_LONG_THRESHOLD = 0.6
P_SHORT_THRESHOLD = 0.4


def decide_open_rows(
    predictions: list[dict],
    p_long_threshold: float = P_LONG_THRESHOLD,
    p_short_threshold: float = P_SHORT_THRESHOLD,
) -> list[dict]:
    """Apply spec section 10 entry rule:
    fire LONG iff p_long >= 0.6 AND p_short < 0.4 (mirror for SHORT).
    """
    by_ticker: dict[str, dict[str, float]] = {}
    for p in predictions:
        by_ticker.setdefault(p["ticker"], {})[p["direction"]] = p["p_hat"]

    fires = []
    for ticker, dirs in by_ticker.items():
        p_long = dirs.get("LONG", 0.5)
        p_short = dirs.get("SHORT", 0.5)
        if p_long >= p_long_threshold and p_short < p_short_threshold:
            fires.append({"ticker": ticker, "direction": "LONG", "p_long": p_long, "p_short": p_short})
        if p_short >= p_long_threshold and p_long < p_short_threshold:
            fires.append({"ticker": ticker, "direction": "SHORT", "p_long": p_long, "p_short": p_short})
    return fires


def compute_atr_stop(*, entry: float, atr: float, mult: float, direction: str) -> float:
    return entry - mult * atr if direction == "LONG" else entry + mult * atr


def decide_close_pnl(
    *,
    entry: float, exit_ltp: float, stop: float,
    direction: str, position_inr: float,
    intraday_low: float | None = None,
    intraday_high: float | None = None,
) -> tuple[float, str]:
    """Returns (pnl_inr, exit_reason). exit_reason in {"TIME_STOP", "ATR_STOP"}."""
    stopped = False
    actual_exit = exit_ltp
    if direction == "LONG":
        if intraday_low is not None and intraday_low <= stop:
            stopped, actual_exit = True, stop
    else:
        if intraday_high is not None and intraday_high >= stop:
            stopped, actual_exit = True, stop

    sign = 1 if direction == "LONG" else -1
    pct = sign * (actual_exit - entry) / entry
    pnl = position_inr * pct
    return pnl, ("ATR_STOP" if stopped else "TIME_STOP")


def write_open_row(*, today: pd.Timestamp, fire: dict, entry_ltp: float, atr: float) -> None:
    """Append an OPEN row to recommendations.csv."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LEDGER_PATH.exists()
    fields = ["open_date", "ticker", "direction", "entry_ltp", "atr14", "stop", "position_inr",
              "p_long", "p_short", "exit_date", "exit_ltp", "exit_reason", "pnl_inr"]
    with open(LEDGER_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        stop = compute_atr_stop(entry=entry_ltp, atr=atr, mult=ATR_MULT, direction=fire["direction"])
        w.writerow({
            "open_date": str(today.date()), "ticker": fire["ticker"], "direction": fire["direction"],
            "entry_ltp": entry_ltp, "atr14": atr, "stop": stop, "position_inr": POSITION_INR,
            "p_long": fire["p_long"], "p_short": fire["p_short"],
            "exit_date": "", "exit_ltp": "", "exit_reason": "", "pnl_inr": "",
        })


def update_close_row(
    *, today: pd.Timestamp, ticker: str, direction: str,
    exit_ltp: float, intraday_low: float, intraday_high: float,
) -> None:
    """Find OPEN row from prior trading day and write its close fields."""
    if not LEDGER_PATH.exists():
        return
    rows = list(csv.DictReader(open(LEDGER_PATH, "r", encoding="utf-8")))
    for row in rows:
        if row["exit_date"] == "" and row["ticker"] == ticker and row["direction"] == direction:
            entry = float(row["entry_ltp"])
            stop = float(row["stop"])
            pnl, reason = decide_close_pnl(
                entry=entry, exit_ltp=exit_ltp, stop=stop,
                direction=direction, position_inr=POSITION_INR,
                intraday_low=intraday_low, intraday_high=intraday_high,
            )
            row["exit_date"] = str(today.date())
            row["exit_ltp"] = exit_ltp
            row["exit_reason"] = reason
            row["pnl_inr"] = round(pnl, 2)
            break
    fields = ["open_date", "ticker", "direction", "entry_ltp", "atr14", "stop", "position_inr",
              "p_long", "p_short", "exit_date", "exit_ltp", "exit_reason", "pnl_inr"]
    with open(LEDGER_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def open_today() -> int:
    """09:15 IST: read today_predictions.json, decide fires, write OPEN rows at Kite LTP."""
    preds_path = OUT_DIR / "today_predictions.json"
    if not preds_path.exists():
        print("[open] no today_predictions.json")
        return 1
    preds = json.loads(preds_path.read_text())["predictions"]
    fires = decide_open_rows(preds)
    if not fires:
        print("[open] 0 fires")
        return 0

    from pipeline.kite_ltp import get_ltp_batch  # existing kite client
    tickers = [f["ticker"] for f in fires]
    ltps = get_ltp_batch(tickers)

    today = pd.Timestamp.now().normalize()
    for f in fires:
        ltp = ltps.get(f["ticker"])
        if ltp is None:
            continue
        # ATR(14) from yesterday's bars
        from pipeline.research.h_2026_05_04_cross_asset_perstock_lasso.runner import _load_bars
        bars = _load_bars(f["ticker"])
        if bars is None or len(bars) < 30:
            continue
        prev_close = bars["Close"].shift(1)
        tr = pd.concat(
            [(bars["High"] - bars["Low"]),
             (bars["High"] - prev_close).abs(),
             (bars["Low"] - prev_close).abs()], axis=1,
        ).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1])
        write_open_row(today=today, fire=f, entry_ltp=ltp, atr=atr14)
    print(f"[open] wrote {len(fires)} OPEN rows")
    return 0


def close_today() -> int:
    """14:25 IST: for each OPEN row from prior trading day, write CLOSE fields at Kite LTP."""
    if not LEDGER_PATH.exists():
        print("[close] no ledger yet")
        return 0
    rows = list(csv.DictReader(open(LEDGER_PATH, "r", encoding="utf-8")))
    open_rows = [r for r in rows if r["exit_date"] == ""]
    if not open_rows:
        print("[close] 0 open rows")
        return 0

    from pipeline.kite_ltp import get_ltp_batch  # existing kite client
    tickers = list({r["ticker"] for r in open_rows})
    ltps = get_ltp_batch(tickers)

    today = pd.Timestamp.now().normalize()
    n_closed = 0
    for r in open_rows:
        ltp = ltps.get(r["ticker"])
        if ltp is None:
            continue
        # Intraday low/high since 09:15 IST today via kite intraday history
        from pipeline.kite_intraday import get_intraday_low_high
        try:
            lo, hi = get_intraday_low_high(r["ticker"], today)
        except Exception:
            lo, hi = ltp, ltp
        update_close_row(
            today=today, ticker=r["ticker"], direction=r["direction"],
            exit_ltp=ltp, intraday_low=lo, intraday_high=hi,
        )
        n_closed += 1
    print(f"[close] closed {n_closed} rows")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("open", "close"):
        print("usage: holdout_ledger.py {open|close}")
        sys.exit(2)
    sys.exit(open_today() if sys.argv[1] == "open" else close_today())
