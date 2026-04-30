"""EODHD capabilities probe — what does the All-In-One plan actually deliver
for Indian markets? Pricing page is opaque; this script answers via 6 API calls.

Probes
------
1. /api/exchanges-list — does NSE / BSE / etc. show up?
2. /api/exchange-symbol-list/NSE — how many tickers?
3. /api/exchange-symbol-list/BSE — how many tickers?
4. /api/eod/RELIANCE.NSE — EOD bars (depth, latest date)
5. /api/intraday/RELIANCE.NSE?interval=1m — 1-min intraday availability
6. /api/news?s=RELIANCE.NSE&from=2019-01-01&to=2019-03-31 — pre-2020 news depth
7. /api/sentiments?s=RELIANCE.NSE — sentiment-bundled output
8. /api/intraday/RELIANCE.NSE?interval=5m — 5-min intraday
9. /api/user — quota / plan info
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "pipeline" / "data" / "research" / "eodhd_probe" / date.today().isoformat() / "capabilities.json"


def _api_key() -> str:
    k = os.environ.get("EODHD_API_KEY")
    if k:
        return k
    for p in (REPO / ".env", REPO / "pipeline" / ".env"):
        if p.is_file():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.strip().startswith("EODHD_API_KEY="):
                    return ln.split("=", 1)[1].strip()
    raise SystemExit("EODHD_API_KEY missing")


def _get(path: str, **params) -> tuple[int, object | str]:
    params["api_token"] = _api_key()
    params.setdefault("fmt", "json")
    qs = urlencode(params)
    url = f"https://eodhd.com{path}?{qs}"
    req = Request(url, headers={"User-Agent": "askanka/1.0"})
    try:
        with urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
            ctype = r.headers.get("content-type", "")
        if "json" in ctype.lower():
            return r.status, json.loads(body)
        return r.status, body[:1000]
    except Exception as e:
        return 0, f"ERROR {type(e).__name__}: {e}"


def main() -> int:
    out: dict = {"probed_at": date.today().isoformat(), "probes": {}}

    # 1. exchanges-list
    status, body = _get("/api/exchanges-list/")
    indian = []
    if isinstance(body, list):
        for ex in body:
            name = (ex.get("Name") or "").lower()
            code = ex.get("Code") or ""
            if any(k in name for k in ("india", "national stock", "bombay", "mumbai")):
                indian.append({"code": code, "name": ex.get("Name"),
                               "country": ex.get("Country"), "currency": ex.get("Currency")})
            elif code in ("NSE", "BSE", "INDIA", "NSEI", "BOM"):
                indian.append({"code": code, "name": ex.get("Name"),
                               "country": ex.get("Country"), "currency": ex.get("Currency")})
    out["probes"]["1_exchanges_list"] = {
        "status": status,
        "n_total_exchanges": len(body) if isinstance(body, list) else None,
        "indian_matches": indian,
    }
    print(f"1. exchanges_list: {status}, found {len(indian)} Indian matches")
    for ix in indian:
        print(f"   {ix['code']:8s} {ix['name']} ({ix.get('currency')})")

    # 2. NSE ticker count
    status, body = _get("/api/exchange-symbol-list/NSE")
    out["probes"]["2_nse_tickers"] = {
        "status": status,
        "n_tickers": (body.count("\n") if isinstance(body, str) else
                      len(body) if isinstance(body, list) else None),
        "first_5": (body.splitlines()[:5] if isinstance(body, str) else
                    body[:5] if isinstance(body, list) else None),
    }
    print(f"2. NSE tickers: {status}, n={out['probes']['2_nse_tickers']['n_tickers']}")

    # 3. BSE ticker count
    status, body = _get("/api/exchange-symbol-list/BSE")
    out["probes"]["3_bse_tickers"] = {
        "status": status,
        "n_tickers": (body.count("\n") if isinstance(body, str) else
                      len(body) if isinstance(body, list) else None),
    }
    print(f"3. BSE tickers: {status}, n={out['probes']['3_bse_tickers']['n_tickers']}")

    # 4. EOD depth — RELIANCE.NSE
    status, body = _get("/api/eod/RELIANCE.NSE")
    if isinstance(body, list) and body:
        first = body[0].get("date")
        last = body[-1].get("date")
        out["probes"]["4_eod_depth"] = {
            "status": status, "n_bars": len(body),
            "first": first, "last": last,
        }
        print(f"4. RELIANCE.NSE EOD: n={len(body)} bars, {first} -> {last}")
    else:
        out["probes"]["4_eod_depth"] = {"status": status, "body_preview": str(body)[:200]}
        print(f"4. RELIANCE.NSE EOD: {status} non-list response")

    # 5. Intraday 1m — last 3 days (epoch seconds)
    import time
    from datetime import datetime
    three_days_ago = int(time.mktime((date.today() - timedelta(days=3)).timetuple()))
    status, body = _get("/api/intraday/RELIANCE.NSE", interval="1m",
                        **{"from": three_days_ago})
    if isinstance(body, list):
        out["probes"]["5_intraday_1m"] = {
            "status": status, "n_bars": len(body),
            "first": body[0] if body else None,
            "last": body[-1] if body else None,
        }
        print(f"5. RELIANCE.NSE 1m intraday: n={len(body)}")
    else:
        out["probes"]["5_intraday_1m"] = {"status": status, "body_preview": str(body)[:300]}
        print(f"5. RELIANCE.NSE 1m: {status} {str(body)[:120]}")

    # 6. Pre-2020 news depth
    status, body = _get("/api/news", s="RELIANCE.NSE", **{"from": "2019-01-01", "to": "2019-03-31", "limit": 1000})
    out["probes"]["6_news_2019Q1"] = {
        "status": status,
        "n_news": len(body) if isinstance(body, list) else None,
        "earliest_date": (min((h.get("date","") for h in body), default=None)
                          if isinstance(body, list) and body else None),
    }
    print(f"6. RELIANCE.NSE news Q1 2019: n={out['probes']['6_news_2019Q1']['n_news']}")

    # 7. Sentiment bundle
    status, body = _get("/api/sentiments", s="RELIANCE.NSE")
    out["probes"]["7_sentiments"] = {
        "status": status,
        "type": type(body).__name__,
        "size_bytes": len(json.dumps(body)) if isinstance(body, (dict, list)) else len(str(body)),
        "preview": (str(body)[:300] if not isinstance(body, (dict, list))
                    else json.dumps(body, default=str)[:300]),
    }
    print(f"7. RELIANCE.NSE sentiments: {status}, "
          f"size={out['probes']['7_sentiments']['size_bytes']} bytes")

    # 8. Intraday 5m availability
    status, body = _get("/api/intraday/RELIANCE.NSE", interval="5m")
    out["probes"]["8_intraday_5m"] = {
        "status": status,
        "n_bars": len(body) if isinstance(body, list) else None,
        "first": body[0] if isinstance(body, list) and body else None,
    }
    print(f"8. RELIANCE.NSE 5m intraday: status={status}, n={out['probes']['8_intraday_5m']['n_bars']}")

    # 9. /api/user — plan info
    status, body = _get("/api/user")
    out["probes"]["9_user_plan"] = {
        "status": status,
        "plan_info": body if isinstance(body, dict) else str(body)[:300],
    }
    if isinstance(body, dict):
        print(f"9. plan: {body.get('subscriptionType', '?')}, "
              f"calls today: {body.get('apiRequests', '?')} of {body.get('dailyRateLimit', '?')}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nfull capabilities -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
