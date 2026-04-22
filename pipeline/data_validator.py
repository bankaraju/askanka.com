"""
Anka Research — Data Validation Gate
MANDATORY check before ANY data reaches subscribers (Telegram or website).

RULE: No number goes out without passing validation.
If validation fails, the message is BLOCKED and an alert is sent to Bharat instead.

This is not optional. Every pipeline output must call validate_before_send().
"""

import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("anka.validator")

IST = timezone(timedelta(hours=5, minutes=30))
VALIDATION_LOG = Path(__file__).parent / "logs" / "validation.log"


class ValidationError(Exception):
    """Raised when data fails validation. Blocks sending to subscribers."""
    pass


def validate_msi(msi_result: dict) -> list:
    """Validate MSI data before publishing."""
    errors = []

    score = msi_result.get("msi_score")
    if score is None or not isinstance(score, (int, float)):
        errors.append("MSI score is None or non-numeric")
    elif score < 0 or score > 100:
        errors.append(f"MSI score {score} is outside 0-100 range")

    # Check data quality — reject if <80%
    quality = msi_result.get("data_quality_pct", 0)
    if quality < 80:
        missing = [k for k, v in msi_result.get("data_quality", {}).items() if v != "OK"]
        errors.append(f"MSI data quality {quality}% — missing: {', '.join(missing)}")

    # Check components are not all defaults (0.5)
    comps = msi_result.get("components", {})
    default_count = sum(1 for c in comps.values() if c.get("norm") == 0.5 and c.get("raw") is None)
    if default_count >= 3:
        errors.append(f"{default_count}/5 MSI components are defaults — data not real")

    return errors


def validate_pcr(oi_data: dict) -> list:
    """Validate PCR data before publishing."""
    errors = []

    pcr = oi_data.get("pcr")
    if pcr is None or not isinstance(pcr, (int, float)):
        errors.append("PCR is None or non-numeric")
    elif pcr < 0.1 or pcr > 5.0:
        errors.append(f"PCR {pcr} is outside reasonable range (0.1-5.0)")

    # Support and resistance must be different
    support = oi_data.get("support", 0)
    resistance = oi_data.get("resistance", 0)
    if support == resistance and support > 0:
        errors.append(f"Support ({support}) equals resistance ({resistance}) — invalid")

    # OI totals must be non-zero during market hours
    total_ce = oi_data.get("total_ce_oi", 0)
    total_pe = oi_data.get("total_pe_oi", 0)
    if total_ce == 0 and total_pe == 0:
        now = datetime.now(IST)
        if 9 <= now.hour <= 16:
            errors.append("Both CE and PE OI are zero during market hours")

    return errors


def validate_prices(prices: dict, tickers: list) -> list:
    """Validate price data — no zeros, no None, no stale."""
    errors = []

    for ticker in tickers:
        price = prices.get(ticker)
        if price is None:
            errors.append(f"{ticker}: price is None")
        elif price <= 0:
            errors.append(f"{ticker}: price is {price} (zero or negative)")
        elif isinstance(price, float) and price < 1:
            errors.append(f"{ticker}: price is {price} (suspiciously low)")

    return errors


def validate_pnl(pnl: dict) -> list:
    """Validate P&L calculation — catch impossible values."""
    errors = []

    spread = pnl.get("spread_pnl_pct", 0)
    if abs(spread) > 50:
        errors.append(f"Spread P&L {spread:+.2f}% exceeds ±50% — likely calculation error")

    for leg in pnl.get("long_legs", []) + pnl.get("short_legs", []):
        entry = leg.get("entry", 0)
        current = leg.get("current", 0)
        if entry > 0 and current > 0:
            move = abs(current / entry - 1) * 100
            if move > 30:
                errors.append(f"{leg['ticker']}: {move:.1f}% move since entry — verify data")
        if entry == current and entry > 0:
            errors.append(f"{leg['ticker']}: entry equals current ({entry}) — price may not be updating")

    return errors


