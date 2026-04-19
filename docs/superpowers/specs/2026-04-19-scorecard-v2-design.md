# Scorecard V2 — Sector-Anchored Management & Financial Intelligence

**Date:** 2026-04-19
**Status:** Design
**Depends on:** Existing trust score artifacts (213 stocks), screener_financials.json, indianapi_stock.json
**Re-scoring model:** Sonnet 4.6 (API)

---

## 1. Problem Statement

The current trust score system scores each stock in isolation. The LLM freelances — picking whatever guidance items it notices, with no consistent financial yardstick. This produces:

- ICICIBANK (F, 0.0) — 21 items extracted, all classified as "quietly_dropped." India's best-run private bank.
- APOLLOHOSP (F, 13.6) — scored on bed expansion but not on ARPOB, occupancy, or margin delivery.
- SUNPHARMA (F, 5.6), INFY (F, 17.5), MARUTI (F, 10.0) — all demonstrably well-managed companies.

**Root causes:**
1. No sector-specific KPIs — the LLM picks random guidance items instead of scoring on metrics that matter for that industry.
2. No financial anchoring — management promises are scored without checking if the financials confirm delivery.
3. No peer context — an "F" hospital might still outperform an "A" metal stock, but grades are absolute, not relative.
4. Model quality — Gemini is too conservative with "DELIVERED" verdicts, especially for banking.

## 2. Solution: Three-Layer Sector-Anchored Scorecard

### 2.1 Architecture

```
Layer 1:  financial_score         (pure quant, no LLM)
          ├── Common metrics: ROE, ROCE, margins, leverage, cash conversion
          ├── Sector-specific KPIs: NIM for banks, ARPOB for hospitals
          ├── Source: screener_financials.json + indianapi keyMetrics
          └── Output: 0-100 percentile score within sector

Layer 2A: management_quant_score  (pure quant, no LLM)
          ├── Capital allocation: 5Y ROE/ROIC vs sector median
          ├── Governance: promoter pledge, auditor changes
          ├── Accounting conservatism: CFO/PAT consistency, exceptional items
          └── Output: 0-100 percentile score within sector

Layer 2B: management_llm_score    (Sonnet re-score)
          ├── Execution delivery: scored against sector-specific KPI rubric
          ├── Strategic coherence: does guidance align with sector dynamics?
          ├── Disclosure quality: clarity and frequency of communication
          └── Output: 0-100 score with cited evidence

Layer 2:  management_score = 0.5 × 2A + 0.5 × 2B
          Hard cap rule: if quant red flags exist (pledge > 30%, CFO/PAT < 0.3),
          LLM cannot push management_score above 50 regardless of narrative.

Layer 3:  composite_score = w_fin × financial + w_mgmt × management
          Weights are sector-configurable (see §4).
          Forced ranking within sector → sector_rank, sector_percentile, sector_grade.
```

### 2.2 Key Principles

1. **Grades are ALWAYS relative to sector peers.** An "A" bank is not compared to an "A" pharma stock.
2. **Financial score is fully deterministic.** Same inputs → same score. No LLM.
3. **LLM scores against a fixed rubric, not freeform.** Sonnet receives sector-specific KPIs and scores delivery against those exact KPIs.
4. **Every score carries confidence.** Users see whether a rank is based on full or partial evidence.
5. **Missing data reduces confidence, not score.** Coverage-aware renormalization.

## 3. Sector Taxonomy

### 3.1 Normalization: 54 raw industries → 24 sector entries (20 substantive + 4 small/unmapped)

