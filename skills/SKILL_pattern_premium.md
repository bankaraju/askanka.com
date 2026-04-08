---
name: Pattern Premium Equity Research
version: 1.0
scope: Any Indian listed equity
---

# Pattern Premium — Forensic Equity Research Skill

## What This Does

Takes any Indian listed company name and produces a forensic research report that answers one question: **Is management credible, and is the stock priced for what they can actually deliver?**

Three layers:
1. **Guidance Scorecard** — Every material financial target management committed to, cross-referenced against actual results
2. **Sector Forensic Ratios** — Industry-specific ratios that expose the gap between narrative and reality
3. **Realistic Valuation** — What the stock should be worth based on executable capacity, not headline promises

## The Two-Command Pipeline

```
python run_research.py <SYMBOL>          # Collects all data (30-60 seconds)
python run_pattern_premium.py <SYMBOL>   # Analyses and scores (3-5 minutes)
```

Output: `artifacts/<SYMBOL>/FINAL_REPORT.json`

## What Gets Collected (Automatic)

| Source | What | How |
|--------|------|-----|
| NSE API | 8 years annual report PDFs | Auto-extracts from ZIP, validates |
| NSE API | XBRL financial results (annual + quarterly) | Structured XML |
| Screener.in | 11 years P&L, Balance Sheet, Cash Flow, Ratios | HTML scrape |
| Screener.in | Earnings call transcript PDFs | BSE archive links |
| NSE API | Corporate actions, board meetings | JSON |

## Layer 1: Guidance Scorecard

### What We Extract (Material Guidance Only)
- Revenue / profit / margin targets with specific numbers
- Order book / pipeline targets
- Capex and capacity expansion with amounts and timelines
- Export / diversification targets
- New product / program delivery dates
- Dividend and return policies
- Operational KPI targets

### How We Score
Each guidance item from Year N is checked against Year N+1 actuals:

| Status | Definition |
|--------|-----------|
| **DELIVERED** | Actual meets or exceeds target (within 5%) |
| **EXCEEDED** | Actual >10% above target |
| **PARTIALLY_DELIVERED** | Actual within 5-20% of target |
| **MISSED** | Actual >20% below target |
| **QUIETLY_DROPPED** | Theme disappeared from subsequent reports without explanation |
| **TOO_EARLY** | Target timeline hasn't arrived |

### The Critical Signal: Quietly Dropped
When management stops talking about a commitment without explaining why, that is the single most important forensic indicator. It means they failed and hoped nobody would notice.

Detection rule: Theme appears in 2+ consecutive annual reports, then vanishes for 2+ years with no mention.

## Layer 2: Sector Forensic Ratios

Each sector has its own ratio library. These are not generic financial ratios — they are forensic instruments designed to expose specific patterns of misrepresentation.

### Defence & Aerospace (15 ratios)
**Core question: Can they deliver what they've booked?**

| Ratio | What It Exposes | Red Flag |
|-------|----------------|----------|
| Order Book / Revenue | Years of backlog | >7 years = unexecutable |
| Order Book / Production Capacity | Real backlog at current rates | >8 years = fantasy |
| Order Inflow / Revenue | Booking vs executing speed | >1.5 = growing gap |
| OB CAGR / Revenue CAGR | Execution gap trend | OB growing, revenue not |
| Capex / Order Book | Investing to deliver? | <0.5% = not investing |
| Capex / Revenue | Manufacturer or service co? | <3% = not manufacturing |
| Revenue / Employee | Productivity or outsourcing? | Rising + declining staff |
| Advances / Revenue | Collecting before delivery | >50% = PoC warning |
| Unbilled Rev / Revenue | Aggressive accounting | >20% = aggressive |
| Receivables Days | Cash collection | >180 = government risk |
| OCF / PAT | Paper profits or real? | <0.5 = paper profits |
| Export Rev % | International credibility | <2% after years of promises |
| Customer Concentration | Single customer risk | >90% = monopoly trap |