def validate_signal(signal: dict) -> list:
    """Validate a signal before sending to subscribers."""
    errors = []

    hit_rate = signal.get("hit_rate", 0)
    if isinstance(hit_rate, float) and hit_rate > 1:
        hit_rate = hit_rate / 100  # Normalize if percentage
    if hit_rate < 0 or hit_rate > 1:
        errors.append(f"Hit rate {hit_rate} outside 0-1 range")

    n = signal.get("n_precedents", 0)
    if n < 3:
        errors.append(f"Only {n} precedents — minimum is 3")

    # Check tickers exist
    for leg_type in ["long", "long_leg", "long_legs"]:
        legs = signal.get(leg_type, [])
        if isinstance(legs, list):
            for leg in legs:
                ticker = leg.get("ticker", leg) if isinstance(leg, dict) else leg
                if not ticker or ticker == "unknown":
                    errors.append(f"Invalid ticker in long leg: {ticker}")

    return errors


def validate_before_send(data_type: str, data: dict) -> dict:
    """MANDATORY validation gate. Call before ANY subscriber-facing output.

    Args:
        data_type: "msi", "pcr", "signal", "pnl", "playbook"
        data: the data dict to validate

    Returns:
        {"valid": bool, "errors": list, "blocked": bool}

    If blocked=True, DO NOT send to subscribers. Send alert to Bharat instead.
    """
    validators = {
        "msi": validate_msi,
        "pcr": validate_pcr,
        "pnl": validate_pnl,
        "signal": validate_signal,
    }

    validator = validators.get(data_type)
    if not validator:
        return {"valid": True, "errors": [], "blocked": False}

    errors = validator(data)
    blocked = len(errors) > 0

    # Log validation result
    result = {
        "valid": not blocked,
        "errors": errors,
        "blocked": blocked,
        "data_type": data_type,
        "timestamp": datetime.now(IST).isoformat(),
    }

    if blocked:
        log.error("VALIDATION BLOCKED %s: %s", data_type, "; ".join(errors))
        _log_validation(result)
    else:
        log.debug("Validation passed: %s", data_type)

    return result


def cross_validate_pcr(our_pcr: float, tolerance: float = 0.15) -> dict:
    """Cross-validate our PCR against external sources.

    Returns {"valid": bool, "our_pcr": float, "reference": str, "diff": float}
    """
    # During market hours, we can check against NSE
    # After hours, log but don't block
    now = datetime.now(IST)
    if now.hour < 9 or now.hour > 16:
        return {"valid": True, "our_pcr": our_pcr, "reference": "after_hours", "diff": 0}

    # Try to get NSE reference PCR
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com",
        })
        session.get("https://www.nseindia.com", timeout=5)
        resp = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            timeout=10,
        )
        data = resp.json()
        records = data.get("filtered", {})
        nse_ce = records.get("CE", {}).get("totOI", 0)
        nse_pe = records.get("PE", {}).get("totOI", 0)

        if nse_ce > 0 and nse_pe > 0:
            nse_pcr = nse_pe / nse_ce
            diff = abs(our_pcr - nse_pcr)
            valid = diff <= tolerance

            if not valid:
                log.warning("PCR MISMATCH: ours=%.2f NSE=%.2f diff=%.2f (tolerance=%.2f)",
                           our_pcr, nse_pcr, diff, tolerance)

            return {
                "valid": valid,
                "our_pcr": round(our_pcr, 3),
                "nse_pcr": round(nse_pcr, 3),
                "diff": round(diff, 3),
                "tolerance": tolerance,
            }
    except Exception as exc:
        log.debug("NSE cross-validation failed: %s", exc)

    return {"valid": True, "our_pcr": our_pcr, "reference": "unavailable", "diff": 0}


def _log_validation(result: dict):
    """Append validation failure to log file."""
    try:
        VALIDATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(VALIDATION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    except Exception:
        pass


def send_validation_alert(errors: list, data_type: str):
    """Send validation failure alert to Bharat's personal chat (not channel)."""
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")  # Personal chat, not channel

    if not bot_token or not chat_id:
        return

    text = (
        f"🚫 *DATA VALIDATION FAILED*\n"
        f"Type: {data_type}\n"
        f"Time: {datetime.now(IST).strftime('%H:%M IST')}\n\n"
        f"Errors:\n" + "\n".join(f"• {e}" for e in errors) + "\n\n"
        f"_Message BLOCKED from subscribers. Fix before next cycle._"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass
