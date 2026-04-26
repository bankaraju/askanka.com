"""Phase 2 reconciliation runner — compare minute-aggregated daily close to EOD parquet for 5 sample tickers.

Wires phase_2.adjustment_adapter so both series use a single adjustment convention
(§10 Unadjusted) before the §13 0.5% strict threshold is applied.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.autoresearch.etf_v3_eval.cross_source_reconciliation import compare_to_eod
from pipeline.autoresearch.etf_v3_eval.phase_2.adjustment_adapter import (
    AdjustmentEvent,
    unadjust_eod_series,
)

logger = logging.getLogger(__name__)

SAMPLE_TICKERS = ["ABB", "ACC", "ADANIENT", "ABFRL", "ABBOTINDIA"]
MINUTE_PARQUET = Path("pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_minute_bars.parquet")
EOD_DIR = Path("pipeline/data/fno_historical")
CORP_ACTION_PARQUET = Path("pipeline/data/earnings_calendar/history.parquet")
WINDOW_START = date(2026, 2, 26)
WINDOW_END = date(2026, 4, 23)
OUT = Path("pipeline/data/research/etf_v3_evaluation/phase_2_backtest/reconciliation_strict.json")

# Regexes used to detect and parse split/bonus events from agenda_raw text
_SPLIT_RE = re.compile(
    r"stock\s+split|sub[-\s]?division|subdivision",
    re.IGNORECASE,
)
_BONUS_RE = re.compile(r"\bbonus\s+(share|issue)", re.IGNORECASE)
_RATIO_RE = re.compile(r"(\d+)\s*[:\-/]\s*(\d+)")  # e.g. "2:1", "5-1"


def _parse_ratio_from_text(text: str) -> float | None:
    """Try to extract a numeric split/bonus ratio from agenda_raw free text.

    Returns the factor to multiply pre-event prices (e.g. 2.0 for a 2:1 split),
    or None if no ratio can be reliably parsed.
    """
    m = _RATIO_RE.search(text)
    if m:
        new_shares, old_shares = int(m.group(1)), int(m.group(2))
        if old_shares > 0 and new_shares > 0:
            return new_shares / old_shares
    return None


def _load_corp_actions(tickers: list[str]) -> dict[str, list[AdjustmentEvent]]:
    """Read earnings_calendar history.parquet, filter to split/bonus events for
    *tickers* within the reconciliation window, and return a mapping of ticker →
    list[AdjustmentEvent].

    The parquet only contains EventKind.QUARTERLY_EARNINGS rows; if the dataset
    has no splits/bonuses for the window, returns an empty dict (not an error).
    """
    if not CORP_ACTION_PARQUET.exists():
        logger.warning("Corp-action parquet not found at %s — skipping adjustment", CORP_ACTION_PARQUET)
        return {}

    df = pd.read_parquet(CORP_ACTION_PARQUET)
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date

    mask = (
        df["symbol"].isin(tickers)
        & (df["event_date"] >= WINDOW_START)
        & (df["event_date"] <= WINDOW_END)
    )
    sub = df[mask].copy()

    events: dict[str, list[AdjustmentEvent]] = {}
    for _, row in sub.iterrows():
        raw = str(row.get("agenda_raw") or "")
        kind = str(row.get("kind") or "")
        is_split = bool(_SPLIT_RE.search(raw) or _SPLIT_RE.search(kind))
        is_bonus = bool(_BONUS_RE.search(raw) or _BONUS_RE.search(kind))

        if not (is_split or is_bonus):
            continue  # Not a structural adjustment event — skip

        ev_kind = "split" if is_split else "bonus"
        ratio = _parse_ratio_from_text(raw)
        if ratio is None:
            logger.warning(
                "Could not parse ratio for %s %s on %s — skipping event",
                row["symbol"], ev_kind, row["event_date"],
            )
            continue

        sym = str(row["symbol"])
        events.setdefault(sym, []).append(
            AdjustmentEvent(symbol=sym, event_date=row["event_date"], kind=ev_kind, ratio=ratio)
        )

    logger.info("Corp-action loader resolved %d split/bonus events for %s tickers", sum(len(v) for v in events.values()), len(events))
    return events


def load_eod_for_tickers(
    tickers: list[str],
    events_by_ticker: dict[str, list[AdjustmentEvent]] | None = None,
) -> pd.DataFrame:
    """Load EOD close CSVs for *tickers*, optionally unadjusting each series.

    When *events_by_ticker* is supplied, any ticker found in the mapping has its
    auto-adjusted closes reversed via unadjust_eod_series so that reconciliation
    compares series under the same §10-Unadjusted convention as Kite minute bars.
    """
    events_by_ticker = events_by_ticker or {}
    frames = []
    for t in tickers:
        path = EOD_DIR / f"{t}.csv"
        if not path.exists():
            logger.warning("EOD CSV missing for %s at %s", t, path)
            continue
        df = pd.read_csv(path).rename(columns={"Date": "trade_date", "Close": "close"})
        df["ticker"] = t
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df = df[["ticker", "trade_date", "close"]]
        if t in events_by_ticker:
            df = unadjust_eod_series(df, events_by_ticker[t])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ticker", "trade_date", "close"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    minute_all = pd.read_parquet(MINUTE_PARQUET)
    minute_sample = minute_all[minute_all["ticker"].isin(SAMPLE_TICKERS)].copy()

    events = _load_corp_actions(SAMPLE_TICKERS)
    eod_sample = load_eod_for_tickers(SAMPLE_TICKERS, events_by_ticker=events)

    from pipeline.autoresearch.etf_v3_eval.cross_source_reconciliation import (
        MAX_DELTA_PCT,
        aggregate_minute_to_daily,
    )

    report = compare_to_eod(minute_sample, eod_sample, raise_on_failure=False)
    report["sample_tickers"] = SAMPLE_TICKERS
    report["threshold_pct"] = MAX_DELTA_PCT
    report["corp_action_events_parsed"] = {t: len(v) for t, v in events.items()}

    daily = aggregate_minute_to_daily(minute_sample)
    merged = daily[["ticker", "trade_date", "close"]].rename(columns={"close": "close_minute"}).merge(
        eod_sample[["ticker", "trade_date", "close"]].rename(columns={"close": "close_eod"}),
        on=["ticker", "trade_date"],
    )
    merged["delta_pct"] = (merged["close_minute"] - merged["close_eod"]).abs() / merged["close_eod"]

    report["per_ticker"] = {
        t: {
            "mean_delta_pct": float(g["delta_pct"].mean()),
            "max_delta_pct": float(g["delta_pct"].max()),
            "n_rows": int(len(g)),
            "n_above_threshold": int((g["delta_pct"] > MAX_DELTA_PCT).sum()),
        }
        for t, g in merged.groupby("ticker")
    }
    above = merged[merged["delta_pct"] > MAX_DELTA_PCT].sort_values("delta_pct", ascending=False)
    report["failing_rows"] = [
        {
            "ticker": str(r["ticker"]),
            "trade_date": str(r["trade_date"]),
            "close_minute": float(r["close_minute"]),
            "close_eod": float(r["close_eod"]),
            "delta_pct": float(r["delta_pct"]),
        }
        for _, r in above.iterrows()
    ]
    report["population_pass"] = float(merged["delta_pct"].mean()) < MAX_DELTA_PCT
    report["strict_pass"] = report["rows_above_threshold"] == 0

    # Build the residual-cause note based on findings
    n_corp_events = sum(len(v) for v in events.values())
    rows_above = report["rows_above_threshold"]
    if report["strict_pass"]:
        report["note"] = (
            f"Strict §13 PASS: 0/{report['n_rows_compared']} rows above {MAX_DELTA_PCT*100:.1f}% threshold. "
            f"Corp-action loader parsed {n_corp_events} split/bonus events in window "
            f"(earnings_calendar parquet contains only QUARTERLY_EARNINGS rows — no structural "
            f"adjustments detected for these 5 tickers in 2026-02-26..2026-04-23). "
            "Single-convention reconciliation passes regardless."
        )
    else:
        max_delta = report["max_delta_pct"]
        report["note"] = (
            f"Strict §13 FAIL: {rows_above}/{report['n_rows_compared']} rows above {MAX_DELTA_PCT*100:.1f}% threshold "
            f"(max delta {max_delta*100:.3f}%). "
            f"Corp-action loader parsed {n_corp_events} split/bonus events in window — "
            "earnings_calendar parquet contains ONLY EventKind.QUARTERLY_EARNINGS rows; "
            "no splits or bonuses are recorded for these 5 tickers in the 2026-02-26..2026-04-23 window. "
            "Residual cause: adjustment-mode mismatch is NOT the only divergence source. "
            "Likely contributors: (1) Kite minute bars use intraday LTP while EOD CSV uses "
            "official NSE closing price (post-auction settlement); (2) yfinance partial-day "
            "handling on the last bar of each session may differ from EOD source; "
            "(3) circuit-breaker / auction-session price differences on high-volatility days. "
            "Phase 2 must investigate intraday-vs-EOD methodology delta before depending on "
            "EOD parquet for ANY validation step."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