| # | Sector | Stock Count | Raw Industries Mapped |
|---|--------|-------------|----------------------|
| 1 | Banks | 19 | Regional Banks |
| 2 | NBFC_HFC | 16 | Consumer Financial Services |
| 3 | IT_Services | 16 | Software & Programming, Computer Services |
| 4 | Capital_Markets | 12 | Investment Services, Misc. Financial Services |
| 5 | Pharma | 12 | Biotechnology & Drugs, Major Drugs |
| 6 | Power_Utilities | 13 | Electric Utilities, Natural Gas Utilities, Coal |
| 7 | FMCG | 13 | Personal & Household Prods., Tobacco, Food Processing, Beverages |
| 8 | Metals_Mining | 12 | Iron & Steel, Metal Mining, Misc. Fabricated Products |
| 9 | Capital_Goods | 17 | Electronic Instr. & Controls, Misc. Capital Goods, Appliance & Tool, Semiconductors |
| 10 | Chemicals | 9 | Chemical Manufacturing, Fabricated Plastic & Rubber |
| 11 | Insurance | 8 | Insurance (Life), Insurance (Prop. & Casualty), Insurance (Accident & Health) |
| 12 | Infra_EPC | 8 | Construction Services |
| 13 | Oil_Gas | 7 | Oil & Gas Operations, Oil & Gas - Integrated |
| 14 | Consumer_Discretionary | 12 | Consumer Durables, Consumer Retail, Jewelry, Recreational Products, Audio/Video, Retail (all) |
| 15 | Cement_Building | 5 | Construction - Raw Materials |
| 16 | Autos | 5 | Auto & Truck Manufacturers |
| 17 | Auto_Ancillaries | 5 | Auto & Truck Parts |
| 18 | Logistics_Transport | 6 | Water Transportation, Misc. Transportation, Railroads, Airline |
| 19 | Hospitals_Diagnostics | 3 | Healthcare Facilities |
| 20 | Defence | 3 | Aerospace & Defense |
| 21 | Telecom | 2 | Communications Services |
| 22 | Real_Estate_Hotels | 3 | Real Estate Operations, Hotels & Motels, Restaurants |
| 23 | Business_Services | 2 | Business Services |
| 24 | Unmapped | 3 | Unknown — must be manually resolved |

**Rules:**
- Consumer Durables + Consumer Retail merged into Consumer_Discretionary (12 stocks, viable for ranking).
- Hotels + Real Estate merged into Real_Estate_Hotels (3 stocks, flagged `low_peer_count`).
- Sectors with < 5 stocks: rank but flag `low_peer_count = true`. Percentile grades less reliable.
- Every stock maps to exactly one sector. Conglomerates map by dominant revenue driver.
- `Unmapped` stocks must be manually assigned before scoring.

### 3.2 Sector mapping source priority
1. Manual override in `sector_taxonomy.json` (highest priority)
2. IndianAPI `industry` field (211/216 coverage)
3. Screener sector label (fallback)

### 3.3 Sector taxonomy file: `pipeline/config/sector_taxonomy.json`

```json
{
  "version": "2.0",
  "updated_at": "2026-04-19",
  "sectors": {
    "Banks": {
      "display_name": "Banks (Private & PSU)",
      "industries": ["Regional Banks"],
      "composite_weights": {"financial": 0.70, "management": 0.30},
      "min_peer_count": 5
    }
  },
  "overrides": {
    "RELIANCE": "Oil_Gas",
    "ADANIENT": "Capital_Goods"
  }
}
```

## 4. Sector KPI Frameworks

Each sector defines 5-8 KPIs. Every stock in the sector is scored on ALL KPIs. Missing KPIs are renormalized, not penalized.

### 4.1 Banks (19 stocks)
| KPI | Direction | Weight | Source | Computation |
|-----|-----------|--------|--------|-------------|
| NIM | higher=better | 20% | Screener: (Revenue - Interest) / Total Assets | Derived |
| GNPA % | lower=better | 15% | Sonnet: extract from AR/concall | LLM-extracted |
| NNPA % | lower=better | 10% | Sonnet: extract from AR/concall | LLM-extracted |
| PCR | higher=better | 10% | Sonnet: extract from AR/concall | LLM-extracted |
| CAR / CET1 | higher=better | 15% | Sonnet: extract from AR/concall | LLM-extracted |
| CASA Ratio | higher=better | 10% | Sonnet: extract from AR/concall | LLM-extracted |
| Cost-to-Income | lower=better | 10% | Screener: Expenses / Revenue | Derived |
| ROA | higher=better | 10% | IndianAPI: keyMetrics.mgmtEffectiveness | Direct |

**Composite weights:** 0.70 financial / 0.30 management.

### 4.2 NBFC / HFC (16 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| AUM Growth | higher=better | 15% | Sonnet: extract from AR |
| NIM / Spread | higher=better | 20% | Screener: derived |
| Cost of Funds | lower=better | 10% | Sonnet: extract |
| GNPA / Stage 3 | lower=better | 15% | Sonnet: extract |
| Provision Coverage | higher=better | 10% | Sonnet: extract |
| Debt/Equity | lower=better | 10% | Screener: Borrowings / (Equity + Reserves) |
| ROA | higher=better | 10% | IndianAPI or Screener derived |
| ROE | higher=better | 10% | Screener: about.ROE |

