"""EODHD intraday capabilities probe — what does the NEW $29.99 plan unlock?

Goals:
  1. How far back does 1m / 5m / 1h actually go?
  2. Is mid-cap intraday available (HAL, TATAMOTORS)?
  3. Is volume data complete on every interval?
  4. What's the per-day trading window coverage?
  5. What's the cost-per-call so we can plan a 5y backfill quota budget?

Outputs:
  pipeline/data/research/eodhd_probe/<date>/intraday_capabilities.json
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "pipeline" / "data" / "research" / "eodhd_probe" / date.today().isoformat() / "intraday_capabilities.json"


def _api_key() -> str:
    for p in (REPO / "pipeline" / ".env", REPO / ".env"):
        if p.is_file():
            for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.strip().startswith("EODHD_API_KEY="):
                    return ln.split("=", 1)[1].strip()
    return os.environ["EODHD_API_KEY"]


def _intraday(symbol: str, interval: str, *, from_epoch: int | None = None,
              to_epoch: int | None = None) -> tuple[int, list[dict] | str]:
    params = {"interval": interval, "api_token": _api_key(), "fmt": "json"}
    if from_epoch is not None:
        params["from"] = from_epoch
    if to_epoch is not None:
        params["to"] = to_epoch
    url = f"https://eodhd.com/api/intraday/{symbol}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "askanka/1.0"})
    try:
        with urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
        return r.status, json.loads(body)
    except Exception as e:
        return 0, f"ERROR {type(e).__name__}: {e}"


def _epoch(d: date) -> int:
    return int(time.mktime(d.timetuple()))


def main() -> int:
    out = {"probed_at": datetime.utcnow().isoformat() + "Z", "probes": {}}

    print("=== Probe 1: 1m depth — how far back? ===")
    # EODHD's 1m endpoint typically caps history. Walk back through years.
    for years_back in (0, 1, 2, 3, 5):
        target = date.today() - timedelta(days=365 * years_back + 30)
        status, body = _intraday("RELIANCE.NSE", "1m",
                                 from_epoch=_epoch(target),
                                 to_epoch=_epoch(target + timedelta(days=2)))
        if isinstance(body, list):
            n = len(body)
            first = body[0].get("datetime") if body else None
            last = body[-1].get("datetime") if body else None
            print(f"  years_back={years_back} ({target.isoformat()}): "
                  f"n={n}, first={first}, last={last}")
            out["probes"].setdefault("1m_depth", {})[str(years_back)] = {
                "target_date": target.isoformat(),
                "n": n, "first": first, "last": last,
            }
        else:
            print(f"  years_back={years_back} ({target.isoformat()}): {body}")
            out["probes"].setdefault("1m_depth", {})[str(years_back)] = {
                "target_date": target.isoformat(), "error": str(body),
            }
        time.sleep(0.4)

    print("\n=== Probe 2: 5m depth ===")
    for years_back in (0, 2, 5, 6):
        target = date.today() - timedelta(days=365 * years_back + 30)
        status, body = _intraday("RELIANCE.NSE", "5m",
                                 from_epoch=_epoch(target),
                                 to_epoch=_epoch(target + timedelta(days=5)))
        if isinstance(body, list):
            n = len(body)
            first = body[0].get("datetime") if body else None
            last = body[-1].get("datetime") if body else None
            print(f"  years_back={years_back} ({target.isoformat()}): n={n}, first={first}")
            out["probes"].setdefault("5m_depth", {})[str(years_back)] = {
                "target_date": target.isoformat(), "n": n, "first": first, "last": last,
            }
        time.sleep(0.4)

    print("\n=== Probe 3: 1h depth ===")
    for years_back in (0, 5, 8):
        target = date.today() - timedelta(days=365 * years_back + 30)
        status, body = _intraday("RELIANCE.NSE", "1h",
                                 from_epoch=_epoch(target),
                                 to_epoch=_epoch(target + timedelta(days=10)))
        if isinstance(body, list):
            n = len(body)
            first = body[0].get("datetime") if body else None
            print(f"  years_back={years_back} ({target.isoformat()}): n={n}, first={first}")
            out["probes"].setdefault("1h_depth", {})[str(years_back)] = {
                "target_date": target.isoformat(), "n": n, "first": first,
            }
        time.sleep(0.4)

    print("\n=== Probe 4: Mid-cap coverage ===")
    midcaps = ["HAL.NSE", "TATAMOTORS.NSE", "BEL.NSE", "MAZDOCK.NSE",
               "LAURUSLABS.NSE", "TRENT.NSE"]
    for sym in midcaps:
        target = date.today() - timedelta(days=10)
        status, body = _intraday(sym, "1m",
                                 from_epoch=_epoch(target),
                                 to_epoch=_epoch(target + timedelta(days=2)))
        if isinstance(body, list):
            n = len(body)
            print(f"  {sym}: n={n}")
            out["probes"].setdefault("midcap_1m", {})[sym] = {"n": n}
        else:
            print(f"  {sym}: {body}")
            out["probes"].setdefault("midcap_1m", {})[sym] = {"error": str(body)}
        time.sleep(0.4)

    print("\n=== Probe 5: Volume completeness (1m vs 5m vs 1h) ===")
    target = date.today() - timedelta(days=10)
    for interval in ("1m", "5m", "1h"):
        status, body = _intraday("RELIANCE.NSE", interval,
                                 from_epoch=_epoch(target),
                                 to_epoch=_epoch(target + timedelta(days=2)))
        if isinstance(body, list) and body:
            n_total = len(body)
            n_with_vol = sum(1 for b in body if b.get("volume") is not None
                             and b.get("volume", 0) > 0)
            print(f"  {interval}: total={n_total}, with-volume={n_with_vol} "
                  f"({100*n_with_vol/n_total:.1f}%)")
            out["probes"].setdefault("volume_completeness", {})[interval] = {
                "total": n_total, "with_volume": n_with_vol,
                "pct": round(100 * n_with_vol / n_total, 1),
            }
        time.sleep(0.4)

    print("\n=== Probe 6: Per-day bar count for 1m on a known full trading day ===")
    # NSE: 09:15 -> 15:30 = 375 minutes. Expect ~375 bars/day for 1m.
    last_trading_day = date(2026, 4, 30)  # known full Thu
    status, body = _intraday("RELIANCE.NSE", "1m",
                             from_epoch=_epoch(last_trading_day),
                             to_epoch=_epoch(last_trading_day + timedelta(days=1)))
    if isinstance(body, list):
        n = len(body)
        print(f"  RELIANCE.NSE 1m on {last_trading_day}: n={n} (expected ~375)")
        out["probes"]["per_day_1m_bars"] = {
            "date": last_trading_day.isoformat(), "n_bars": n,
            "expected_full_day": 375,
            "coverage_pct": round(100 * n / 375, 1) if n else 0,
        }

    print("\n=== Summary ===")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"  capabilities -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
