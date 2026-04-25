"""One-off: freeze peer cohorts for H-2026-04-25-001.

Reads the canonical sector taxonomy (via pipeline.scorecard_v2.sector_mapper)
and the per-stock IndianAPI snapshot (opus/artifacts/<SYM>/indianapi_stock.json)
for ``stockDetailsReusableData.marketCap`` (INR cr). Writes
``pipeline/data/earnings_calendar/peers_frozen.json`` keyed by today's date.

This is committed to the repository — re-freezing requires a new
hypothesis version per data validation policy §11.3 (point-in-time
correctness)."""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from pipeline.earnings_calendar.peers import freeze_peers
from pipeline.scorecard_v2.sector_mapper import SectorMapper

log = logging.getLogger("earnings_calendar.freeze_peers")

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "opus" / "artifacts"
OUT_PATH = REPO_ROOT / "pipeline" / "data" / "earnings_calendar" / "peers_frozen.json"


def _load_market_cap(symbol: str) -> float | None:
    p = ARTIFACTS_DIR / symbol / "indianapi_stock.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("indianapi_stock unreadable for %s: %s", symbol, exc)
        return None
    mcap = d.get("stockDetailsReusableData", {}).get("marketCap")
    if mcap is None:
        return None
    try:
        return float(mcap)
    except (TypeError, ValueError):
        return None


def build_meta() -> dict[str, tuple[str, float | None]]:
    mapper = SectorMapper()
    sectors = mapper.map_all()
    meta: dict[str, tuple[str, float | None]] = {}
    n_no_sector = 0
    n_no_mcap = 0
    for symbol, info in sectors.items():
        sector = info["sector"]
        if sector == "Unmapped":
            n_no_sector += 1
            continue
        mcap = _load_market_cap(symbol)
        if mcap is None:
            n_no_mcap += 1
            continue
        meta[symbol] = (sector, mcap)
    log.info(
        "freeze_peers meta: n=%d  unmapped_sector=%d  missing_mcap=%d",
        len(meta), n_no_sector, n_no_mcap,
    )
    return meta


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    meta = build_meta()
    asof = dt.date.today().isoformat()
    lineage = {
        "sector_source": "pipeline.scorecard_v2.sector_mapper.SectorMapper",
        "sector_taxonomy": "pipeline/config/sector_taxonomy.json",
        "industry_field": "indianapi.industry (per-stock)",
        "market_cap_source": "opus/artifacts/<SYM>/indianapi_stock.json :: stockDetailsReusableData.marketCap (INR cr)",
        "n_size_bucket_neighbours": 3,
        "min_peers": 1,
        "known_caveats": [
            "IndianAPI 'industry' tags are vendor-supplied and contain known errors (e.g. NAM-INDIA tagged 'Regional Banks'); these are quarantined at audit time per data validation policy §9.4 and not corrected in this freeze.",
            "Single-cap dominants (RELIANCE) get smaller peers because no equally-large peer exists in their sector — this is intended behaviour, not a bug.",
            "BHARTIARTL has only one peer (IDEA) because the Communications Services bucket has 2 F&O members — the cohort is real, not padded.",
        ],
    }
    out = freeze_peers(meta, OUT_PATH, asof=asof, lineage=lineage)
    payload = json.loads(out.read_text())
    n_with_peers = len(payload["cohorts"])
    n_total = len(meta)
    print(f"Wrote {out}")
    print(f"  frozen_at:        {asof}")
    print(f"  symbols_with_peers: {n_with_peers}/{n_total}")


if __name__ == "__main__":
    main()