### Banking (23 ratios) — Implemented
NIM, GNPA, NNPA, provision coverage, slippage ratio, SMA-2, CASA, cost-to-income, CAR, CET1, etc.

### To Build: Real Estate, IT Services, Pharma, Infrastructure, FMCG

## Layer 3: Realistic Valuation

### The Problem With Street Valuations
Street analysts value defence companies on order book. They value IT companies on TCV. They value real estate on pre-sales. These are all forward-looking metrics that assume 100% execution.

### Our Approach
1. **Calculate executable capacity** — What can actually be delivered in 5 years at current production/delivery rates?
2. **Cap revenue growth** — Growth is limited by execution capacity, not demand or order book
3. **Apply agency discount** — Government companies, promoter-dominated firms get credibility haircuts based on forensic flag count
4. **Fair PE** — Based on realistic growth (not headline growth) × PEG appropriate to sector and governance quality
5. **Compare to market** — Overvaluation % = (Market Cap / Fair Value - 1) × 100

### Valuation Output
```
HAL Example:
- Order book: Rs 1,89,302 Cr (headline)
- Executable in 5 years: Rs 1,70,396 Cr (90%)
- Revenue growth: 8% (capped by production, not demand)
- Fair PE: 9.6x (PEG 1.2 × 8% growth)
- Current PE: 29.4x
- Overvaluation: 225%
```

## Pattern Premium Score

The final output is a single number: **Pattern Premium %**

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| Execution Score | 50% | Delivery rate on material guidance |
| Accuracy Bonus | 15% | Companies that beat guidance (sandbagging) |
| Dropped Theme Penalty | 25% | -3% per quietly dropped high-significance theme |
| Credibility Trajectory | 10% | Improving vs deteriorating over time |

**Verdict:**
- **PREMIUM** (>+2%): Management over-delivers. Stock deserves higher multiple.
- **FAIR** (-2% to +2%): Management delivers roughly what they promise.
- **DISCOUNT** (<-2%): Management under-delivers. Stock deserves lower multiple.

## Quality Gates

1. Every number traces to a named, dated filing or Screener.in
2. Source hierarchy: XBRL > PDF > Screener > Aggregators
3. Divergent sources flagged as "High-Interest Intelligence"
4. DCF aborted when DSO > 200 days or negative OCF
5. Minimum 3 years of annual reports for any scoring
6. Minimum 10 guidance items for Pattern Premium calculation

## What This Does NOT Do

- Does not predict stock price direction or timing
- Does not account for momentum, sentiment, or liquidity flows
- Does not replace technical analysis for entry/exit
- The market can stay irrational longer than you can stay solvent
- A 225% overvaluation doesn't mean the stock falls tomorrow

## Open Questions For Future Development

1. **Market vs Fundamentals**: Markets don't always trade on PE. An overvalued stock can stay overvalued for years if the narrative is strong. How do we reconcile forensic fair value with market reality?

2. **Catalyst Identification**: When does the gap between forensic value and market price close? What triggers re-rating (earnings miss, order cancellation, management change)?

3. **Portfolio Construction**: Should we only recommend stocks where Pattern Premium is positive AND market price is below fair value? Or can we recommend overvalued stocks with improving trajectories?

4. **Short Candidates**: Stocks with negative Pattern Premium AND overvaluation are natural short candidates. But shorting in India is hard (limited F&O stocks, no easy borrowing).

5. **Regime Integration**: How does the askanka.com regime engine (RISK-OFF / RISK-ON) interact with Pattern Premium? In RISK-OFF, even fundamentally strong stocks fall. In RISK-ON, even weak stocks rally.

6. **Sector Libraries**: Need to build for Real Estate (pre-sales vs completions), IT (TCV vs executable pipeline, attrition impact), Infra (order book vs WC bleeding), Pharma (R&D pipeline vs approvals), FMCG (distribution reach vs volume growth).

7. **Temporal Decay**: A guidance item from 5 years ago is less relevant than one from last year. Should older items decay in the scoring?

8. **Management Skin-in-Game**: Promoter holding, insider buying/selling, ESOP grants — these signal whether management believes their own guidance.