**Composite weights:** 0.65 financial / 0.35 management.

### 4.3 Insurance (8 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Solvency Ratio | higher=better | 20% | Sonnet: extract from AR |
| Claim Settlement Ratio | higher=better | 15% | Sonnet: extract |
| Persistency (13th month) | higher=better | 15% | Sonnet: extract (life only) |
| VNB Margin | higher=better | 15% | Sonnet: extract (life only) |
| Embedded Value Growth | higher=better | 10% | Sonnet: extract |
| Combined / Expense Ratio | lower=better | 15% | Sonnet: extract |
| ROE | higher=better | 10% | Screener: about.ROE |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.4 IT Services (16 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Revenue CAGR 3Y | higher=better | 25% | IndianAPI: growth.revenueGrowthRate5Year or Screener derived |
| EBIT Margin | higher=better | 20% | Screener: OPM% |
| FCF / Net Income | higher=better | 15% | Screener: FCF / Net Profit |
| ROIC | higher=better | 15% | IndianAPI or Screener derived |
| Attrition % | lower=better | 10% | Sonnet: extract from AR/concall |
| Client Concentration | lower=better | 10% | Sonnet: top-5 client share |
| Employee Cost % | context | 5% | Screener: from AR if available |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.5 Pharma (12 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Revenue Growth ex-one-offs | higher=better | 20% | Screener: Sales CAGR |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 15% | Screener: about.ROCE |
| R&D as % of Sales | higher=better | 15% | Sonnet: extract from AR |
| Export vs Domestic Mix | context | 10% | Sonnet: extract |
| Cash Conversion (CFO/PAT) | higher=better | 10% | Screener: CFO/OP |
| USFDA Flags | lower=better | 10% | Sonnet: warning letters, observations |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.6 FMCG (13 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Volume Growth | higher=better | 20% | Sonnet: extract from concall |
| Gross Margin | higher=better | 15% | Screener: derived if available |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROIC / ROCE | higher=better | 20% | Screener: about.ROCE |
| Working Capital Days | lower=better | 15% | Screener: derived from BS |
| Brand Spend % | context | 10% | Sonnet: extract if disclosed |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.7 Autos (5 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Volume Growth | higher=better | 20% | Sonnet: extract from AR/concall |
| Realization Growth | higher=better | 10% | Sonnet: extract |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Net Debt/EBITDA | lower=better | 15% | Screener: derived |
| Capacity Utilization | higher=better | 15% | Sonnet: extract |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.8 Auto Ancillaries (5 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Asset Turns | higher=better | 15% | Screener: Sales / Total Assets |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Customer Concentration | lower=better | 15% | Sonnet: extract |
| EV Mix Exposure | higher=better | 15% | Sonnet: extract |
| Export Share | higher=better | 15% | Sonnet: extract |

**Composite weights:** 0.55 financial / 0.45 management.

### 4.9 Metals & Mining (12 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| EBITDA/ton or Margin | higher=better | 25% | Screener: OPM% (ton if extractable) |
| Net Debt/EBITDA | lower=better | 20% | Screener: derived |
| ROCE Through Cycle (5Y avg) | higher=better | 25% | Screener: historical ROCE |
| Capacity Utilization | higher=better | 15% | Sonnet: extract |
| Cash Cost Position | lower=better | 15% | Sonnet: extract if disclosed |

**Composite weights:** 0.65 financial / 0.35 management.

### 4.10 Oil & Gas (7 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Segment Profitability / GRM | higher=better | 25% | Sonnet: extract (refiners: GRM, upstream: lifting cost) |
| Net Debt/EBITDA | lower=better | 20% | Screener: derived |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Cash Conversion | higher=better | 15% | Screener: CFO/OP |
| Interest Coverage | higher=better | 10% | Screener: derived |
| Reserve Replacement (upstream) | higher=better | 10% | Sonnet: extract if upstream |

**Note:** Refiners, OMCs, and upstream have OPPOSITE dynamics on the same trigger (e.g., crude price). Sub-sector tagging is critical — the subsector field distinguishes them even though they share a sector.

**Composite weights:** 0.65 financial / 0.35 management.

### 4.11 Capital Goods (17 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Order Book / Revenue | higher=better | 20% | Sonnet: extract |
| Order Inflow Growth | higher=better | 15% | Sonnet: extract |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| Working Capital Days | lower=better | 15% | Screener: derived |
| CFO Conversion (CFO/PAT) | higher=better | 15% | Screener: CFO/OP |
| ROCE | higher=better | 15% | Screener: about.ROCE |

**Composite weights:** 0.55 financial / 0.45 management.

### 4.12 Infra / EPC (8 stocks)
Same KPIs as Capital Goods. Separate sector because business dynamics differ (project-based vs product-based).

**Composite weights:** 0.50 financial / 0.50 management.

### 4.13 Chemicals / Specialty (9 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| Asset Turns | higher=better | 15% | Screener: derived |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Export Share | higher=better | 15% | Sonnet: extract |
| Customer Concentration | lower=better | 10% | Sonnet: extract |
| Capex Intensity | context | 10% | Screener: derived |
| Working Capital Days | lower=better | 10% | Screener: derived |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.14 Cement / Building Materials (5 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| EBITDA/ton (or Margin) | higher=better | 25% | Screener: OPM% |
| Cost/ton (or Expense ratio) | lower=better | 15% | Screener: derived |
| Net Debt/EBITDA | lower=better | 20% | Screener: derived |
| Capacity Utilization | higher=better | 15% | Sonnet: extract |
| ROCE | higher=better | 15% | Screener: about.ROCE |
| Realization/ton | higher=better | 10% | Sonnet: extract |

**Composite weights:** 0.65 financial / 0.35 management.

### 4.15 Power / Utilities (13 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| PLF (generators) | higher=better | 20% | Sonnet: extract |
| Regulated ROE | higher=better | 15% | Sonnet: extract |
| Debt Service Coverage | higher=better | 20% | Screener: derived |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| ROE | higher=better | 15% | Screener: about.ROE |
| AT&C Losses | lower=better | 10% | Sonnet: extract if discom-linked |

**Composite weights:** 0.65 financial / 0.35 management.

### 4.16 Capital Markets / AMC / Brokers (12 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| AUM Growth | higher=better | 20% | Sonnet: extract |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROE | higher=better | 20% | Screener: about.ROE |
| Cash Conversion | higher=better | 15% | Screener: CFO/OP |
| Revenue Growth | higher=better | 15% | IndianAPI or Screener derived |
| Client / AUM Concentration | lower=better | 10% | Sonnet: extract |

**Composite weights:** 0.65 financial / 0.35 management.

### 4.17 Defence (3 stocks)
Uses existing 15-ratio forensic framework from `opus/sector_libraries/defence.py`. Already fully coded.

**Composite weights:** 0.50 financial / 0.50 management.
**Flag:** `low_peer_count = true`.

### 4.18 Hospitals / Diagnostics (3 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| ARPOB / Revenue per bed | higher=better | 20% | Sonnet: extract |
| Occupancy % | higher=better | 15% | Sonnet: extract |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 15% | Screener: about.ROCE |
| Bed Additions | higher=better | 15% | Sonnet: extract |
| Debt/EBITDA | lower=better | 15% | Screener: derived |

**Composite weights:** 0.55 financial / 0.45 management.
**Flag:** `low_peer_count = true`.

### 4.19 Consumer Discretionary (12 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| SSSG / Revenue Growth | higher=better | 20% | Sonnet: extract or Screener |
| Gross Margin | higher=better | 15% | Screener: derived if available |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Inventory Turns | higher=better | 15% | Screener: derived |
| Store/Distribution Growth | higher=better | 10% | Sonnet: extract |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.20 Logistics / Transport (6 stocks)
| KPI | Direction | Weight | Source |
|-----|-----------|--------|--------|
| Revenue Growth | higher=better | 20% | Screener: Sales CAGR |
| EBITDA Margin | higher=better | 20% | Screener: OPM% |
| ROCE | higher=better | 20% | Screener: about.ROCE |
| Asset Utilization | higher=better | 15% | Sonnet: extract |
| Net Debt/EBITDA | lower=better | 15% | Screener: derived |
| Cash Conversion | higher=better | 10% | Screener: CFO/OP |

**Composite weights:** 0.60 financial / 0.40 management.

### 4.21 Telecom (2 stocks), Real_Estate_Hotels (3 stocks), Business_Services (2 stocks)
Use common core KPIs only (ROE, ROCE, margins, leverage, cash conversion, growth).
**Flag:** `low_peer_count = true` for all.
**Composite weights:** 0.60 financial / 0.40 management.

## 5. Management Score — The LLM Rubric

### 5.1 Layer 2A: Management Quant Score (no LLM)

Five dimensions, each scored 1-5 by percentile within sector:

| Dimension | Weight | Proxy Metric | Source |
|-----------|--------|-------------|--------|
| Capital Allocation | 30% | 5Y ROE vs sector median + equity dilution history | Screener: historical ROE series |
| Governance | 20% | Promoter pledge % (0=5, <10%=4, 10-30%=3, 30-50%=2, >50%=1) | IndianAPI: shareholding or Sonnet |
| Execution Consistency | 25% | Std-dev of EBITDA margin over 5Y vs sector median | Screener: historical OPM% |
| Accounting Conservatism | 15% | CFO/PAT consistency over 5Y (higher=better) | Screener: CFO/Net Profit |
| Skin in the Game | 10% | Promoter holding % trend | IndianAPI: shareholding |

**Hard cap rules:**
- Promoter pledge > 30% → management_quant_score capped at 40.
- CFO/PAT < 0.3 (5Y average) → management_quant_score capped at 50.
- Auditor changed 2+ times in 3Y → penalty of -10 points.

### 5.2 Layer 2B: Management LLM Score (Sonnet re-score)

Sonnet receives a **structured prompt per stock** containing:
1. The sector-specific KPI rubric (from §4)
2. The company's annual report text and concall transcripts (from artifacts)
3. The screener financials (for cross-referencing)

Sonnet scores each stock on:

| Dimension | Weight | What Sonnet Evaluates |
|-----------|--------|-----------------------|
| Execution Delivery | 40% | Did management deliver on sector-specific KPIs they guided on? Score each KPI as EXCEEDED / DELIVERED / PARTIALLY / MISSED / DROPPED |
| Strategic Coherence | 20% | Does guidance align with sector dynamics? Are they investing in the right things for this industry? |
| Capital Allocation Narrative | 20% | Is capex productive? Are acquisitions value-accretive? Is capital being returned appropriately? |
| Disclosure Quality | 20% | Clarity, frequency, and honesty of communication. Do they address misses head-on or deflect? |

**Sonnet output format (per stock):**
```json
{
  "symbol": "APOLLOHOSP",
  "sector": "Hospitals_Diagnostics",
  "execution_delivery": {
    "score": 35,
    "kpi_scores": [
      {"kpi": "Bed Additions", "status": "MISSED", "detail": "Guided 2000 by FY27, tracking 1500 by FY28"},
      {"kpi": "ARPOB", "status": "DELIVERED", "detail": "ARPOB grew 12% YoY per concall"},
      {"kpi": "Occupancy", "status": "PARTIALLY", "detail": "65% vs guided 70%+"}
    ]
  },
  "strategic_coherence": {"score": 55, "reason": "Pharmacy + digital health diversification is sound but dilutes hospital focus"},
  "capital_allocation": {"score": 40, "reason": "Heavy capex on expansion with delayed returns; debt/EBITDA rising"},
  "disclosure_quality": {"score": 60, "reason": "Quarterly investor decks are detailed; expansion delays acknowledged"},
  "management_llm_score": 44,
  "biggest_strength": "ARPOB growth and pharmacy scale",
  "biggest_red_flag": "Bed expansion 2yr behind schedule while debt rises",
  "what_street_misses": "Pharmacy margin cross-subsidizing hospital margin miss"
}
```

### 5.3 Hard Cap Integration

After computing `management_score = 0.5 × quant + 0.5 × llm`:
- If quant red flags triggered → cap management_score at the quant cap value.
- This prevents Sonnet from overriding hard evidence. ICICIBANK can't get F if its quant metrics are top-quartile.

## 6. Scoring & Ranking

### 6.1 Percentile Scoring

For each sector, for each metric:
1. Collect values for all stocks in that sector.
2. Rank and convert to percentile (0-100).
3. For "lower is better" metrics, reverse the percentile.
4. Winsorize at 5th/95th percentile before ranking.
5. If metric is N/A for a stock, exclude from that stock's weighted sum and renormalize remaining weights.

### 6.2 Composite Score

```
composite_score = w_fin × financial_score + w_mgmt × management_score
```

Where `w_fin` and `w_mgmt` come from sector config (§4).

### 6.3 Forced Ranking & Grade Bands

Within each sector, sort by composite_score descending:
- **A:** Top 15%
- **B:** Next 20%
- **C:** Middle 30%
- **D:** Next 20%
- **F:** Bottom 15%

For sectors with < 5 stocks: still rank, but flag `low_peer_count = true` and note "grade less reliable — small peer group."

### 6.4 Confidence Score

```
coverage_pct = (available_kpis / total_sector_kpis) × 100
data_sources = count of [screener, indianapi, llm_extracted] that contributed

confidence = "high"   if coverage_pct >= 80 and data_sources >= 2
           = "medium" if coverage_pct >= 50
           = "low"    if coverage_pct < 50
```

## 7. Output Fields (per stock)

### 7.1 Core fields (always present)
```
symbol, company_name, sector, subsector
financial_score, management_score, composite_score
sector_rank, sector_percentile, sector_grade
confidence, coverage_pct, low_peer_count
```

### 7.2 Remark fields
```
grade_reason          — one-line diagnostic (auto-generated from scores)
biggest_strength      — from Sonnet re-score
biggest_red_flag      — from Sonnet re-score
what_street_misses    — from Sonnet re-score
sector_leader         — best stock in this sector + its composite score
sector_gap_to_leader  — how far behind the leader
sector_gap_to_median  — above or below sector median
```

### 7.3 Remark format
```
"APOLLOHOSP ranks 3/3 in Healthcare Facilities. Financial 45/100 (ROCE 16.6%
vs sector median 14.2%). Management 18/100 — critical bed expansion missed,
ARPOB on track. Leader: MAXHEALTH (composite 52). Confidence: medium."
```

### 7.4 Breakdown fields (for expanded row)
```
kpi_scores[]          — per-KPI score with value, percentile, direction
mgmt_quant_breakdown  — capital_alloc, governance, execution, accounting, skin_in_game
mgmt_llm_breakdown    — execution_delivery, strategic_coherence, capital_alloc_narrative, disclosure
sector_peers[]        — all stocks in sector with their composite scores
```

## 8. Data Pipeline

### 8.1 Computation flow (no new data fetching)

```
Step 1: Load sector taxonomy           → pipeline/config/sector_taxonomy.json
Step 2: Map all 213 stocks to sectors   → indianapi industry + overrides
Step 3: Extract quant metrics           → screener_financials.json (P&L, BS, CF, ratios)
                                        → indianapi keyMetrics
Step 4: Compute financial_score         → percentile within sector, weighted by KPI weights
Step 5: Compute management_quant_score  → ROE stability, pledge, CFO/PAT, margin volatility
Step 6: Sonnet re-score (API)           → sector-specific prompt per stock, batch by sector
Step 7: Compute management_llm_score    → from Sonnet output
Step 8: Blend management_score          → 0.5 × quant + 0.5 × llm, apply hard caps
Step 9: Compute composite_score         → sector-configurable weights
Step 10: Forced ranking                 → sector_rank, sector_percentile, sector_grade
Step 11: Generate remarks               → auto-generated from all scores + Sonnet fields
Step 12: Export                         → data/trust_scores_v2.json + terminal API
```

### 8.2 Files created/modified

**New files:**
- `pipeline/config/sector_taxonomy.json` — sector definitions, KPI weights, composite weights
- `pipeline/scorecard_v2/financial_scorer.py` — extract metrics from screener/indianapi, compute financial_score
- `pipeline/scorecard_v2/management_quant.py` — compute management_quant_score from quant proxies
- `pipeline/scorecard_v2/management_llm.py` — Sonnet re-score orchestrator + prompt templates
- `pipeline/scorecard_v2/composite_ranker.py` — composite_score, forced ranking, grade assignment
- `pipeline/scorecard_v2/remark_generator.py` — auto-generate remark strings from all scores
- `pipeline/scorecard_v2/__init__.py` — public API: `run_scorecard_v2()`

**Modified files:**
- `pipeline/website_exporter.py` — export `trust_scores_v2.json` with new fields
- `pipeline/terminal/api/trust_scores.py` — serve V2 scores
- `pipeline/terminal/static/js/pages/intelligence.js` — V2 UI (see §9)
- `pipeline/signal_enrichment.py` — use composite_score for signal gating

### 8.3 Sonnet re-score cost estimate

- Per stock: ~8-15K tokens input (AR excerpts + concall + screener + sector rubric), ~800 tokens response
- Total: ~2-3M input tokens, ~170K output tokens
- Sonnet 4.6 pricing: $3/M input, $15/M output
- Estimated cost: ~$7 input + ~$2.50 output ≈ **$10-12 total**
- Batching: process by sector (all banks together, all pharma together)
- Context management: send only relevant AR sections + concall excerpts, not full text. Cap input at 12K tokens per stock.
- Time: ~45-60 minutes with rate limiting

### 8.4 Refresh cadence

| What | When | Trigger |
|------|------|---------|
| Financial metrics (screener) | Quarterly | After results season |
| Management quant (pledge, dilution) | Quarterly | After results season |
| Management LLM (Sonnet re-score) | Quarterly | After new AR/concall artifacts |
| Sector taxonomy | Annual | NSE F&O list changes |
| Composite scores + ranks | After any layer refreshes | Automatic |

## 9. Terminal UI — Intelligence Tab V2

### 9.1 Table layout

**Visible columns (default):**
| Column | Width | Source |
|--------|-------|--------|
| Ticker | 100px | symbol |
| Sector | 120px | sector (with subsector tooltip) |
| Grade | 60px | sector_grade (badge, color-coded) |
| Composite | 70px | composite_score (heatmap background) |
| Fin Score | 70px | financial_score (heatmap) |
| Mgmt Score | 70px | management_score (heatmap) |
| Rank | 60px | sector_rank / sector_total |
| Key Metric 1 | 80px | top KPI for this sector |
| Key Metric 2 | 80px | second KPI |
| Remark | flex | grade_reason (truncated, full on hover) |

### 9.2 Filters
- **Sector dropdown** — filter to single sector (shows all peers)
- **Grade filter** — A/B/C/D/F checkboxes
- **Confidence filter** — high/medium/low
- **Search** — ticker search (existing)

### 9.3 Heatmap coloring
Composite, Financial, and Management score cells get background gradient:
- 80-100: deep green
- 60-79: light green
- 40-59: amber
- 20-39: orange
- 0-19: red

### 9.4 Expandable row (click to expand)
Shows a detail card with:
1. **Sector context:** "Rank 3/19 in Banks. Leader: HDFCBANK (87). Median: 52."
2. **KPI breakdown table:** each sector KPI with value, percentile, and direction indicator
3. **Management breakdown:** quant sub-scores + LLM sub-scores with cited reasons
4. **Remark:** full grade_reason + biggest_strength + biggest_red_flag + what_street_misses
5. **Confidence:** coverage_pct, data_sources, low_peer_count flag

### 9.5 Context panel (right side, on click)
Same as expandable row but in the existing side panel. Shows sector peer mini-table: all peers ranked with their composite scores, highlighting the selected stock.

## 10. Integration with Signal Pipeline

### 10.1 Trust gate update

Current trust gate in `signal_enrichment.py` uses `trust_grade` to block signals. Update to:
- Use `sector_grade` instead of absolute grade.
- Block long signals on stocks with sector_grade D or F.
- Block short signals on stocks with sector_grade A.
- Confidence filter: reduce conviction score for low-confidence grades.

### 10.2 Spread intelligence

The spread intelligence engine uses trust scores for regime-gated pair selection. Update to:
- Long the sector_grade A/B stock, short the D/F stock within same sector.
- sector_gap_to_leader informs conviction: larger gap = higher conviction on the spread.

## 11. Migration Path

### 11.1 V1 → V2 coexistence
- V2 scores stored in `data/trust_scores_v2.json` alongside existing `data/trust_scores.json`.
- Terminal serves V2 by default, V1 available via toggle.
- Signal pipeline switches to V2 after validation.
- V1 files retained but not refreshed after V2 is validated.

### 11.2 Validation criteria
V2 is promoted to primary when:
1. All 213 stocks have composite scores.
2. No stock with known-good management (HDFCBANK, TCS, BAJFINANCE) grades below C.
3. Sector rankings pass sanity check (manual review of top/bottom per sector).
4. Confidence is "high" for > 60% of stocks.

## 12. Out of Scope (Approach C, future)

- Score momentum tracking (quarter-over-quarter deltas)
- Valuation vs quality gap analysis
- Event risk flags, analyst overrides, watchlist
- Balance sheet stress detection
- Automated quarterly refresh pipeline
- Estimate revision integration
- Full 30+ column configurable table
