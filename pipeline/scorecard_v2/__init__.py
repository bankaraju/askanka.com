"""Scorecard V2 — Sector-anchored management & financial intelligence."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .sector_mapper import SectorMapper
from .metric_extractor import MetricExtractor
from .financial_scorer import score_sector
from .management_quant import compute_management_quant
from .composite_ranker import compute_composite, forced_rank_sector, generate_remark, compute_confidence

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "config" / "sector_taxonomy.json"
_DEFAULT_ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "opus" / "artifacts"
_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent.parent / "data" / "trust_scores_v2.json"


def run_scorecard_v2(
    taxonomy_path: Path = _DEFAULT_TAXONOMY,
    artifacts_dir: Path = _DEFAULT_ARTIFACTS,
    output_path: Path = _DEFAULT_OUTPUT,
    skip_llm: bool = False,
) -> dict:
    log.info("Scorecard V2: starting")

    # Step 1-2: Map stocks to sectors
    mapper = SectorMapper(taxonomy_path, artifacts_dir)
    stock_map = mapper.map_all()
    log.info("Mapped %d stocks to sectors", len(stock_map))

    # Step 3: Extract metrics
    extractor = MetricExtractor(artifacts_dir)
    all_metrics = {}
    for symbol in stock_map:
        all_metrics[symbol] = extractor.extract(symbol)

    # Step 4-5: Score by sector
    all_scores = {}
    for sector in mapper.get_all_sectors():
        peers = mapper.get_sector_peers(sector)
        if not peers:
            continue
        kpis = mapper.get_sector_kpis(sector)
        weights = mapper.get_composite_weights(sector)

        # Financial scores
        sector_metrics = {s: all_metrics[s] for s in peers if s in all_metrics}
        fin_scores = score_sector(sector_metrics, kpis) if sector_metrics else {}

        # Management quant scores
        mgmt_quant_scores = {}
        for s in peers:
            m = all_metrics.get(s, {})
            mgmt_quant_scores[s] = compute_management_quant(m)

        # Management LLM scores (skip_llm = use quant only)
        mgmt_llm_scores = {}
        if not skip_llm:
            pass  # Task 7 adds LLM scoring here

        # Blend management
        for s in peers:
            quant = mgmt_quant_scores.get(s, 50)
            llm = mgmt_llm_scores.get(s, quant)  # fallback to quant if no LLM
            mgmt_score = 0.5 * quant + 0.5 * llm
            all_scores[s] = {
                "financial_score": round(fin_scores.get(s, 50), 1),
                "management_score": round(mgmt_score, 1),
                "sector": sector,
                "display_name": stock_map[s]["display_name"],
            }

        # Forced rank within sector
        sector_stocks = {s: all_scores[s] for s in peers if s in all_scores}
        ranked = forced_rank_sector(sector_stocks, weights)
        for s, r in ranked.items():
            all_scores[s].update(r)

    # Generate remarks and confidence
    for s in all_scores:
        m = all_metrics.get(s, {})
        data_sources = sum(1 for k in ["has_screener", "has_indianapi"] if m.get(k, False))
        all_scores[s]["confidence"] = compute_confidence(
            m.get("coverage_pct", 0), data_sources,
        )
        all_scores[s]["grade_reason"] = generate_remark({
            "symbol": s, **all_scores[s],
            "biggest_strength": m.get("biggest_strength", ""),
            "biggest_red_flag": m.get("biggest_red_flag", ""),
        })
        all_scores[s]["low_peer_count"] = mapper.is_low_peer_count(
            all_scores[s].get("sector", "")
        )

    # Build output
    stocks_list = []
    for s in sorted(all_scores, key=lambda x: all_scores[x].get("composite_score", 0), reverse=True):
        entry = {"symbol": s, **all_scores[s]}
        stocks_list.append(entry)

    output = {
        "version": "2.0",
        "updated_at": datetime.now(IST).isoformat(),
        "total_scored": len(stocks_list),
        "stocks": stocks_list,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("Scorecard V2: wrote %d stocks to %s", len(stocks_list), output_path)

    return output
