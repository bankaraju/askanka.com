# Reverse Regime-Stock Analysis — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Author:** Bharat + Claude

## Problem Statement

The current forward flow (ETF regime → predefined spread playbook) has a structural weakness: extreme regimes (RISK-OFF, EUPHORIA) last only ~1 day on average. By the time we get the overnight signal, the market has already gapped at open. We're always one step behind.

The reverse analysis asks: given a regime event, which stocks in our F&O universe historically moved, how much of that move was gap vs drift, and does the effect persist long enough to trade after the gap?

## Three Phases

### Phase A: Regime Stock Profile (Research Report)

**Input:**
- 66 Indian F&O stocks with 4-year daily OHLCV (2022-04-04 to 2026-04-02)
- 716 days of regime labels from ETF composite signal (5 zones: RISK-OFF, CAUTION, NEUTRAL, RISK-ON, EUPHORIA)
- 266 regime transitions with dates

**Analysis per stock × regime:**
1. **Day 0 gap** — overnight return (previous close → open) on the day a regime is classified
2. **Day 1-5 drift** — cumulative return AFTER the open (open → close over 1d, 3d, 5d)
3. **Persistence score** — is Day 3-5 drift in the SAME direction as Day 0 gap? (binary: persists / reverses)
4. **Tradeable flag** — drift exceeds gap (there's alpha left after the market has gapped)
5. **Hit rate** — what % of regime episodes produced this pattern
6. **Confidence interval** — based on episode count (17 RISK-OFF episodes = wide CI, 120 NEUTRAL = tight CI)

**Sector baskets (equal-weight, using sub-sector classification):**
- Defence: HAL, BEL, BDL
- IT Services: TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM, PERSISTENT
- Banks (Private): HDFCBANK, ICICIBANK, AXISBANK, KOTAKBANK
- Banks (PSU): SBI, BANKBARODA, FEDERALBNK
- OMCs/Downstream: BPCL, HPCL, IOC
- Upstream Energy: ONGC, OIL, COALINDIA
- Pharma: SUNPHARMA, DRREDDY, CIPLA, DIVISLAB
- Metals: TATASTEEL, HINDALCO, JSPL, SAIL, VEDL, NMDC
- Auto: MARUTI, TATAMOTORS, M&M, BHARATFORG
- FMCG: HUL, ITC, DABUR, BRITANNIA
- Real Estate: DLF, OBEROIRLTY, GODREJPROP, SOBHA
- Infra/Power: NTPC, POWERGRID, TATAPOWER, LT
- Conglomerate: RELIANCE, ADANIENT, SIEMENS
- Healthcare: APOLLOHOSP, MAXHEALTH, ASTERDM
- Aviation: INTERGLOBE
- Housing Finance: LICHSGFIN
- Cement: ULTRACEMCO, AMBUJACEM

Each basket gets the same gap/drift/persistence analysis as individual stocks.

**Output:**
- `autoresearch/reverse_regime_profile.json` — full results
- Console report ranked by tradeable + persistence
- Narrative: "In RISK-OFF, Defence basket drifts +1.8% over 3d AFTER a +0.5% gap. Hit rate 71% across 17 episodes. IT basket drifts -2.1% over 5d after -0.8% gap. Spread drift: +3.9% net, persists."

**Gate to Phase B:** If fewer than 5 stock-regime combinations show tradeable + persistent patterns (drift > gap, hit rate > 55%, persistence > 60%), the reverse analysis doesn't add value over the existing forward flow. Stop here.

### Phase B: Dynamic Stock Ranker (Daily Automation)

Only built if Phase A passes the gate.

**Daily flow:**
1. Read today's regime from ETF engine
2. Look up historical profile from Phase A results
3. Rank stocks by: drift magnitude × hit rate × persistence score
4. Compute current z-score of top stock vs its sector index
5. Output morning recommendation with confidence interval

**Output:**
- Feeds into existing morning brief (run_premarket.py or morning_brief.py)
- Telegram message: "RISK-OFF regime. Historical best: long COALINDIA (+2.3% 5d drift, 73% hit), short INFY (-1.8%, 68% hit). Current z-score: 1.4σ."
- JSON for terminal dashboard

**Integration:** Wires into existing Spread Intelligence Engine as an additional signal layer (modifier, not gate). Does NOT replace the ETF regime gate — adds stock-level intelligence on top.

### Phase C: Correlation Break Detector

Only built if Phase B is running and producing recommendations.

**What it detects:**
- Stock that NORMALLY correlates with a regime is NOT moving as expected
- Example: "HAL usually +1.5% in RISK-OFF but today it's flat. Correlation break."
- Two interpretations:
  - **Opportunity:** The stock hasn't moved yet but should → enter position
  - **Warning:** Something has changed fundamentally → avoid this stock

**Method:**
- For each stock, compute rolling correlation to its regime-expected return
- Flag when actual return deviates >1.5σ from expected
- Cross-reference with news/OI to classify as opportunity vs warning

**Output:**
- Alert in morning brief: "CORRELATION BREAK: HAL expected +1.5% in RISK-OFF, actual +0.1%. Check news."
- Feeds into spread_intelligence.py as a modifier signal

## Technical Implementation

### Data Sources
- **Stock prices:** EODHD via `eodhd_client.py` → `data/india_historical/*.csv`
- **Regime labels:** Reconstructed from ETF composite signal using `autoresearch/regime_to_trades.py` zone logic (calm_center=0.0953, calm_band=3.8974)
- **Sector classification:** Hardcoded sub-sector groups (NOT broad GICS sectors — refiners vs OMCs vs upstream matter)

### Gap vs Drift Calculation
```
For each regime transition date T:
  gap = (open_T / close_T-1) - 1          # overnight gap
  drift_1d = (close_T / open_T) - 1       # intraday Day 0
  drift_3d = (close_T+2 / open_T) - 1     # open Day 0 → close Day 2
  drift_5d = (close_T+4 / open_T) - 1     # open Day 0 → close Day 4
  
  tradeable = abs(drift_5d) > abs(gap)     # drift exceeds gap
  persists = sign(drift_5d) == sign(gap)   # same direction
```

### File Structure
```
autoresearch/
  reverse_regime_analysis.py     # Phase A: research report
  reverse_regime_ranker.py       # Phase B: daily automation (later)
  reverse_regime_breaks.py       # Phase C: correlation breaks (later)
  reverse_regime_profile.json    # Phase A output
```

### Dependencies
- pandas, numpy (already installed)
- eodhd_client.py (existing)
- ETF composite signal reconstruction (from regime_to_trades.py)
- No new API calls needed — all data is local in india_historical/*.csv

## What This Does NOT Do
- Does NOT replace the ETF regime engine (that remains the primary classifier)
- Does NOT replace management scorecards (those come later for stock selection within spreads)
- Does NOT auto-execute trades (recommendation only)
- Does NOT require downloading more stock data for Phase A (66 CSVs are sufficient)

## Success Criteria
- Phase A: At least 5 stock-regime combinations with drift > gap, hit rate > 55%, persistence > 60%
- Phase B: Morning recommendation matches or outperforms the static spread playbook over a 2-week paper trade
- Phase C: At least 3 correlation breaks detected per month that lead to actionable signals

## Regime Episode Counts (for confidence reference)
| Regime | Episodes | Avg Duration | Confidence |
|--------|----------|-------------|------------|
| RISK-OFF | 17 | 1 day | Low (wide CI) |
| CAUTION | 55 | 1 day | Medium |
| NEUTRAL | 120 | 5 days | High |
| RISK-ON | 64 | 1 day | Medium |
| EUPHORIA | 11 | 1 day | Low (wide CI) |
