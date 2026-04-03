"""
Anka Research Pipeline — Kite Connect Auto-Authentication
Fully automated daily token refresh. No manual intervention required.

Run at 08:15 IST every trading day via schtasks (refresh_kite.bat).
Credentials stored in .env — never in code.
"""

import hashlib
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pyotp
import requests
from dotenv import load_dotenv, set_key

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("anka.kite_auth")

ENV_FILE = Path(__file__).parent / ".env"

IST = timezone(timedelta(hours=5, minutes=30))


def _env(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        raise RuntimeError(f"Missing env var: {key}")
    return val


def refresh_access_token() -> str:
    """Run the full Kite login flow and return a fresh access token.

    Flow:
      1. POST /api/login  (user_id + password)
      2. POST /api/twofa  (request_id + computed TOTP)
      3. GET  /connect/login → redirect captures request_token
      4. POST /session/token (request_token + checksum) → access_token
      5. Write access_token to .env KITE_ACCESS_TOKEN

    Raises RuntimeError on any failure.
    """
    api_key    = _env("KITE_API_KEY")
    api_secret = _env("KITE_API_SECRET")
    user_id    = _env("KITE_USER_ID")
    password   = _env("KITE_PASSWORD")
    totp_secret = _env("KITE_TOTP_SECRET")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    # ── Step 1: Password login ────────────────────────────────────────────
    r1 = session.post("https://kite.zerodha.com/api/login", data={
        "user_id": user_id,
        "password": password,
    }, timeout=15)
    r1.raise_for_status()
    data1 = r1.json()
    if data1.get("status") != "success":
        raise RuntimeError(f"Login failed: {data1.get('message')}")
    request_id = data1["data"]["request_id"]
    log.debug("Step 1 OK — request_id: %s", request_id[:12])

    # ── Step 2: TOTP ─────────────────────────────────────────────────────
    totp_code = pyotp.TOTP(totp_secret).now()
    r2 = session.post("https://kite.zerodha.com/api/twofa", data={
        "user_id":     user_id,
        "request_id":  request_id,
        "twofa_value": totp_code,
        "twofa_type":  "totp",
    }, timeout=15)
    r2.raise_for_status()
    if r2.json().get("status") != "success":
        raise RuntimeError(f"TOTP failed: {r2.json().get('message')}")
    log.debug("Step 2 OK — TOTP verified")

    # ── Step 3: Capture request_token from redirect ───────────────────────
    request_token = None
    try:
        session.get(
            "https://kite.zerodha.com/connect/login",
            params={"api_key": api_key, "v": "3"},
            allow_redirects=True,
            timeout=15,
        )
    except Exception as exc:
        match = re.search(r"request_token=([A-Za-z0-9]+)", str(exc))
        if match:
            request_token = match.group(1)

    if not request_token:
        raise RuntimeError("Could not extract request_token from redirect")
    log.debug("Step 3 OK — request_token: %s", request_token[:10])

    # ── Step 4: Exchange for access_token ────────────────────────────────
    checksum = hashlib.sha256(
        (api_key + request_token + api_secret).encode()
    ).hexdigest()
    r4 = requests.post("https://api.kite.trade/session/token", data={
        "api_key":       api_key,
        "request_token": request_token,
        "checksum":      checksum,
    }, timeout=15)
    r4.raise_for_status()
    if r4.json().get("status") != "success":
        raise RuntimeError(f"Token exchange failed: {r4.json().get('message')}")

    access_token = r4.json()["data"]["access_token"]
    log.info("Access token refreshed at %s IST",
             datetime.now(IST).strftime("%H:%M"))

    # ── Step 5: Persist to .env ───────────────────────────────────────────
    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token)
    log.debug("Saved KITE_ACCESS_TOKEN to .env")

    return access_token


def get_kite_client():
    """Return an authenticated KiteConnect instance.

    Uses the access token already in .env. If it is missing or expired,
    attempts a fresh refresh automatically.
    """
    from kiteconnect import KiteConnect
    api_key = _env("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN", "")

    kite = KiteConnect(api_key=api_key)

    if not access_token:
        log.info("No access token — refreshing now")
        access_token = refresh_access_token()

    kite.set_access_token(access_token)

    # Quick validity check
    try:
        kite.profile()
    except Exception:
        log.info("Access token expired — refreshing")
        access_token = refresh_access_token()
        kite.set_access_token(access_token)

    return kite


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        token = refresh_access_token()
        print(f"Token refreshed OK: {token[:12]}...")

        # Smoke test: live prices
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
        kite.set_access_token(token)
        prices = kite.ltp(["NSE:HAL", "NSE:TCS", "NSE:COALINDIA", "NSE:HPCL"])
        for sym, d in prices.items():
            print(f"  {sym}: Rs{d['last_price']:,.2f}")
        print("Kite live data: OK")
        sys.exit(0)
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
