"""Build ssf_availability.json from the F&O universe (v1 conservative default).

Output schema: {ticker: {"is_ssf_available": bool, "borrow_cost_bps": int, "notes": str}}

For v1 we use a conservative default: all F&O tickers are SSF-available at 25 bps
(the Zerodha ballpark for most names). A v2 would call Kite's instrument API
and the NSE SLB API for per-ticker truth.

Path note: FNO_DIR is pipeline/data/fno_historical/ (213 CSVs), not
pipeline/data/india_historical/fno_stocks/ which does not exist. Matches
pipeline.autoresearch.overshoot_reversion_backtest._FNO_DIR.
"""
from __future__ import annotations

import json

from pipeline.autoresearch.regime_autoresearch.constants import FNO_DIR, REPO_ROOT

OUT = REPO_ROOT / "pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json"
DEFAULT_BORROW_BPS = 25
HIGH_BORROW_TICKERS = {"IRCTC": 80, "VEDL": 60, "ADANIENT": 100, "ADANIPOWER": 100}


def main() -> int:
    tickers = sorted(p.stem for p in FNO_DIR.glob("*.csv"))
    table = {}
    for t in tickers:
        table[t] = {
            "is_ssf_available": True,
            "borrow_cost_bps": HIGH_BORROW_TICKERS.get(t, DEFAULT_BORROW_BPS),
            "notes": "v1 default; refresh via Kite + NSE SLB in v2",
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(table)} tickers to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
