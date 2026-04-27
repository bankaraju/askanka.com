"""Scanner (TA) paired-shadow options sidecar: OPEN + CLOSE paths.

Mirrors pipeline.phase_c_options_shadow but for Scanner Top-10 signals.
Called from cli_pattern_scanner.cmd_paired_open / cmd_paired_close (T8c).

Key differences from Phase C sidecar:
- signal_row does NOT carry entry_px; caller passes it separately.
- No drift_vs_rent_tier / drift_vs_rent_matrix fields.
- 3 additional provenance fields: pattern_id, scanner_composite_score_at_entry,
  scanner_z_score_at_entry.
- option_type: CE if direction==LONG, PE if direction==SHORT.

Spec: docs/superpowers/specs/2026-04-27-ta-scanner-pattern-paired-shadow-design.md §6.5, §7.3, §8.3, §8.4
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from pipeline import options_atm_helpers, options_quote, options_greeks
from pipeline.kite_client import get_kite
from pipeline.research.phase_c_v5 import cost_model

IST = timezone(timedelta(hours=5, minutes=30))

LEDGER_PATH: Path = Path(
    "pipeline/data/research/scanner/live_paper_scanner_options_ledger.json"
)
NFO_MASTER_PATH: Path = Path("pipeline/data/kite_cache/instruments_nfo.csv")
LOG_PATH: Path = Path("pipeline/logs/scanner_paired_shadow.log")

log = logging.getLogger(__name__)


def _ist_now() -> datetime:
    return datetime.now(IST)


def _ensure_log_handler() -> None:
    if log.handlers:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(LOG_PATH, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def _load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_ledger(rows: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def _empty_close_fields() -> dict:
    return {
        "exit_time": None, "exit_bid": None, "exit_ask": None, "exit_mid": None,
        "seconds_to_expiry_at_close": None,
        "pnl_gross_pct": None, "pnl_net_pct": None,
        "pnl_gross_inr": None, "pnl_net_inr": None,
    }


def _resolve_instrument_token(tradingsymbol: str, nfo_master_df: pd.DataFrame) -> int:
    sub = nfo_master_df.loc[
        nfo_master_df["tradingsymbol"] == tradingsymbol, "instrument_token"
    ]
    if sub.empty:
        raise ValueError(
            f"instrument_token not found for tradingsymbol {tradingsymbol!r}"
        )
    return int(sub.iloc[0])


def open_options_pair(
    scanner_signal: dict,
    entry_px: float,
    *,
    kite_client=None,
    nfo_master_df=None,
    lot_size: int | None = None,
) -> dict:
    """Open a paired ATM-options leg for a Scanner Top-10 signal.

    scanner_signal: one top_10 row from pattern_signals_today.json.
        Required fields: signal_id, ticker, pattern_id, direction,
        composite_score, z_score.
    entry_px: spot price for ATM strike resolution (from Kite LTP at 09:25 IST).
    Returns: the options-ledger row written (status OPEN | SKIPPED_LIQUIDITY | ERROR).
    Idempotent on signal_id.

    Spec: §6.5, §8.3
    """
    _ensure_log_handler()
    signal_id = str(scanner_signal.get("signal_id", ""))
    ticker = str(scanner_signal.get("ticker") or scanner_signal.get("symbol", ""))
    direction = str(scanner_signal.get("direction", "LONG")).upper()
    option_type = "CE" if direction == "LONG" else "PE"

    # Idempotency: return existing row if already in ledger
    rows = _load_ledger()
    for r in rows:
        if r.get("signal_id") == signal_id:
            log.info("idempotent skip: %s already in scanner options ledger", signal_id)
            return r

    base_row: dict = {
        "signal_id": signal_id,
        "date": scanner_signal.get("date"),
        "scan_date": scanner_signal.get("scan_date", scanner_signal.get("date")),
        "ticker": ticker,
        "pattern_id": str(scanner_signal.get("pattern_id", "")),
        "scanner_composite_score_at_entry": float(scanner_signal.get("composite_score", 0.0)),
        "scanner_z_score_at_entry": float(scanner_signal.get("z_score", 0.0)),
        "side": "LONG" if direction == "LONG" else "SHORT",
        "option_type": option_type,
        "expiry_date": None,
        "days_to_expiry": None,
        "is_expiry_day": None,
        "strike": None,
        "tradingsymbol": None,
        "instrument_token": None,
        "lot_size": lot_size,
        "lots": 1,
        "notional_at_entry": None,
        "entry_time": None,
        "entry_bid": None,
        "entry_ask": None,
        "entry_mid": None,
        "spread_pct_at_entry": None,
        "entry_iv": None,
        "entry_delta": None,
        "entry_theta": None,
        "entry_vega": None,
        "status": None,
        "skip_reason": None,
        **_empty_close_fields(),
    }

    try:
        if nfo_master_df is None:
            nfo_master_df = options_atm_helpers.load_nfo_master(NFO_MASTER_PATH)
        if kite_client is None:
            kite_client = get_kite()
        if base_row["lot_size"] is None:
            base_row["lot_size"] = options_atm_helpers.get_lot_size_for_ticker(
                ticker, nfo_master_df
            )

        today = _ist_now().date()
        spot = float(entry_px)

        expiry = options_atm_helpers.resolve_nearest_monthly_expiry(
            today, ticker, nfo_master_df
        )
        dte = (expiry - today).days
        is_expiry_day = dte == 0

        strike = options_atm_helpers.resolve_atm_strike(
            spot, ticker, expiry, nfo_master_df
        )

        tradingsymbol = options_atm_helpers.compose_tradingsymbol(
            ticker, expiry, strike, option_type
        )
        instrument_token = _resolve_instrument_token(tradingsymbol, nfo_master_df)

        base_row.update({
            "expiry_date": expiry.isoformat(),
            "days_to_expiry": dte,
            "is_expiry_day": is_expiry_day,
            "strike": int(strike),
            "tradingsymbol": tradingsymbol,
            "instrument_token": instrument_token,
            "entry_time": _ist_now().isoformat(),
        })

        quote = options_quote.fetch_mid_with_liquidity_check(
            kite_client, instrument_token
        )
        base_row.update({
            "entry_bid": quote.bid,
            "entry_ask": quote.ask,
            "entry_mid": quote.mid,
            "spread_pct_at_entry": quote.spread_pct,
        })

        if not quote.liquidity_passed:
            base_row["status"] = "SKIPPED_LIQUIDITY"
            base_row["skip_reason"] = quote.skip_reason
            log.info("liquidity skip %s: %s", signal_id, quote.skip_reason)
        else:
            try:
                iv = options_greeks.backsolve_iv(
                    spot=spot, strike=float(strike), dte_days=max(dte, 1),
                    mid_premium=quote.mid, option_type=option_type,
                )
                greeks = options_greeks.compute_greeks(
                    spot=spot, strike=float(strike), dte_days=max(dte, 1),
                    iv=iv, option_type=option_type,
                )
                base_row.update({
                    "entry_iv": iv,
                    "entry_delta": greeks["delta"],
                    "entry_theta": greeks["theta"],
                    "entry_vega": greeks["vega"],
                })
            except Exception as iv_exc:
                # IV solver failure is non-blocking per spec §9.
                log.warning("IV solver failed for %s: %s", signal_id, iv_exc)

            base_row["notional_at_entry"] = (
                quote.mid * base_row["lot_size"] * base_row["lots"]
            )
            base_row["status"] = "OPEN"
            log.info("opened %s @ %s, mid=%s", signal_id, tradingsymbol, quote.mid)

    except Exception as exc:
        log.error(
            "open_options_pair %s failed: %s\n%s",
            signal_id, exc, traceback.format_exc(),
        )
        base_row["status"] = "ERROR"
        base_row["skip_reason"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    rows.append(base_row)
    _save_ledger(rows)
    return base_row


def close_options_pair(
    signal_id: str,
    *,
    kite_client=None,
) -> dict | None:
    """Close the matching OPEN options row at live mid-price (15:30 IST).

    Returns the updated row, or None if no matching row.
    Wide spread at close is informational — row still transitions to CLOSED.
    Terminal-state rows (CLOSED, SKIPPED_LIQUIDITY, ERROR, TIME_STOP_FAIL_FETCH)
    are returned unchanged without a Kite call.

    Spec: §6.5, §8.4
    """
    _ensure_log_handler()
    rows = _load_ledger()

    idx = next((i for i, r in enumerate(rows) if r.get("signal_id") == signal_id), None)
    if idx is None:
        return None

    row = rows[idx]
    if row.get("status") != "OPEN":
        log.info(
            "close_options_pair: %s already in terminal state %s, skipping",
            signal_id, row.get("status"),
        )
        return row

    if kite_client is None:
        kite_client = get_kite()

    try:
        instrument_token = int(row["instrument_token"])
        quote = options_quote.fetch_mid_with_liquidity_check(kite_client, instrument_token)

        if not quote.liquidity_passed:
            log.warning(
                "close_options_pair: wide/illiquid spread at close for %s (%s) "
                "-- closing anyway per spec §8.4",
                signal_id, quote.skip_reason,
            )

        exit_time = _ist_now()
        entry_mid = float(row["entry_mid"])
        lot_size = int(row["lot_size"])
        lots = int(row["lots"])
        notional_at_entry = float(row["notional_at_entry"])
        exit_mid = quote.mid

        pnl_gross_pct = (exit_mid - entry_mid) / entry_mid
        pnl_gross_inr = (exit_mid - entry_mid) * lot_size * lots

        pnl_net_inr = cost_model.apply_to_pnl(
            pnl_gross_inr, instrument="option",
            notional_inr=notional_at_entry, side="LONG",
        )
        pnl_net_pct = pnl_net_inr / notional_at_entry

        seconds_to_expiry_at_close = None
        if row.get("is_expiry_day"):
            market_close = exit_time.replace(hour=15, minute=30, second=0, microsecond=0)
            seconds_to_expiry_at_close = int((market_close - exit_time).total_seconds())

        row.update({
            "exit_time": exit_time.isoformat(),
            "exit_bid": quote.bid,
            "exit_ask": quote.ask,
            "exit_mid": exit_mid,
            "seconds_to_expiry_at_close": seconds_to_expiry_at_close,
            "pnl_gross_pct": pnl_gross_pct,
            "pnl_net_pct": pnl_net_pct,
            "pnl_gross_inr": pnl_gross_inr,
            "pnl_net_inr": pnl_net_inr,
            "status": "CLOSED",
        })
        log.info(
            "closed %s @ exit_mid=%.4f pnl_gross_pct=%.4f pnl_net_pct=%.4f",
            signal_id, exit_mid, pnl_gross_pct, pnl_net_pct,
        )

    except Exception as exc:
        log.error(
            "close_options_pair %s fetch failed: %s\n%s",
            signal_id, exc, traceback.format_exc(),
        )
        row["status"] = "TIME_STOP_FAIL_FETCH"

    rows[idx] = row
    _save_ledger(rows)
    return row
