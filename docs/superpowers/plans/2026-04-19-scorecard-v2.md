# Scorecard V2 — Sector-Anchored Management & Financial Intelligence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current inconsistent per-stock trust scores with a 3-layer sector-anchored scorecard: financial_score (pure quant) + management_score (quant + Sonnet LLM) → composite_score with forced sector ranking, rich remarks, and a redesigned terminal UI.

**Architecture:** Extract financial metrics from existing screener/IndianAPI artifacts (no new fetching). Compute percentile scores within each of 24 sector groups. Re-score management on Sonnet with sector-specific KPI rubrics. Blend into composite, forced-rank within sector, generate human-readable remarks. Serve through terminal API with heatmap table and expandable rows.

**Tech Stack:** Python 3.13, FastAPI, vanilla JS, Anthropic SDK (Sonnet 4.6), existing screener_financials.json + indianapi_stock.json artifacts.

**Design spec:** `docs/superpowers/specs/2026-04-19-scorecard-v2-design.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `pipeline/config/sector_taxonomy.json` | Sector definitions: industry→sector mapping, KPI weights, composite weights, overrides |
| `pipeline/scorecard_v2/__init__.py` | Public API: `run_scorecard_v2()` orchestrator |
| `pipeline/scorecard_v2/sector_mapper.py` | Map 213 stocks to sectors using taxonomy + indianapi |
| `pipeline/scorecard_v2/metric_extractor.py` | Extract raw metrics from screener/indianapi artifacts |
| `pipeline/scorecard_v2/financial_scorer.py` | Percentile scoring within sector, weighted by KPI config |
| `pipeline/scorecard_v2/management_quant.py` | Management quant score: ROE stability, pledge, CFO/PAT, margin vol |
| `pipeline/scorecard_v2/management_llm.py` | Sonnet re-score orchestrator + prompt templates |
| `pipeline/scorecard_v2/composite_ranker.py` | Composite blend, forced ranking, grade bands, remark generation |
| `pipeline/tests/test_sector_mapper.py` | Tests for sector mapping |
| `pipeline/tests/test_metric_extractor.py` | Tests for metric extraction |
| `pipeline/tests/test_financial_scorer.py` | Tests for percentile scoring |
| `pipeline/tests/test_management_quant.py` | Tests for management quant score |
| `pipeline/tests/test_composite_ranker.py` | Tests for composite + ranking + remarks |
| `pipeline/tests/test_scorecard_v2_integration.py` | End-to-end integration test |

### Modified files
| File | Change |
|------|--------|
| `pipeline/terminal/api/trust_scores.py` | Serve V2 scores from `trust_scores_v2.json`, add sector filter endpoint |
| `pipeline/terminal/static/js/pages/intelligence.js` | V2 table with heatmap, sector filter, expandable rows |
| `pipeline/website_exporter.py` | Export `trust_scores_v2.json` |
| `pipeline/signal_enrichment.py` | Use `sector_grade` for trust gate (after validation) |

---

## Task 1: Sector Taxonomy Config

**Files:**
- Create: `pipeline/config/sector_taxonomy.json`
- Create: `pipeline/scorecard_v2/sector_mapper.py`
- Create: `pipeline/tests/test_sector_mapper.py`

- [ ] **Step 1: Write failing test for sector_mapper**

```python
# pipeline/tests/test_sector_mapper.py
"""Tests for sector_mapper — maps stocks to normalized sectors."""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures"


def _make_taxonomy():
    return {
        "version": "2.0",
        "sectors": {
            "Banks": {
                "display_name": "Banks (Private & PSU)",
                "industries": ["Regional Banks"],
                "composite_weights": {"financial": 0.70, "management": 0.30},
                "kpis": [
                    {"name": "NIM", "direction": "higher", "weight": 0.20, "source": "derived"},
                    {"name": "ROA", "direction": "higher", "weight": 0.15, "source": "indianapi"},
                ],
            },
            "IT_Services": {
                "display_name": "IT Services",
                "industries": ["Software & Programming", "Computer Services"],
                "composite_weights": {"financial": 0.60, "management": 0.40},
                "kpis": [
                    {"name": "EBIT_Margin", "direction": "higher", "weight": 0.25, "source": "screener"},
                ],
            },
        },
        "overrides": {"RELIANCE": "Oil_Gas"},
        "common_kpis": ["ROE", "ROCE", "Revenue_Growth_3Y", "Debt_to_Equity", "CFO_PAT"],
    }


def _make_indianapi(industry: str) -> dict:
    return {"companyName": "Test Co", "industry": industry}


