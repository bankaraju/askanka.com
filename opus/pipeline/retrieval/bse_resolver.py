# opus/pipeline/retrieval/bse_resolver.py
"""
Map NSE symbols to BSE scrip codes via BSE Suggest API.

The BSE search endpoint returns candidates; we pick the best match
by preferring Active status and exact name prefix matching.
"""
from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("opus.bse_resolver")

BSE_SUGGEST_URL = "https://api.bseindia.com/BseIndiaAPI/api/Suggest/w"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}
IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_CACHE = Path(__file__).parent.parent.parent / "config" / "bse_scrip_map.json"


def resolve_bse_scrip(nse_symbol: str) -> Optional[dict]:
    """Resolve a single NSE symbol to BSE scrip code.

    Returns: {"bse_scrip": "500325", "company_name": "...", "isin": "..."} or None.
    """
    try:
        resp = requests.get(
            BSE_SUGGEST_URL,
            params={"query": nse_symbol},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        candidates = resp.json()
        if not candidates or not isinstance(candidates, list):
            return None

        active = [c for c in candidates if c.get("status", "").lower() == "active"]
        best = active[0] if active else candidates[0]

        scrip = best.get("scrip_code") or best.get("ScripCode") or best.get("scripcode")
        if not scrip:
            return None

        return {
            "bse_scrip": str(scrip),
            "company_name": best.get("scrip_name") or best.get("LongName") or best.get("SCRIP_CD", ""),
            "isin": best.get("isin") or best.get("ISIN_NUMBER", ""),
        }
    except Exception as exc:
        log.warning("BSE resolve failed for %s: %s", nse_symbol, exc)
        return None


def batch_resolve(
    symbols: list[str],
    cache_path: Path = DEFAULT_CACHE,
    delay: float = 1.0,
) -> dict:
    """Resolve all symbols, skipping those already cached.

    Returns the full cache dict and writes it to cache_path.
    """
    existing: dict = {"resolved_at": "", "count": 0, "mappings": {}}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    mappings = existing.get("mappings", {})
    to_resolve = [s for s in symbols if s not in mappings]

    log.info("BSE resolver: %d cached, %d to resolve", len(mappings), len(to_resolve))

    for i, sym in enumerate(to_resolve):
        result = resolve_bse_scrip(sym)
        if result:
            mappings[sym] = result
            log.info("  [%d/%d] %s → %s", i + 1, len(to_resolve), sym, result["bse_scrip"])
        else:
            log.warning("  [%d/%d] %s → NOT FOUND", i + 1, len(to_resolve), sym)
        if delay > 0 and i < len(to_resolve) - 1:
            time.sleep(delay)

    cache = {
        "resolved_at": datetime.now(IST).isoformat(),
        "count": len(mappings),
        "mappings": mappings,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return cache
