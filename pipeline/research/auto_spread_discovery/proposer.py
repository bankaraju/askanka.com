"""ASDE v0 — sector-pair candidate enumerator.

Reads sector taxonomy + SectorMapper to produce a frozen list of
(sector_a, sector_b, regime, hold) candidate cells. The output is the
denominator for the BH-FDR multiplicity correction in v1+.

Design lock — v0
----------------
- 24 sectors from sector_taxonomy.json minus 'Unmapped' = 23.
- Ordered pairs (a != b): 23 * 22 = 506 directional pairs.
- 5 regimes (RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA).
- 3 hold horizons (1, 3, 5).
- Total cell-family at proposal time: 506 * 5 * 3 = 7,590 cells.
- Per-side leg count: top-3 by 60d ADV. Cells where either side has
  fewer than 3 mappable F&O tickers are dropped (post-liquidity-filter
  size is recorded separately).

Output
------
- pipeline/data/research/auto_spread_discovery/candidates_<YYYY-MM-DD>.csv
  Columns: pair_id, sector_a, sector_b, regime, hold, status (ENUMERATED
  or DROPPED_LIQUIDITY), n_legs_a, n_legs_b, legs_a (semicolon-joined),
  legs_b, frozen_at.
- pipeline/data/research/auto_spread_discovery/cardinality_<YYYY-MM-DD>.json
  Family-size summary for BH-FDR bookkeeping.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TAXONOMY = REPO / "pipeline" / "config" / "sector_taxonomy.json"
OUT_DIR = REPO / "pipeline" / "data" / "research" / "auto_spread_discovery"

REGIMES = ("RISK-OFF", "CAUTION", "NEUTRAL", "RISK-ON", "EUPHORIA")
HOLDS = (1, 3, 5)
PER_SIDE_TOP_K = 3
EXCLUDE_SECTORS = ("Unmapped",)


@dataclass(frozen=True)
class Candidate:
    pair_id: str
    sector_a: str
    sector_b: str
    regime: str
    hold: int
    status: str
    n_legs_a: int
    n_legs_b: int
    legs_a: tuple[str, ...]
    legs_b: tuple[str, ...]
    frozen_at: str


def _load_sectors() -> list[str]:
    if not TAXONOMY.is_file():
        raise FileNotFoundError(f"sector taxonomy not found at {TAXONOMY}")
    doc = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    sectors = sorted(doc.get("sectors", {}).keys())
    return [s for s in sectors if s not in EXCLUDE_SECTORS]


def _ticker_to_sector() -> dict[str, str]:
    """Best-effort ticker->sector. Empty dict if SectorMapper unavailable."""
    try:
        from pipeline.scorecard_v2.sector_mapper import SectorMapper
        mapped = SectorMapper().map_all()
    except Exception:
        return {}
    return {t: (v.get("sector") or "Unmapped") for t, v in mapped.items()}


def _liquidity_rank(tickers: list[str]) -> list[str]:
    """Rank by 60d ADV (close * volume mean). Falls back to alphabetical
    when fno_historical data is unavailable.

    v0 uses an alphabetical fallback to keep the enumerator pure-stdlib;
    v1 will swap in the actual ADV computation from
    pipeline.data.fno_historical.
    """
    return sorted(tickers)[:PER_SIDE_TOP_K] if tickers else []


def enumerate_candidates(
    *,
    today: date | None = None,
    sectors: list[str] | None = None,
    ticker_map: dict[str, str] | None = None,
) -> list[Candidate]:
    today = today or date.today()
    sectors = sectors or _load_sectors()
    ticker_map = ticker_map if ticker_map is not None else _ticker_to_sector()

    by_sector: dict[str, list[str]] = {}
    for ticker, sector in ticker_map.items():
        by_sector.setdefault(sector, []).append(ticker)

    out: list[Candidate] = []
    frozen_iso = datetime.utcnow().isoformat() + "Z"
    for a in sectors:
        for b in sectors:
            if a == b:
                continue
            legs_a = tuple(_liquidity_rank(by_sector.get(a, [])))
            legs_b = tuple(_liquidity_rank(by_sector.get(b, [])))
            for regime in REGIMES:
                for hold in HOLDS:
                    pid = f"{a}__VS__{b}__{regime}__{hold}d"
                    if len(legs_a) < PER_SIDE_TOP_K or len(legs_b) < PER_SIDE_TOP_K:
                        status = "DROPPED_LIQUIDITY"
                    else:
                        status = "ENUMERATED"
                    out.append(Candidate(
                        pair_id=pid,
                        sector_a=a, sector_b=b,
                        regime=regime, hold=hold,
                        status=status,
                        n_legs_a=len(legs_a), n_legs_b=len(legs_b),
                        legs_a=legs_a, legs_b=legs_b,
                        frozen_at=frozen_iso,
                    ))
    return out


def write_outputs(candidates: list[Candidate], *, today: date | None = None) -> tuple[Path, Path]:
    today = today or date.today()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"candidates_{today.isoformat()}.csv"
    json_path = OUT_DIR / f"cardinality_{today.isoformat()}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow([
            "pair_id", "sector_a", "sector_b", "regime", "hold",
            "status", "n_legs_a", "n_legs_b", "legs_a", "legs_b", "frozen_at",
        ])
        for c in candidates:
            w.writerow([
                c.pair_id, c.sector_a, c.sector_b, c.regime, c.hold,
                c.status, c.n_legs_a, c.n_legs_b,
                ";".join(c.legs_a), ";".join(c.legs_b), c.frozen_at,
            ])

    enumerated = [c for c in candidates if c.status == "ENUMERATED"]
    dropped = [c for c in candidates if c.status == "DROPPED_LIQUIDITY"]
    summary = {
        "frozen_at": candidates[0].frozen_at if candidates else "",
        "n_total": len(candidates),
        "n_enumerated": len(enumerated),
        "n_dropped_liquidity": len(dropped),
        "n_distinct_sector_pairs_enumerated": len({(c.sector_a, c.sector_b) for c in enumerated}),
        "regimes": list(REGIMES),
        "holds": list(HOLDS),
        "per_side_top_k": PER_SIDE_TOP_K,
        "bh_fdr_denominator_v1": len(enumerated),
        "notes": [
            "v0 enumeration only; backtest call lands in v1.",
            "DROPPED_LIQUIDITY rows do NOT count toward BH-FDR denominator.",
            "Re-enumeration any time a new F&O ticker is added.",
        ],
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return csv_path, json_path


def main() -> int:
    today = date.today()
    candidates = enumerate_candidates(today=today)
    csv_path, json_path = write_outputs(candidates, today=today)
    enumerated = sum(1 for c in candidates if c.status == "ENUMERATED")
    dropped = sum(1 for c in candidates if c.status == "DROPPED_LIQUIDITY")
    print(f"ASDE v0 candidates -> {csv_path}")
    print(f"ASDE v0 cardinality -> {json_path}")
    print(f"  enumerated: {enumerated}")
    print(f"  dropped (liquidity): {dropped}")
    print(f"  total: {len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
