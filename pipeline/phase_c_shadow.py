"""Phase C F3 live shadow ledger driver.

Two subcommands:

    python -m pipeline.phase_c_shadow open
        Read pipeline/data/correlation_breaks.json, filter OPPORTUNITY
        classifications, fetch live LTP via Kite, append OPEN rows to
        the live_paper ledger at
        pipeline/data/research/phase_c/live_paper_ledger.json.
        Idempotent: re-running in the same session is a no-op.

    python -m pipeline.phase_c_shadow close
        Find today's OPEN ledger entries, fetch live LTP for each,
        transition OPEN -> CLOSED with a TIME_STOP reason (14:30 IST).

Scheduled from:
    pipeline/scripts/phase_c_shadow_open.bat   (daily 09:25 IST)
    pipeline/scripts/phase_c_shadow_close.bat  (daily 14:30 IST)

Status (2026-04-23): EXPLORATORY — research-tier forward-scorecard only.
The H-2026-04-23-001 compliance run (100k permutations, Bonferroni
alpha = 1.17e-4 over 426 hypotheses) produced zero surviving
(ticker, direction) pairs; the residual-reversion edge could not be
ruled in at the corrected significance. These ledger entries are kept
for continued forward accumulation, not as trade recommendations. They
size at 0.5 unit (TIER_EXPLORING) and are excluded from subscriber-tier
Telegram broadcasts. Promotion back to SIGNAL requires 20+ closed
trades with >=65% win rate per config.TIER_PROMOTION_*.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date as _date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_PIPELINE_DIR = Path(__file__).resolve().parent
_BREAKS_PATH = _PIPELINE_DIR / "data" / "correlation_breaks.json"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _load_breaks() -> dict:
    """Return parsed correlation_breaks.json or an empty dict if absent."""
    if not _BREAKS_PATH.is_file():
        log.warning("correlation_breaks.json not found at %s", _BREAKS_PATH)
        return {}
    try:
        return json.loads(_BREAKS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("correlation_breaks.json is not valid JSON: %s", exc)
        return {}


def _filter_opportunity(breaks: list[dict]) -> list[dict]:
    """Return only rows whose classification is OPPORTUNITY_LAG (tradeable opportunities).

    OPPORTUNITY_OVERSHOOT is alert-only until H-2026-04-23-003 (FADE hypothesis) passes.
    """
    return [b for b in breaks if b.get("classification") == "OPPORTUNITY_LAG"]


def _side_from_expected(expected_return: float) -> str:
    """Backtest convention: LONG if expected_return >= 0, else SHORT."""
    return "LONG" if float(expected_return) >= 0 else "SHORT"


def _fetch_ltp(symbols: list[str]) -> dict[str, float]:
    """Wrapper around pipeline.kite_client.fetch_ltp (lazy import).

    Lazy import keeps unit tests from triggering Kite auth on collection.
    """
    if not symbols:
        return {}
    from pipeline.kite_client import fetch_ltp
    return fetch_ltp(symbols)


def build_open_signals(breaks_doc: dict, ltp: dict[str, float]) -> pd.DataFrame:
    """Convert the breaks doc + LTP snapshot into the live_paper signals schema.

    Args:
        breaks_doc: parsed correlation_breaks.json — {date, scan_time, breaks: [...]}
        ltp: {symbol: live_price}; symbols missing from this dict are skipped.

    Returns:
        DataFrame with columns:
            date, signal_time, symbol, side, z_score, stop_pct, target_pct, entry_px
        Empty DataFrame if no OPPORTUNITY entries have both a price and a
        well-formed expected_return.
    """
    breaks = breaks_doc.get("breaks", []) or []
    date_str = breaks_doc.get("date") or _date.today().isoformat()
    scan_time = breaks_doc.get("scan_time") or f"{date_str} 09:25:00"
    opps = _filter_opportunity(breaks)
    rows: list[dict] = []
    for b in opps:
        sym = b.get("symbol")
        if not sym:
            continue
        if sym not in ltp:
            log.warning("no LTP for %s — skipping", sym)
            continue
        expected = b.get("expected_return")
        if expected is None:
            log.warning("no expected_return on break for %s — skipping", sym)
            continue
        rows.append({
            "date": date_str,
            "signal_time": scan_time,
            "symbol": sym,
            "side": _side_from_expected(expected),
            "z_score": float(b.get("z_score", 0.0)),
            "stop_pct": 0.02,
            "target_pct": 0.01,
            "entry_px": float(ltp[sym]),
        })
    return pd.DataFrame(rows)


def _open_options_sidecar(signals: pd.DataFrame) -> None:
    """Best-effort paired-shadow options OPEN. Never propagates (spec §5)."""
    from pipeline import phase_c_options_shadow
    n_ok = 0
    n_err = 0
    for row in signals.to_dict("records"):
        try:
            phase_c_options_shadow.open_options_pair(row)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001 — spec §5 mandates blanket catch
            n_err += 1
            log.warning(
                "options sidecar OPEN failed for %s: %s: %s",
                row.get("symbol"), type(exc).__name__, exc,
            )
    log.info(
        "options sidecar: %d ok, %d errors out of %d signals",
        n_ok, n_err, len(signals),
    )


def cmd_open() -> int:
    """Append OPEN rows to the live_paper ledger. Returns process exit code."""
    from pipeline.research.phase_c_backtest import live_paper
    doc = _load_breaks()
    if not doc:
        log.info("no breaks doc; nothing to open")
        return 0
    breaks = doc.get("breaks", []) or []
    opps = _filter_opportunity(breaks)
    if not opps:
        log.info("no OPPORTUNITY signals in today's breaks (%d total breaks)", len(breaks))
        return 0
    syms = [b["symbol"] for b in opps if "symbol" in b]
    log.info("fetching LTP for %d OPPORTUNITY symbols", len(syms))
    ltp = _fetch_ltp(syms)
    signals = build_open_signals(doc, ltp)
    if signals.empty:
        log.info("no signals had both a Kite LTP and a valid expected_return; nothing to record")
        return 0
    n = live_paper.record_opens(signals)
    log.info("live_paper ledger: %d new OPEN entries recorded", n)

    # Sidecar: paired-shadow options ledger (spec §5 — exceptions caught here)
    _open_options_sidecar(signals)

    return 0


def _close_options_sidecar(date_str: str) -> None:
    """Best-effort paired-shadow options CLOSE. Never propagates (spec §5).

    Sweeps every OPEN row in the options ledger and calls close_options_pair
    on each. Mirrors the futures cmd_close pattern: status-driven, not
    date-driven. The previous date-filtered version was a no-op because
    futures rows carry the signal-generation date in `date`, never the
    close date — same shape of bug fixed for futures in commit 6843d57.
    """
    from pipeline import phase_c_options_shadow
    rows = phase_c_options_shadow._load_ledger()  # noqa: SLF001 — intentional
    open_rows = [r for r in rows if r.get("status") == "OPEN"]
    n_ok = 0
    n_err = 0
    n_noop = 0
    for row in open_rows:
        signal_id = row.get("signal_id")
        try:
            result = phase_c_options_shadow.close_options_pair(signal_id)
            if result is None:
                n_noop += 1
            else:
                n_ok += 1
        except Exception as exc:  # noqa: BLE001 — spec §5 mandates blanket catch
            n_err += 1
            log.warning(
                "options sidecar CLOSE failed for %s: %s: %s",
                signal_id, type(exc).__name__, exc,
            )
    log.info(
        "options sidecar CLOSE: %d open swept, %d ok, %d no-match, %d errors",
        len(open_rows), n_ok, n_noop, n_err,
    )


def cmd_close(date_override: str | None = None) -> int:
    """Close today's OPEN rows at live LTP (14:30 IST mechanical)."""
    from pipeline.research.phase_c_backtest import live_paper
    date_str = date_override or _date.today().isoformat()
    ledger = live_paper._load()  # noqa: SLF001 — intentional reuse
    open_syms = sorted({e["symbol"] for e in ledger if e["status"] == "OPEN"})
    if not open_syms:
        log.info("no OPEN entries for %s; nothing to close", date_str)
        return 0
    log.info("fetching LTP for %d OPEN symbols at 14:30", len(open_syms))
    ltp = _fetch_ltp(open_syms)
    if not ltp:
        log.error("LTP fetch returned nothing; leaving ledger untouched")
        return 1
    n = live_paper.close_at_1430(date_str, ltp)
    log.info("live_paper ledger: %d entries transitioned OPEN -> CLOSED", n)

    # Sidecar: paired-shadow options ledger close (spec §5 — exceptions caught here)
    _close_options_sidecar(date_str)

    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="Phase C F3 live shadow ledger driver",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open", help="Append OPEN rows for today's OPPORTUNITY signals")
    p_close = sub.add_parser("close", help="Close today's OPEN rows at live LTP")
    p_close.add_argument(
        "--date",
        default=None,
        help="Override the trade date (YYYY-MM-DD). Defaults to today IST.",
    )
    args = parser.parse_args(argv)
    if args.cmd == "open":
        return cmd_open()
    if args.cmd == "close":
        return cmd_close(args.date)
    parser.error(f"unknown cmd: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