class TestSectorMapper:
    def test_maps_bank_by_industry(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        (artifacts / "HDFCBANK").mkdir(parents=True)
        (artifacts / "HDFCBANK" / "indianapi_stock.json").write_text(
            json.dumps(_make_indianapi("Regional Banks"))
        )
        mapper = SectorMapper(taxonomy_path, artifacts)
        result = mapper.map_all()
        assert result["HDFCBANK"]["sector"] == "Banks"
        assert result["HDFCBANK"]["display_name"] == "Banks (Private & PSU)"

    def test_override_takes_precedence(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        (artifacts / "RELIANCE").mkdir(parents=True)
        (artifacts / "RELIANCE" / "indianapi_stock.json").write_text(
            json.dumps(_make_indianapi("Oil & Gas - Integrated"))
        )
        mapper = SectorMapper(taxonomy_path, artifacts)
        result = mapper.map_all()
        assert result["RELIANCE"]["sector"] == "Oil_Gas"

    def test_unmapped_industry_gets_unmapped_sector(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        (artifacts / "WEIRDCO").mkdir(parents=True)
        (artifacts / "WEIRDCO" / "indianapi_stock.json").write_text(
            json.dumps(_make_indianapi("Underwater Basket Weaving"))
        )
        mapper = SectorMapper(taxonomy_path, artifacts)
        result = mapper.map_all()
        assert result["WEIRDCO"]["sector"] == "Unmapped"

    def test_missing_indianapi_still_maps_via_override(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        (artifacts / "RELIANCE").mkdir(parents=True)
        mapper = SectorMapper(taxonomy_path, artifacts)
        result = mapper.map_all()
        assert result["RELIANCE"]["sector"] == "Oil_Gas"

    def test_sector_peer_lists(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        for sym in ["HDFCBANK", "ICICIBANK", "SBIN"]:
            (artifacts / sym).mkdir(parents=True)
            (artifacts / sym / "indianapi_stock.json").write_text(
                json.dumps(_make_indianapi("Regional Banks"))
            )
        mapper = SectorMapper(taxonomy_path, artifacts)
        result = mapper.map_all()
        peers = mapper.get_sector_peers("Banks")
        assert set(peers) == {"HDFCBANK", "ICICIBANK", "SBIN"}

    def test_low_peer_count_flag(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        tax = _make_taxonomy()
        tax["sectors"]["Banks"]["min_peer_count"] = 5
        taxonomy_path.write_text(json.dumps(tax))
        artifacts = tmp_path / "artifacts"
        for sym in ["HDFCBANK", "ICICIBANK"]:
            (artifacts / sym).mkdir(parents=True)
            (artifacts / sym / "indianapi_stock.json").write_text(
                json.dumps(_make_indianapi("Regional Banks"))
            )
        mapper = SectorMapper(taxonomy_path, artifacts)
        mapper.map_all()
        assert mapper.is_low_peer_count("Banks") is True

    def test_get_kpis_for_sector(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        mapper = SectorMapper(taxonomy_path, artifacts)
        kpis = mapper.get_sector_kpis("Banks")
        assert len(kpis) == 2
        assert kpis[0]["name"] == "NIM"

    def test_get_composite_weights(self, tmp_path):
        from pipeline.scorecard_v2.sector_mapper import SectorMapper

        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(_make_taxonomy()))
        artifacts = tmp_path / "artifacts"
        mapper = SectorMapper(taxonomy_path, artifacts)
        w = mapper.get_composite_weights("Banks")
        assert w == {"financial": 0.70, "management": 0.30}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_sector_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.scorecard_v2'`

- [ ] **Step 3: Create sector_taxonomy.json with all 24 sectors**

Create `pipeline/config/sector_taxonomy.json` with the full sector taxonomy from the design spec (§3 and §4). Each sector entry must have:
- `display_name`: human-readable name
- `industries`: list of raw indianapi industry strings that map to this sector
- `composite_weights`: `{"financial": float, "management": float}` summing to 1.0
- `min_peer_count`: minimum peers for reliable ranking (default 5)
- `kpis`: list of `{"name", "direction", "weight", "source"}` objects

The `overrides` object maps specific symbols to sectors (e.g., `"RELIANCE": "Oil_Gas"`).
The `common_kpis` list defines metrics computed for ALL sectors regardless.

Use the exact KPI names, weights, and composite weights from the design spec §4.1-§4.21.

Full content is too large to inline — build it from the spec tables. Key constraint: KPI weights within each sector must sum to 1.0.

- [ ] **Step 4: Implement sector_mapper.py**

```python
# pipeline/scorecard_v2/sector_mapper.py
"""Map stocks to normalized sectors using taxonomy config + indianapi industry."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "config" / "sector_taxonomy.json"
_DEFAULT_ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "opus" / "artifacts"


class SectorMapper:
    def __init__(self, taxonomy_path: Path = _DEFAULT_TAXONOMY,
                 artifacts_dir: Path = _DEFAULT_ARTIFACTS):
        self._taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        self._artifacts = artifacts_dir
        self._industry_to_sector: dict[str, str] = {}
        self._sector_stocks: dict[str, list[str]] = {}
        self._stock_map: dict[str, dict[str, Any]] = {}

        for sector_key, sector_def in self._taxonomy.get("sectors", {}).items():
            for industry in sector_def.get("industries", []):
                self._industry_to_sector[industry] = sector_key

    def map_all(self) -> dict[str, dict[str, Any]]:
        overrides = self._taxonomy.get("overrides", {})
        self._stock_map = {}
        self._sector_stocks = {}

        for sym_dir in sorted(self._artifacts.iterdir()):
            if not sym_dir.is_dir() or sym_dir.name in ("transcripts",):
                continue
            symbol = sym_dir.name

            if symbol in overrides:
                sector = overrides[symbol]
            else:
                ia_path = sym_dir / "indianapi_stock.json"
                if ia_path.exists():
                    try:
                        ia = json.loads(ia_path.read_text(encoding="utf-8"))
                        raw_industry = ia.get("industry", "Unknown")
                        sector = self._industry_to_sector.get(raw_industry, "Unmapped")
                    except Exception:
                        sector = "Unmapped"
                else:
                    sector = "Unmapped"

            sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
            self._stock_map[symbol] = {
                "sector": sector,
                "display_name": sector_def.get("display_name", sector),
                "subsector": "",
            }
            self._sector_stocks.setdefault(sector, []).append(symbol)

        return self._stock_map

    def get_sector_peers(self, sector: str) -> list[str]:
        return self._sector_stocks.get(sector, [])

    def is_low_peer_count(self, sector: str) -> bool:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        min_peers = sector_def.get("min_peer_count", 5)
        return len(self._sector_stocks.get(sector, [])) < min_peers

    def get_sector_kpis(self, sector: str) -> list[dict]:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        return sector_def.get("kpis", [])

    def get_composite_weights(self, sector: str) -> dict[str, float]:
        sector_def = self._taxonomy.get("sectors", {}).get(sector, {})
        return sector_def.get("composite_weights", {"financial": 0.60, "management": 0.40})

    def get_all_sectors(self) -> list[str]:
        return list(self._taxonomy.get("sectors", {}).keys())
```

- [ ] **Step 5: Create `__init__.py`**

```python
# pipeline/scorecard_v2/__init__.py
"""Scorecard V2 — Sector-anchored management & financial intelligence."""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_sector_mapper.py -v`
Expected: 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/config/sector_taxonomy.json pipeline/scorecard_v2/__init__.py pipeline/scorecard_v2/sector_mapper.py pipeline/tests/test_sector_mapper.py
git commit -m "feat(scorecard-v2): sector taxonomy config + mapper"
```

---

## Task 2: Metric Extractor

**Files:**
- Create: `pipeline/scorecard_v2/metric_extractor.py`
- Create: `pipeline/tests/test_metric_extractor.py`

- [ ] **Step 1: Write failing tests for metric extraction**

```python
# pipeline/tests/test_metric_extractor.py
"""Tests for metric_extractor — extract raw financial metrics from artifacts."""
from __future__ import annotations
import json
import pytest
from pathlib import Path


def _make_screener_bank():
    """Minimal screener shape for a bank (has Revenue+, Interest, Deposits)."""
    return {
        "about": {"ROCE": "7.51", "ROE": "14.4", "Stock P/E": "16.5", "Book Value": "364"},
        "profit_loss": [
            {"": "Revenue+", "Mar 2023": "121,067", "Mar 2024": "159,516", "Mar 2025": "190,000"},
            {"": "Interest", "Mar 2023": "50,543", "Mar 2024": "74,108", "Mar 2025": "85,000"},
            {"": "Expenses+", "Mar 2023": "87,864", "Mar 2024": "99,560", "Mar 2025": "110,000"},
            {"": "Net Profit+", "Mar 2023": "36,000", "Mar 2024": "46,000", "Mar 2025": "55,000"},
        ],
        "balance_sheet": [
            {"": "Equity Capital", "Mar 2024": "1,400"},
            {"": "Reserves", "Mar 2024": "250,000"},
            {"": "Deposits", "Mar 2024": "2,300,000"},
            {"": "Borrowing", "Mar 2024": "500,000"},
            {"": "Total Assets", "Mar 2024": "2,100,000"},
        ],
        "cash_flow": [
            {"": "Cash from Operating Activity+", "Mar 2024": "80,000"},
            {"": "CFO/OP", "Mar 2024": "174%"},
        ],
        "ratios": [{"": "ROE %", "Mar 2024": "19%", "Mar 2023": "17%", "Mar 2022": "15%"}],
    }


def _make_screener_nonbank():
    """Minimal screener shape for a non-bank (has Sales+, OPM%)."""
    return {
        "about": {"ROCE": "16.6", "ROE": "18.4", "Stock P/E": "59.1"},
        "profit_loss": [
            {"": "Sales+", "Mar 2023": "18,000", "Mar 2024": "20,000", "Mar 2025": "22,000"},
            {"": "Operating Profit", "Mar 2023": "3,000", "Mar 2024": "3,600", "Mar 2025": "4,100"},
            {"": "OPM %", "Mar 2023": "17%", "Mar 2024": "18%", "Mar 2025": "19%"},
            {"": "Net Profit+", "Mar 2023": "2,000", "Mar 2024": "2,500", "Mar 2025": "3,000"},
        ],
        "balance_sheet": [
            {"": "Equity Capital", "Mar 2024": "72"},
            {"": "Reserves", "Mar 2024": "9,000"},
            {"": "Borrowings+", "Mar 2024": "4,000"},
            {"": "Total Assets", "Mar 2024": "25,000"},
        ],
        "cash_flow": [
            {"": "Cash from Operating Activity+", "Mar 2024": "3,200"},
            {"": "CFO/OP", "Mar 2024": "128%"},
        ],
        "ratios": [{"": "ROE %", "Mar 2024": "18%", "Mar 2023": "16%"}],
    }


def _make_indianapi():
    return {
        "keyMetrics": {
            "mgmtEffectiveness": [
                {"key": "returnOnAverageAssets", "displayName": "Return on average assets - most recent fiscal year", "value": "2.17"},
                {"key": "returnOnAverageEquity5YearAverage", "displayName": "Return on average equity - 5 year average", "value": "16.80"},
            ],
            "margins": [
                {"key": "operatingMarginTTM", "displayName": "Operating margin - trailing 12 month", "value": "34.72"},
            ],
            "growth": [
                {"key": "revenueGrowthRate5Year", "displayName": "Revenue growth rate, 5 year", "value": "17.04"},
            ],
        }
    }


class TestMetricExtractor:
    def test_extract_common_metrics_nonbank(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "APOLLOHOSP").mkdir(parents=True)
        (artifacts / "APOLLOHOSP" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("APOLLOHOSP")
        assert m["ROE"] == pytest.approx(18.4)
        assert m["ROCE"] == pytest.approx(16.6)
        assert m["EBITDA_Margin"] == pytest.approx(19.0, abs=1)
        assert m["is_bank"] is False

    def test_extract_bank_nim_proxy(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "ICICIBANK").mkdir(parents=True)
        (artifacts / "ICICIBANK" / "screener_financials.json").write_text(
            json.dumps(_make_screener_bank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("ICICIBANK")
        assert m["is_bank"] is True
        assert "NIM_proxy" in m
        assert m["NIM_proxy"] > 0

    def test_extract_revenue_growth(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "TCS").mkdir(parents=True)
        (artifacts / "TCS" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("TCS")
        assert "Revenue_Growth_3Y" in m
        assert m["Revenue_Growth_3Y"] > 0

    def test_extract_cfo_pat(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "X").mkdir(parents=True)
        (artifacts / "X" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("X")
        assert "CFO_PAT" in m
        assert m["CFO_PAT"] > 0

    def test_extract_debt_to_equity(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "X").mkdir(parents=True)
        (artifacts / "X" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("X")
        assert "Debt_to_Equity" in m
        assert m["Debt_to_Equity"] == pytest.approx(4000 / 9072, abs=0.1)

    def test_indianapi_supplements_screener(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "ICICIBANK").mkdir(parents=True)
        (artifacts / "ICICIBANK" / "screener_financials.json").write_text(
            json.dumps(_make_screener_bank())
        )
        (artifacts / "ICICIBANK" / "indianapi_stock.json").write_text(
            json.dumps(_make_indianapi())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("ICICIBANK")
        assert m.get("ROA_indianapi") == pytest.approx(2.17)

    def test_missing_screener_returns_partial(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "MISSING").mkdir(parents=True)
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("MISSING")
        assert m["coverage_pct"] == 0

    def test_roe_history_for_stability(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "X").mkdir(parents=True)
        (artifacts / "X" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("X")
        assert "ROE_history" in m
        assert isinstance(m["ROE_history"], list)
        assert len(m["ROE_history"]) >= 2

    def test_margin_history_for_volatility(self, tmp_path):
        from pipeline.scorecard_v2.metric_extractor import MetricExtractor

        artifacts = tmp_path / "artifacts"
        (artifacts / "X").mkdir(parents=True)
        (artifacts / "X" / "screener_financials.json").write_text(
            json.dumps(_make_screener_nonbank())
        )
        extractor = MetricExtractor(artifacts)
        m = extractor.extract("X")
        assert "Margin_history" in m
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_metric_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement metric_extractor.py**

Create `pipeline/scorecard_v2/metric_extractor.py`. The extractor must:

1. Read `screener_financials.json` — detect bank vs non-bank by checking if P&L has `Revenue+` (bank) or `Sales+` (non-bank).
2. Parse screener numeric strings: strip commas, handle `%` suffix, handle missing/empty values.
3. Extract common metrics from `about` section: ROE, ROCE, P/E, Book Value.
4. Compute derived metrics from P&L/BS/CF:
   - `Revenue_Growth_3Y`: CAGR from 3 years of revenue/sales data.
   - `EBITDA_Margin`: OPM% for non-banks; Financing Margin% for banks.
   - `Debt_to_Equity`: (Borrowings or Borrowing) / (Equity Capital + Reserves).
   - `CFO_PAT`: Cash from Operating Activity / Net Profit (latest year).
   - `NIM_proxy` (banks only): (Revenue - Interest) / Total Assets.
5. Extract `ROE_history` and `Margin_history` as lists of floats from the ratios and P&L sections.
6. Optionally read `indianapi_stock.json` keyMetrics and store as `ROA_indianapi`, `Revenue_Growth_5Y_indianapi`, etc.
7. Compute `coverage_pct`: count of non-None metrics / total expected metrics × 100.

Key helper function: `_parse_screener_num(val: str) -> float | None` — strips commas, handles `%`, returns None on failure.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_metric_extractor.py -v`
Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/scorecard_v2/metric_extractor.py pipeline/tests/test_metric_extractor.py
git commit -m "feat(scorecard-v2): metric extractor — screener + indianapi"
```

---

## Task 3: Financial Scorer

**Files:**
- Create: `pipeline/scorecard_v2/financial_scorer.py`
- Create: `pipeline/tests/test_financial_scorer.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_financial_scorer.py
"""Tests for financial_scorer — percentile scoring within sector."""
from __future__ import annotations
import pytest


def _make_metrics(roe, roce, margin, de, cfo_pat):
    return {
        "ROE": roe, "ROCE": roce, "EBITDA_Margin": margin,
        "Debt_to_Equity": de, "CFO_PAT": cfo_pat, "coverage_pct": 100,
    }


class TestFinancialScorer:
    def test_percentile_higher_is_better(self):
        from pipeline.scorecard_v2.financial_scorer import _percentile_rank

        values = [10, 20, 30, 40, 50]
        assert _percentile_rank(50, values) == pytest.approx(100, abs=5)
        assert _percentile_rank(10, values) == pytest.approx(20, abs=5)
        assert _percentile_rank(30, values) == pytest.approx(60, abs=5)

    def test_percentile_lower_is_better(self):
        from pipeline.scorecard_v2.financial_scorer import _percentile_rank

        values = [10, 20, 30, 40, 50]
        rank = _percentile_rank(10, values)
        assert rank == pytest.approx(20, abs=5)

    def test_score_sector_returns_0_100(self):
        from pipeline.scorecard_v2.financial_scorer import score_sector

        sector_metrics = {
            "A": _make_metrics(20, 25, 30, 0.5, 1.2),
            "B": _make_metrics(15, 20, 25, 0.8, 1.0),
            "C": _make_metrics(10, 15, 20, 1.5, 0.7),
            "D": _make_metrics(8, 10, 15, 2.0, 0.5),
            "E": _make_metrics(5, 8, 10, 3.0, 0.3),
        }
        kpis = [
            {"name": "ROE", "direction": "higher", "weight": 0.30},
            {"name": "EBITDA_Margin", "direction": "higher", "weight": 0.30},
            {"name": "Debt_to_Equity", "direction": "lower", "weight": 0.20},
            {"name": "CFO_PAT", "direction": "higher", "weight": 0.20},
        ]
        scores = score_sector(sector_metrics, kpis)
        assert all(0 <= s <= 100 for s in scores.values())
        assert scores["A"] > scores["E"]

    def test_missing_metric_renormalizes_weights(self):
        from pipeline.scorecard_v2.financial_scorer import score_sector

        sector_metrics = {
            "A": {"ROE": 20, "EBITDA_Margin": 30, "coverage_pct": 50},
            "B": {"ROE": 10, "EBITDA_Margin": 20, "coverage_pct": 50},
        }
        kpis = [
            {"name": "ROE", "direction": "higher", "weight": 0.50},
            {"name": "EBITDA_Margin", "direction": "higher", "weight": 0.30},
            {"name": "Debt_to_Equity", "direction": "lower", "weight": 0.20},
        ]
        scores = score_sector(sector_metrics, kpis)
        assert scores["A"] > scores["B"]
        assert all(0 <= s <= 100 for s in scores.values())

    def test_winsorize_outliers(self):
        from pipeline.scorecard_v2.financial_scorer import _winsorize

        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]
        result = _winsorize(values, lower=0.1, upper=0.9)
        assert max(result) < 100
        assert min(result) >= 1

    def test_single_stock_sector_gets_50(self):
        from pipeline.scorecard_v2.financial_scorer import score_sector

        sector_metrics = {"ONLY": _make_metrics(15, 20, 25, 1.0, 0.8)}
        kpis = [{"name": "ROE", "direction": "higher", "weight": 1.0}]
        scores = score_sector(sector_metrics, kpis)
        assert scores["ONLY"] == pytest.approx(50, abs=10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_financial_scorer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement financial_scorer.py**

Create `pipeline/scorecard_v2/financial_scorer.py` with:
- `_winsorize(values, lower=0.05, upper=0.95) -> list[float]` — clip extremes.
- `_percentile_rank(value, all_values) -> float` — returns 0-100 percentile.
- `score_sector(sector_metrics: dict[str, dict], kpis: list[dict]) -> dict[str, float]` — for each stock in the sector, compute weighted percentile score across all KPIs. Missing KPIs are skipped and weights renormalized. Returns `{symbol: financial_score}` where scores are 0-100.

Direction handling: for `"direction": "lower"`, invert the percentile (100 - percentile).
Single-stock sectors: assign 50 as the default score.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_financial_scorer.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/scorecard_v2/financial_scorer.py pipeline/tests/test_financial_scorer.py
git commit -m "feat(scorecard-v2): financial scorer — percentile ranking within sector"
```

---

## Task 4: Management Quant Score

**Files:**
- Create: `pipeline/scorecard_v2/management_quant.py`
- Create: `pipeline/tests/test_management_quant.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_management_quant.py
"""Tests for management_quant — quant-only management scoring."""
from __future__ import annotations
import pytest


class TestManagementQuant:
    def test_pledge_scoring(self):
        from pipeline.scorecard_v2.management_quant import _pledge_score

        assert _pledge_score(0) == 5
        assert _pledge_score(5) == 4
        assert _pledge_score(20) == 3
        assert _pledge_score(40) == 2
        assert _pledge_score(60) == 1

    def test_roe_stability_higher_is_better(self):
        from pipeline.scorecard_v2.management_quant import _roe_stability_score

        stable = [15.0, 16.0, 14.5, 15.5, 16.0]
        volatile = [5.0, 25.0, -2.0, 30.0, 8.0]
        assert _roe_stability_score(stable) > _roe_stability_score(volatile)

    def test_margin_volatility_lower_is_better(self):
        from pipeline.scorecard_v2.management_quant import _margin_stability_score

        stable = [18.0, 19.0, 17.5, 18.5, 19.0]
        volatile = [10.0, 25.0, 5.0, 30.0, 12.0]
        assert _margin_stability_score(stable) > _margin_stability_score(volatile)

    def test_cfo_pat_consistency(self):
        from pipeline.scorecard_v2.management_quant import _cfo_pat_consistency_score

        good = [1.2, 1.1, 0.9, 1.0, 1.3]
        bad = [0.1, -0.5, 0.2, 0.05, -0.3]
        assert _cfo_pat_consistency_score(good) > _cfo_pat_consistency_score(bad)

    def test_hard_cap_pledge(self):
        from pipeline.scorecard_v2.management_quant import compute_management_quant

        metrics = {
            "ROE_history": [15, 16, 14, 15, 16],
            "Margin_history": [18, 19, 17, 18, 19],
            "CFO_PAT": 1.0,
            "promoter_pledge_pct": 40,
            "promoter_holding_pct": 50,
        }
        score = compute_management_quant(metrics)
        assert score <= 40

    def test_hard_cap_cfo_pat(self):
        from pipeline.scorecard_v2.management_quant import compute_management_quant

        metrics = {
            "ROE_history": [15, 16, 14, 15, 16],
            "Margin_history": [18, 19, 17, 18, 19],
            "CFO_PAT": 0.2,
            "promoter_pledge_pct": 0,
            "promoter_holding_pct": 50,
        }
        score = compute_management_quant(metrics)
        assert score <= 50

    def test_full_score_range(self):
        from pipeline.scorecard_v2.management_quant import compute_management_quant

        good = {
            "ROE_history": [18, 19, 20, 21, 22],
            "Margin_history": [25, 26, 25, 27, 26],
            "CFO_PAT": 1.3,
            "promoter_pledge_pct": 0,
            "promoter_holding_pct": 70,
        }
        bad = {
            "ROE_history": [5, -2, 8, -5, 3],
            "Margin_history": [10, 25, 5, 30, 8],
            "CFO_PAT": 0.1,
            "promoter_pledge_pct": 60,
            "promoter_holding_pct": 20,
        }
        assert compute_management_quant(good) > compute_management_quant(bad)
        assert 0 <= compute_management_quant(good) <= 100
        assert 0 <= compute_management_quant(bad) <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_management_quant.py -v`
Expected: FAIL

- [ ] **Step 3: Implement management_quant.py**

Create `pipeline/scorecard_v2/management_quant.py` with:
- `_pledge_score(pledge_pct: float) -> int` — 0%=5, <10%=4, 10-30%=3, 30-50%=2, >50%=1
- `_roe_stability_score(roe_history: list[float]) -> float` — higher mean ROE + lower std = better. Scale 0-20.
- `_margin_stability_score(margin_history: list[float]) -> float` — lower std of margins = better. Scale 0-20.
- `_cfo_pat_consistency_score(cfo_pat_values: list[float] | float) -> float` — higher average + fewer negative years. Scale 0-20.
- `_skin_in_game_score(holding_pct: float) -> float` — higher promoter holding = better. Scale 0-10.
- `compute_management_quant(metrics: dict) -> float` — weighted sum of all sub-scores, normalized to 0-100. Apply hard caps: if pledge > 30% cap at 40; if CFO/PAT < 0.3 cap at 50.

Weights per design spec §5.1: Capital Allocation 30%, Governance 20%, Execution 25%, Accounting 15%, Skin 10%.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_management_quant.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/scorecard_v2/management_quant.py pipeline/tests/test_management_quant.py
git commit -m "feat(scorecard-v2): management quant score — pledge, stability, CFO/PAT"
```

---

## Task 5: Composite Ranker + Remark Generator

**Files:**
- Create: `pipeline/scorecard_v2/composite_ranker.py`
- Create: `pipeline/tests/test_composite_ranker.py`

- [ ] **Step 1: Write failing tests**

```python
# pipeline/tests/test_composite_ranker.py
"""Tests for composite_ranker — blend, rank, grade, remark."""
from __future__ import annotations
import pytest


def _make_stock(fin, mgmt, sector="Banks"):
    return {"financial_score": fin, "management_score": mgmt, "sector": sector}


class TestCompositeRanker:
    def test_composite_weighted_blend(self):
        from pipeline.scorecard_v2.composite_ranker import compute_composite

        result = compute_composite(80, 60, {"financial": 0.70, "management": 0.30})
        assert result == pytest.approx(74.0)

    def test_forced_ranking_assigns_grades(self):
        from pipeline.scorecard_v2.composite_ranker import forced_rank_sector

        stocks = {f"S{i}": _make_stock(90 - i * 5, 80 - i * 4) for i in range(20)}
        ranked = forced_rank_sector(
            stocks, {"financial": 0.60, "management": 0.40}
        )
        grades = [r["sector_grade"] for r in ranked.values()]
        assert "A" in grades
        assert "F" in grades
        assert ranked["S0"]["sector_rank"] == 1
        assert ranked["S19"]["sector_rank"] == 20

    def test_grade_distribution(self):
        from pipeline.scorecard_v2.composite_ranker import forced_rank_sector

        stocks = {f"S{i}": _make_stock(100 - i * 4, 80 - i * 3) for i in range(20)}
        ranked = forced_rank_sector(
            stocks, {"financial": 0.60, "management": 0.40}
        )
        grades = [r["sector_grade"] for r in ranked.values()]
        a_count = grades.count("A")
        f_count = grades.count("F")
        assert a_count == 3   # top 15% of 20 = 3
        assert f_count == 3   # bottom 15% of 20 = 3

    def test_remark_generation(self):
        from pipeline.scorecard_v2.composite_ranker import generate_remark

        stock = {
            "symbol": "APOLLOHOSP",
            "sector": "Hospitals_Diagnostics",
            "display_name": "Hospitals / Diagnostics",
            "financial_score": 45,
            "management_score": 18,
            "composite_score": 34,
            "sector_rank": 3,
            "sector_total": 3,
            "sector_leader": "MAXHEALTH",
            "sector_leader_composite": 52,
            "confidence": "medium",
            "biggest_strength": "ARPOB growth",
            "biggest_red_flag": "Bed expansion behind schedule",
        }
        remark = generate_remark(stock)
        assert "APOLLOHOSP" in remark
        assert "3/3" in remark
        assert "MAXHEALTH" in remark
        assert "medium" in remark.lower()

    def test_sector_leader_and_gap(self):
        from pipeline.scorecard_v2.composite_ranker import forced_rank_sector

        stocks = {
            "BEST": _make_stock(90, 80),
            "WORST": _make_stock(20, 10),
        }
        ranked = forced_rank_sector(
            stocks, {"financial": 0.60, "management": 0.40}
        )
        assert ranked["WORST"]["sector_leader"] == "BEST"
        assert ranked["WORST"]["sector_gap_to_leader"] > 0

    def test_confidence_from_coverage(self):
        from pipeline.scorecard_v2.composite_ranker import compute_confidence

        assert compute_confidence(90, 3) == "high"
        assert compute_confidence(60, 1) == "medium"
        assert compute_confidence(30, 1) == "low"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_composite_ranker.py -v`
Expected: FAIL

- [ ] **Step 3: Implement composite_ranker.py**

Create `pipeline/scorecard_v2/composite_ranker.py` with:

- `compute_composite(fin_score, mgmt_score, weights) -> float`
- `compute_confidence(coverage_pct, data_sources) -> str` — "high"/"medium"/"low" per spec §6.4
- `forced_rank_sector(stocks: dict, weights: dict) -> dict` — compute composites, sort, assign sector_rank, sector_percentile, sector_grade (A top 15%, B next 20%, C middle 30%, D next 20%, F bottom 15%). Also compute sector_leader, sector_gap_to_leader, sector_gap_to_median, sector_total.
- `generate_remark(stock: dict) -> str` — one-liner: "{SYMBOL} ranks {rank}/{total} in {sector}. Financial {fin}/100. Management {mgmt}/100 — {red_flag}. Leader: {leader} ({leader_composite}). Confidence: {confidence}."

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_composite_ranker.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/scorecard_v2/composite_ranker.py pipeline/tests/test_composite_ranker.py
git commit -m "feat(scorecard-v2): composite ranker — blend, forced rank, grades, remarks"
```

---

## Task 6: Orchestrator (run_scorecard_v2)

**Files:**
- Modify: `pipeline/scorecard_v2/__init__.py`
- Create: `pipeline/tests/test_scorecard_v2_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# pipeline/tests/test_scorecard_v2_integration.py
"""Integration test — full scorecard V2 pipeline without LLM."""
from __future__ import annotations
import json
import pytest
from pathlib import Path


def _write_artifact(base: Path, symbol: str, industry: str, is_bank: bool = False):
    d = base / symbol
    d.mkdir(parents=True, exist_ok=True)
    (d / "indianapi_stock.json").write_text(json.dumps({
        "companyName": symbol, "industry": industry,
        "keyMetrics": {"mgmtEffectiveness": [
            {"key": "returnOnAverageAssets", "value": "1.5"},
        ]},
    }))
    if is_bank:
        screener = {
            "about": {"ROCE": "7.5", "ROE": "14.0"},
            "profit_loss": [
                {"": "Revenue+", "Mar 2023": "100,000", "Mar 2024": "120,000", "Mar 2025": "140,000"},
                {"": "Interest", "Mar 2023": "40,000", "Mar 2024": "50,000", "Mar 2025": "55,000"},
                {"": "Expenses+", "Mar 2023": "50,000", "Mar 2024": "55,000", "Mar 2025": "60,000"},
                {"": "Net Profit+", "Mar 2023": "15,000", "Mar 2024": "20,000", "Mar 2025": "25,000"},
            ],
            "balance_sheet": [
                {"": "Equity Capital", "Mar 2024": "1,000"}, {"": "Reserves", "Mar 2024": "200,000"},
                {"": "Deposits", "Mar 2024": "1,500,000"}, {"": "Borrowing", "Mar 2024": "300,000"},
                {"": "Total Assets", "Mar 2024": "2,000,000"},
            ],
            "cash_flow": [{"": "Cash from Operating Activity+", "Mar 2024": "30,000"}, {"": "CFO/OP", "Mar 2024": "150%"}],
            "ratios": [{"": "ROE %", "Mar 2023": "12%", "Mar 2024": "14%", "Mar 2022": "10%"}],
        }
    else:
        screener = {
            "about": {"ROCE": "18.0", "ROE": "20.0"},
            "profit_loss": [
                {"": "Sales+", "Mar 2023": "50,000", "Mar 2024": "55,000", "Mar 2025": "60,000"},
                {"": "Operating Profit", "Mar 2023": "10,000", "Mar 2024": "11,000", "Mar 2025": "12,000"},
                {"": "OPM %", "Mar 2023": "20%", "Mar 2024": "20%", "Mar 2025": "20%"},
                {"": "Net Profit+", "Mar 2023": "7,000", "Mar 2024": "8,000", "Mar 2025": "9,000"},
            ],
            "balance_sheet": [
                {"": "Equity Capital", "Mar 2024": "500"}, {"": "Reserves", "Mar 2024": "30,000"},
                {"": "Borrowings+", "Mar 2024": "10,000"}, {"": "Total Assets", "Mar 2024": "60,000"},
            ],
            "cash_flow": [{"": "Cash from Operating Activity+", "Mar 2024": "10,000"}, {"": "CFO/OP", "Mar 2024": "125%"}],
            "ratios": [{"": "ROE %", "Mar 2023": "18%", "Mar 2024": "20%", "Mar 2022": "16%"}],
        }
    (d / "screener_financials.json").write_text(json.dumps(screener))


class TestScorecardV2Integration:
    def test_full_pipeline_without_llm(self, tmp_path):
        from pipeline.scorecard_v2 import run_scorecard_v2

        taxonomy = {
            "version": "2.0",
            "sectors": {
                "Banks": {
                    "display_name": "Banks (Private & PSU)",
                    "industries": ["Regional Banks"],
                    "composite_weights": {"financial": 0.70, "management": 0.30},
                    "min_peer_count": 3,
                    "kpis": [
                        {"name": "ROE", "direction": "higher", "weight": 0.40},
                        {"name": "NIM_proxy", "direction": "higher", "weight": 0.30},
                        {"name": "Debt_to_Equity", "direction": "lower", "weight": 0.30},
                    ],
                },
            },
            "overrides": {},
            "common_kpis": ["ROE", "ROCE"],
        }
        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(taxonomy))
        artifacts = tmp_path / "artifacts"

        for sym in ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"]:
            _write_artifact(artifacts, sym, "Regional Banks", is_bank=True)

        output_path = tmp_path / "trust_scores_v2.json"
        result = run_scorecard_v2(
            taxonomy_path=taxonomy_path,
            artifacts_dir=artifacts,
            output_path=output_path,
            skip_llm=True,
        )

        assert len(result["stocks"]) == 5
        for s in result["stocks"]:
            assert "financial_score" in s
            assert "management_score" in s
            assert "composite_score" in s
            assert "sector_grade" in s
            assert "sector_rank" in s
            assert "grade_reason" in s
            assert s["sector"] == "Banks"
            assert 0 <= s["composite_score"] <= 100

        assert output_path.exists()
        saved = json.loads(output_path.read_text())
        assert len(saved["stocks"]) == 5

    def test_multiple_sectors(self, tmp_path):
        from pipeline.scorecard_v2 import run_scorecard_v2

        taxonomy = {
            "version": "2.0",
            "sectors": {
                "Banks": {
                    "display_name": "Banks",
                    "industries": ["Regional Banks"],
                    "composite_weights": {"financial": 0.70, "management": 0.30},
                    "kpis": [{"name": "ROE", "direction": "higher", "weight": 1.0}],
                },
                "IT_Services": {
                    "display_name": "IT Services",
                    "industries": ["Software & Programming"],
                    "composite_weights": {"financial": 0.60, "management": 0.40},
                    "kpis": [{"name": "EBITDA_Margin", "direction": "higher", "weight": 1.0}],
                },
            },
            "overrides": {},
            "common_kpis": ["ROE"],
        }
        taxonomy_path = tmp_path / "taxonomy.json"
        taxonomy_path.write_text(json.dumps(taxonomy))
        artifacts = tmp_path / "artifacts"

        _write_artifact(artifacts, "HDFCBANK", "Regional Banks", is_bank=True)
        _write_artifact(artifacts, "TCS", "Software & Programming", is_bank=False)

        result = run_scorecard_v2(
            taxonomy_path=taxonomy_path, artifacts_dir=artifacts,
            output_path=tmp_path / "out.json", skip_llm=True,
        )
        sectors = {s["symbol"]: s["sector"] for s in result["stocks"]}
        assert sectors["HDFCBANK"] == "Banks"
        assert sectors["TCS"] == "IT_Services"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_scorecard_v2_integration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement orchestrator in `__init__.py`**

Update `pipeline/scorecard_v2/__init__.py` to contain `run_scorecard_v2()`:

```python
# pipeline/scorecard_v2/__init__.py
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
            llm = mgmt_llm_scores.get(s, quant)
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
        all_scores[s]["confidence"] = compute_confidence(
            m.get("coverage_pct", 0),
            sum(1 for k in ["screener", "indianapi"] if m.get(f"has_{k}", False)),
        )
        all_scores[s]["grade_reason"] = generate_remark({
            "symbol": s, **all_scores[s],
            "biggest_strength": m.get("biggest_strength", ""),
            "biggest_red_flag": m.get("biggest_red_flag", ""),
        })
        all_scores[s]["low_peer_count"] = mapper.is_low_peer_count(all_scores[s].get("sector", ""))

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_scorecard_v2_integration.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Run all scorecard V2 tests together**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_sector_mapper.py pipeline/tests/test_metric_extractor.py pipeline/tests/test_financial_scorer.py pipeline/tests/test_management_quant.py pipeline/tests/test_composite_ranker.py pipeline/tests/test_scorecard_v2_integration.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/scorecard_v2/__init__.py pipeline/tests/test_scorecard_v2_integration.py
git commit -m "feat(scorecard-v2): orchestrator — full pipeline without LLM"
```

---

## Task 7: Management LLM Score (Sonnet Re-score)

**Files:**
- Create: `pipeline/scorecard_v2/management_llm.py`
- Modify: `pipeline/scorecard_v2/__init__.py` (wire LLM into pipeline)

- [ ] **Step 1: Write management_llm.py**

Create `pipeline/scorecard_v2/management_llm.py` with:

```python
# pipeline/scorecard_v2/management_llm.py
"""Sonnet re-score — sector-specific management evaluation."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "opus" / "artifacts"


def _build_prompt(symbol: str, sector: str, kpis: list[dict],
                  ar_text: str, concall_text: str, screener_about: dict) -> str:
    kpi_list = "\n".join(
        f"  - {k['name']} ({k['direction']} is better, weight {k['weight']:.0%})"
        for k in kpis
    )
    return f"""You are scoring management quality for {symbol} in the {sector} sector.

SECTOR-SPECIFIC KPIs to score against:
{kpi_list}

SCREENER SNAPSHOT:
ROE: {screener_about.get('ROE', 'N/A')}, ROCE: {screener_about.get('ROCE', 'N/A')}, P/E: {screener_about.get('Stock P/E', 'N/A')}

ANNUAL REPORT EXCERPTS:
{ar_text[:4000]}

CONCALL EXCERPTS:
{concall_text[:4000]}

Score this company on these 4 dimensions (each 0-100):

1. EXECUTION DELIVERY (40% weight): For EACH sector KPI above, did management deliver on guidance? Score each as EXCEEDED / DELIVERED / PARTIALLY / MISSED / DROPPED with a one-line detail.

2. STRATEGIC COHERENCE (20%): Does guidance align with sector dynamics? Are investments appropriate for this industry?

3. CAPITAL ALLOCATION (20%): Is capex productive? Acquisitions value-accretive? Capital returns appropriate?

4. DISCLOSURE QUALITY (20%): How clear, frequent, and honest is communication? Do they address misses?

Return ONLY valid JSON:
{{
  "execution_delivery": {{
    "score": <0-100>,
    "kpi_scores": [
      {{"kpi": "<name>", "status": "EXCEEDED|DELIVERED|PARTIALLY|MISSED|DROPPED", "detail": "<one line>"}}
    ]
  }},
  "strategic_coherence": {{"score": <0-100>, "reason": "<one line>"}},
  "capital_allocation": {{"score": <0-100>, "reason": "<one line>"}},
  "disclosure_quality": {{"score": <0-100>, "reason": "<one line>"}},
  "management_llm_score": <weighted 0-100>,
  "biggest_strength": "<one line>",
  "biggest_red_flag": "<one line>",
  "what_street_misses": "<one line>"
}}"""


def _load_text(artifacts_dir: Path, symbol: str, filename: str, max_chars: int = 5000) -> str:
    for name in [filename]:
        path = artifacts_dir / symbol / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")[:max_chars]
            except Exception:
                pass
    return ""


def score_stock_llm(
    symbol: str,
    sector: str,
    kpis: list[dict],
    artifacts_dir: Path = _ARTIFACTS,
    client=None,
    model: str = "claude-sonnet-4-6-20250514",
) -> dict[str, Any]:
    ar_text = ""
    for yr in ["2024-2025", "2023-2024", "2022-2023"]:
        ar_text += _load_text(artifacts_dir, symbol, f"ar_text_{yr}.txt", 3000) + "\n"
    concall_text = _load_text(artifacts_dir, symbol, "concall_text.txt", 4000)

    screener_path = artifacts_dir / symbol / "screener_financials.json"
    screener_about = {}
    if screener_path.exists():
        try:
            sf = json.loads(screener_path.read_text(encoding="utf-8"))
            screener_about = sf.get("about", {})
        except Exception:
            pass

    prompt = _build_prompt(symbol, sector, kpis, ar_text, concall_text, screener_about)

    if client is None:
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception as exc:
            log.error("Cannot create Anthropic client: %s", exc)
            return {"management_llm_score": 50, "error": str(exc)}

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as exc:
        log.error("LLM scoring failed for %s: %s", symbol, exc)
        return {"management_llm_score": 50, "error": str(exc)}


def score_sector_llm(
    sector: str,
    symbols: list[str],
    kpis: list[dict],
    artifacts_dir: Path = _ARTIFACTS,
    client=None,
    model: str = "claude-sonnet-4-6-20250514",
    delay: float = 1.0,
) -> dict[str, dict]:
    results = {}
    for i, symbol in enumerate(symbols):
        log.info("LLM scoring %s (%d/%d in %s)", symbol, i + 1, len(symbols), sector)
        results[symbol] = score_stock_llm(symbol, sector, kpis, artifacts_dir, client, model)
        if delay and i < len(symbols) - 1:
            time.sleep(delay)
    return results
```

- [ ] **Step 2: Wire LLM into orchestrator**

In `pipeline/scorecard_v2/__init__.py`, replace the `pass  # Task 7 adds LLM scoring here` comment:

```python
        # Management LLM scores
        mgmt_llm_scores = {}
        if not skip_llm:
            from .management_llm import score_sector_llm
            llm_results = score_sector_llm(sector, peers, kpis, artifacts_dir)
            for s, r in llm_results.items():
                mgmt_llm_scores[s] = r.get("management_llm_score", 50)
                # Store LLM fields for remark generation
                all_metrics.setdefault(s, {}).update({
                    "biggest_strength": r.get("biggest_strength", ""),
                    "biggest_red_flag": r.get("biggest_red_flag", ""),
                    "what_street_misses": r.get("what_street_misses", ""),
                    "llm_breakdown": r,
                })
```

- [ ] **Step 3: Test with a dry-run on 1 stock (manual)**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "
from pipeline.scorecard_v2.management_llm import _build_prompt, _load_text
from pathlib import Path
arts = Path('opus/artifacts')
prompt = _build_prompt('HDFCBANK', 'Banks', [
    {'name': 'NIM', 'direction': 'higher', 'weight': 0.20},
    {'name': 'ROA', 'direction': 'higher', 'weight': 0.15},
], _load_text(arts, 'HDFCBANK', 'ar_text_2024-2025.txt', 3000),
   _load_text(arts, 'HDFCBANK', 'concall_text.txt', 3000),
   {'ROE': '14.4', 'ROCE': '7.51'})
print(f'Prompt length: {len(prompt)} chars')
print(prompt[:500])
"`
Expected: Prompt prints successfully with actual AR text embedded.

- [ ] **Step 4: Commit**

```bash
git add pipeline/scorecard_v2/management_llm.py pipeline/scorecard_v2/__init__.py
git commit -m "feat(scorecard-v2): Sonnet LLM re-score — sector-specific prompts"
```

---

## Task 8: Terminal API — Serve V2 Scores

**Files:**
- Modify: `pipeline/terminal/api/trust_scores.py`

- [ ] **Step 1: Update trust_scores API to serve V2**

Replace `pipeline/terminal/api/trust_scores.py`:

```python
"""GET /api/trust-scores — Scorecard V2 with sector context."""
import json
from pathlib import Path
from fastapi import APIRouter, Query

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent
_V2_FILE = _HERE.parent.parent / "data" / "trust_scores_v2.json"
_V1_FILE = _HERE.parent.parent / "data" / "trust_scores.json"


def _read_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@router.get("/trust-scores")
def trust_scores(sector: str = Query(None), grade: str = Query(None)):
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    stocks = raw.get("stocks", [])

    if sector:
        stocks = [s for s in stocks if s.get("sector", "").lower() == sector.lower()]
    if grade:
        grades = set(g.strip().upper() for g in grade.split(","))
        stocks = [s for s in stocks if s.get("sector_grade", s.get("trust_grade", "?")).upper() in grades]

    return {
        "stocks": stocks,
        "total": len(stocks),
        "updated_at": raw.get("updated_at"),
        "version": raw.get("version", "1.0"),
    }


@router.get("/trust-scores/sectors")
def trust_score_sectors():
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    stocks = raw.get("stocks", [])
    sectors = {}
    for s in stocks:
        sec = s.get("sector", "Unknown")
        if sec not in sectors:
            sectors[sec] = {"name": s.get("display_name", sec), "count": 0}
        sectors[sec]["count"] += 1
    return {"sectors": sectors}


@router.get("/trust-scores/{ticker}")
def trust_score_detail(ticker: str):
    ticker = ticker.upper()
    raw = _read_json(_V2_FILE) if _V2_FILE.exists() else _read_json(_V1_FILE)
    for s in raw.get("stocks", []):
        if (s.get("symbol") or "").upper() == ticker:
            return s
    return {"symbol": ticker, "sector_grade": "?", "composite_score": None, "grade_reason": "Not scored"}
```

- [ ] **Step 2: Test endpoint manually**

Run terminal: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python -m uvicorn app:app --port 8501 --reload`
Test: `curl http://localhost:8501/api/trust-scores?sector=Banks`
Expected: returns bank stocks with V2 fields (or V1 fallback if V2 not yet generated)

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/api/trust_scores.py
git commit -m "feat(scorecard-v2): terminal API — V2 scores with sector filter"
```

---

## Task 9: Terminal UI — Intelligence Tab V2

**Files:**
- Modify: `pipeline/terminal/static/js/pages/intelligence.js` — rewrite `renderTrustScores()`

- [ ] **Step 1: Rewrite renderTrustScores with V2 table**

Replace the `renderTrustScores` function in `pipeline/terminal/static/js/pages/intelligence.js`. The new version must:

1. **Table columns:** Ticker | Sector | Grade (badge) | Composite (heatmap) | Fin Score (heatmap) | Mgmt Score (heatmap) | Rank | Remark
2. **Sector dropdown filter** above the table — populated from `/api/trust-scores/sectors` endpoint
3. **Heatmap cell backgrounds:** score 80-100 = `rgba(34,197,94,0.25)`, 60-79 = `rgba(34,197,94,0.12)`, 40-59 = `rgba(245,158,11,0.15)`, 20-39 = `rgba(249,115,22,0.15)`, 0-19 = `rgba(239,68,68,0.15)`
4. **Expandable row on click:** show a detail card below the row with:
   - Sector context line: "Rank X/Y in {sector}. Leader: {leader} ({score})."
   - Financial score bar + Management score bar (visual)
   - Grade reason (full text)
   - Biggest strength + Biggest red flag
5. **Sort by any column** — click header to sort
6. **Existing search** — keep ticker search working
7. **Grade badge colors:** use existing `GRADE_COLORS` map but use `sector_grade` field (falling back to `trust_grade` for V1 compatibility)

The V2 UI must gracefully handle V1 data — if `sector_grade` is missing, fall back to `trust_grade`. If `composite_score` is missing, fall back to `trust_score`.

Key implementation notes:
- Use `_esc()` helper for XSS safety on all user-facing strings.
- Remark column: truncate to 80 chars with `...`, full text on hover via `title` attribute.
- Score columns: show numeric value with heatmap background.
- Rank column: show as "3/19" format.

- [ ] **Step 2: Test in browser**

Start terminal server and navigate to Intelligence tab. Verify:
- Table renders with all columns
- Sector dropdown filters correctly
- Clicking a row expands to show detail card
- Heatmap colors appear on score cells
- Search still works
- Grade badges show correct colors

- [ ] **Step 3: Commit**

```bash
git add pipeline/terminal/static/js/pages/intelligence.js
git commit -m "feat(scorecard-v2): terminal UI — heatmap table, sector filter, expandable rows"
```

---

## Task 10: Run Full Pipeline on Real Data

**Files:**
- No new files — execute the pipeline

- [ ] **Step 1: Run scorecard V2 without LLM on real data**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "
from pipeline.scorecard_v2 import run_scorecard_v2
result = run_scorecard_v2(skip_llm=True)
print(f'Scored {result[\"total_scored\"]} stocks')
# Sanity check
for s in result['stocks'][:10]:
    print(f'{s[\"symbol\"]:15s} {s.get(\"sector\",\"?\"):20s} {s.get(\"sector_grade\",\"?\"):>3s} fin={s.get(\"financial_score\",0):5.1f} mgmt={s.get(\"management_score\",0):5.1f} comp={s.get(\"composite_score\",0):5.1f}')
"`

Expected: 210+ stocks scored, no crashes. HDFCBANK/TCS should not be F.

- [ ] **Step 2: Validate known-good companies don't get F**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "
import json
d = json.loads(open('data/trust_scores_v2.json').read())
check = ['HDFCBANK', 'TCS', 'BAJFINANCE', 'ICICIBANK', 'INFY', 'MARUTI']
for s in d['stocks']:
    if s['symbol'] in check:
        print(f'{s[\"symbol\"]:15s} grade={s.get(\"sector_grade\",\"?\"):>3s} comp={s.get(\"composite_score\",0):5.1f} sector={s.get(\"sector\",\"?\")}')
"`

Expected: None of the known-good companies should be F. If any are, investigate.

- [ ] **Step 3: Start terminal and visually verify**

Run: `cd C:/Users/Claude_Anka/askanka.com/pipeline/terminal && python -m uvicorn app:app --port 8501`
Navigate to Intelligence tab. Verify the V2 table renders with real data.

- [ ] **Step 4: Commit data file**

```bash
git add data/trust_scores_v2.json
git commit -m "data: scorecard V2 — first quant-only run (no LLM)"
```

---

## Task 11: Sonnet LLM Re-score (API call)

**Files:**
- No new files — execute LLM scoring

**Prerequisite:** ANTHROPIC_API_KEY environment variable set.

- [ ] **Step 1: Run Sonnet re-score on all stocks**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -c "
from pipeline.scorecard_v2 import run_scorecard_v2
result = run_scorecard_v2(skip_llm=False)
print(f'Scored {result[\"total_scored\"]} stocks with LLM')
"`

This will take ~45-60 minutes and cost ~$10-12. Monitor progress in logs.

- [ ] **Step 2: Validate results**

Same validation as Task 10 Step 2. Additionally check that `biggest_strength`, `biggest_red_flag`, and `what_street_misses` are populated.

- [ ] **Step 3: Commit**

```bash
git add data/trust_scores_v2.json
git commit -m "data: scorecard V2 — full Sonnet re-score"
```

---

## Task 12: Wire V2 into Signal Pipeline

**Files:**
- Modify: `pipeline/signal_enrichment.py`
- Modify: `pipeline/website_exporter.py`

- [ ] **Step 1: Update signal_enrichment to use V2**

In `pipeline/signal_enrichment.py`, update `load_trust_scores()` to prefer V2:

Add at the top of the function, before the existing artifact scan:
```python
    # Prefer V2 scores if available
    v2_path = _REPO_ROOT / "data" / "trust_scores_v2.json"
    if v2_path.exists():
        try:
            v2 = json.loads(v2_path.read_text(encoding="utf-8"))
            if v2.get("version") == "2.0":
                for s in v2.get("stocks", []):
                    sym = s.get("symbol")
                    if not sym:
                        continue
                    grade = s.get("sector_grade", "?")
                    if grade in ("?", ""):
                        continue
                    result[sym] = {
                        "trust_grade": grade,
                        "trust_score": s.get("composite_score", 0),
                        "opus_side": None,
                        "thesis": s.get("grade_reason", ""),
                    }
                logger.info("load_trust_scores: loaded %d V2 scores", len(result))
                # Still overlay model_portfolio for opus_side
        except Exception as exc:
            logger.warning("load_trust_scores: V2 load failed — %s, falling back", exc)
```

- [ ] **Step 2: Update website_exporter**

In `pipeline/website_exporter.py`, update `export_trust_scores()` to prefer V2:

```python
def export_trust_scores() -> dict:
    """Export trust scores — prefer V2 if available."""
    v2_path = Path(__file__).resolve().parent.parent / "data" / "trust_scores_v2.json"
    if v2_path.exists():
        try:
            v2 = json.loads(v2_path.read_text(encoding="utf-8"))
            if v2.get("version") == "2.0":
                return v2
        except Exception:
            pass

    # Fallback to V1
    try:
        from signal_enrichment import load_trust_scores
        scores = load_trust_scores()
    except Exception:
        scores = {}

    stocks = []
    for sym in sorted(scores):
        s = scores[sym]
        stocks.append({
            "symbol": sym,
            "trust_grade": s.get("trust_grade"),
            "trust_score": s.get("trust_score"),
            "thesis": (s.get("thesis") or "")[:200],
        })

    return {
        "updated_at": datetime.now(IST).isoformat(),
        "total_scored": len(stocks),
        "stocks": stocks,
    }
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd C:/Users/Claude_Anka/askanka.com && python -m pytest pipeline/tests/test_signal_enrichment.py -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/signal_enrichment.py pipeline/website_exporter.py
git commit -m "feat(scorecard-v2): wire V2 into signal pipeline + website export"
```

---

## Summary

| Task | What | Tests | Est. Time |
|------|------|-------|-----------|
| 1 | Sector taxonomy + mapper | 8 | 15 min |
| 2 | Metric extractor | 9 | 20 min |
| 3 | Financial scorer | 6 | 15 min |
| 4 | Management quant | 7 | 15 min |
| 5 | Composite ranker + remarks | 6 | 15 min |
| 6 | Orchestrator | 2 | 15 min |
| 7 | Management LLM | 0 (manual) | 10 min |
| 8 | Terminal API | 0 (manual) | 10 min |
| 9 | Terminal UI | 0 (visual) | 25 min |
| 10 | Run on real data | 0 (manual) | 10 min |
| 11 | Sonnet re-score | 0 (API run) | 60 min |
| 12 | Wire into signal pipeline | reuse existing | 10 min |
| **Total** | | **38 tests** | **~3.5 hrs** |
