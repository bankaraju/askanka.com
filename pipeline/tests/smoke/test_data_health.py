"""
Smoke Tests — Data Health Checks
Run before any signal generation to verify all data sources are alive.
Returns PASS / FAIL / DEGRADED for each source.

Usage:
    python tests/smoke/test_data_health.py
"""

import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

IST = timezone(timedelta(hours=5, minutes=30))
RESULTS = []


def check(name, test_fn):
    """Run a check and record PASS/FAIL/DEGRADED."""
    try:
        result = test_fn()
        status = result.get("status", "FAIL")
        detail = result.get("detail", "")
        RESULTS.append({"name": name, "status": status, "detail": detail})
        emoji = {"PASS": "✅", "FAIL": "❌", "DEGRADED": "⚠️"}.get(status, "?")
        print(f"  {emoji} {name}: {status} — {detail}")
    except Exception as e:
        RESULTS.append({"name": name, "status": "FAIL", "detail": str(e)[:100]})
        print(f"  ❌ {name}: FAIL — {str(e)[:100]}")


def test_eodhd():
    from eodhd_client import fetch_eod_series
    data = fetch_eod_series("SPY.US", days=5)
    if data and len(data) >= 2:
        last_date = data[-1].get("date", "?")
        return {"status": "PASS", "detail": f"SPY.US: {len(data)} days, last={last_date}"}
    return {"status": "FAIL", "detail": f"Got {len(data) if data else 0} days"}


def test_kite_auth():
    from kite_client import get_kite
    kite = get_kite()
    if kite:
        return {"status": "PASS", "detail": "Kite authenticated"}
    return {"status": "FAIL", "detail": "No Kite connection"}


def test_kite_ltp():
    from kite_client import fetch_ltp
    prices = fetch_ltp(["NIFTY 50", "INDIA VIX"])
    nifty = prices.get("NIFTY 50", 0)
    vix = prices.get("INDIA VIX", 0)
    if nifty > 0 and vix > 0:
        return {"status": "PASS", "detail": f"Nifty={nifty:.0f}, VIX={vix:.1f}"}
    elif nifty > 0:
        return {"status": "DEGRADED", "detail": f"Nifty={nifty:.0f}, VIX missing"}
    return {"status": "FAIL", "detail": "No LTP data"}


def test_nse_flows():
    from macro_stress import _fetch_institutional_flow
    flows = _fetch_institutional_flow()
    if flows and flows.get("fii_net") is not None:
        return {"status": "PASS", "detail": f"FII={flows['fii_net']:+,.0f}, DII={flows.get('dii_net',0):+,.0f}"}
    return {"status": "DEGRADED", "detail": "No flow data (may be holiday)"}


def test_etf_weights():
    path = Path(__file__).parent.parent.parent / "autoresearch" / "etf_optimal_weights.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        n_weights = len(data.get("optimal_weights", {}))
        return {"status": "PASS" if n_weights >= 15 else "DEGRADED",
                "detail": f"{n_weights} weights loaded"}
    return {"status": "FAIL", "detail": "etf_optimal_weights.json not found"}


def test_calm_zone():
    path = Path(__file__).parent.parent.parent / "autoresearch" / "calm_zone_analysis.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"status": "PASS", "detail": f"Calm center={data.get('calm_center', '?')}"}
    return {"status": "FAIL", "detail": "calm_zone_analysis.json not found"}


def test_options_oi():
    now = datetime.now(IST)
    if now.hour < 9 or now.hour > 16:
        return {"status": "DEGRADED", "detail": "Outside market hours — OI may be stale"}
    try:
        from options_monitor import fetch_nifty_oi
        oi = fetch_nifty_oi()
        if oi and oi.get("pcr", 0) > 0:
            return {"status": "PASS", "detail": f"PCR={oi['pcr']:.2f}"}
    except Exception as e:
        return {"status": "FAIL", "detail": str(e)[:80]}
    return {"status": "FAIL", "detail": "No OI data"}


def test_telegram():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        return {"status": "PASS", "detail": "Credentials present"}
    return {"status": "FAIL", "detail": "Missing TELEGRAM_BOT_TOKEN or CHAT_ID"}


def test_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key and key.startswith("sk-ant-"):
        return {"status": "PASS", "detail": "Key present and formatted correctly"}
    return {"status": "FAIL", "detail": "Missing or malformed ANTHROPIC_API_KEY"}


def test_gemini():
    key = os.getenv("GEMINI_API_KEY", "")
    if key and key.startswith("AIza"):
        return {"status": "PASS", "detail": "Key present"}
    return {"status": "DEGRADED", "detail": "Missing GEMINI_API_KEY — images won't generate"}


if __name__ == "__main__":
    print("=" * 50)
    print("SMOKE TESTS — Data Health Check")
    print(f"Time: {datetime.now(IST).strftime('%H:%M IST %Y-%m-%d')}")
    print("=" * 50)

    check("EODHD API", test_eodhd)
    check("Kite Auth", test_kite_auth)
    check("Kite LTP", test_kite_ltp)
    check("NSE Flows", test_nse_flows)
    check("ETF Weights", test_etf_weights)
    check("Calm Zone", test_calm_zone)
    check("Options OI", test_options_oi)
    check("Telegram", test_telegram)
    check("Anthropic API", test_anthropic)
    check("Gemini API", test_gemini)

    # Summary
    passes = sum(1 for r in RESULTS if r["status"] == "PASS")
    fails = sum(1 for r in RESULTS if r["status"] == "FAIL")
    degraded = sum(1 for r in RESULTS if r["status"] == "DEGRADED")

    print(f"\n{'='*50}")
    print(f"RESULT: {passes} PASS | {degraded} DEGRADED | {fails} FAIL")

    if fails > 0:
        print("STATUS: ❌ SYSTEM NOT READY — fix failures before running signals")
    elif degraded > 0:
        print("STATUS: ⚠️ DEGRADED — signals will run with reduced confidence")
    else:
        print("STATUS: ✅ ALL SYSTEMS GO")
    print("=" * 50)

    # Save results
    out = Path(__file__).parent.parent.parent / "artifacts" / "validation" / "smoke_test_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "timestamp": datetime.now(IST).isoformat(),
        "results": RESULTS,
        "summary": {"pass": passes, "fail": fails, "degraded": degraded},
    }, indent=2), encoding="utf-8")
