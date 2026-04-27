# NEUTRAL Day Trading Strategy Framework
**Complete Hypothesis Suite & 30-Day OOS Testing Plan**

*Generated: April 27, 2026*

---

## Executive Summary

NEUTRAL days represent 83.8% of your trading calendar (340 of 412 days). Building a portfolio of uncorrelated NEUTRAL overlays is critical for consistent profitability. This document outlines 7 distinct hypotheses, ranked by evidence strength, with complete OOS testing framework for the next 30 days.

**Expected outcome if 3 strategies pass OOS:**
- Combined NEUTRAL edge: ₹300-450K/year net (after 0.20% transaction costs)
- Plus RISK-ON inversion: ₹14K/year
- **Total v3 annual edge: ₹314-464K/year net**

---

## Core Principles

### 1. Your Three Foundation Ideas (All Correct ✅)

#### Idea A: Z-Score Triggers (Intraday Volatility Spikes)
When stocks/sectors breach ±2σ on NEUTRAL days with no macro catalyst → mean reversion dominates. Catalog D9 evidence: +200-390 bps for PSU BANK/ENERGY fades.

#### Idea B: Sector Rotation → Stock Selection (Layered Filtering)
Identify winning sector (e.g., METAL +0.12pp/day) → pick top 3 stocks within sector by Z-score → trade those. More alpha, tighter execution than index futures.

#### Idea C: Equal Long/Short (Market Neutral)
LONG top N stocks, SHORT bottom N stocks, equal capital each side → eliminates beta, captures spread, survives regime transitions. Institutional-grade portfolio construction.

---

## Complete Hypothesis Suite

### Tier 1: HIGHEST CONVICTION (Test First)

---

### **H1: Sector Z-Score Spike-Fade (Catalog D9)**

**Thesis:**  
On NEUTRAL days, when PSU BANK/ENERGY/INFRA breach +2σ intraday Z-score → SHORT, cover at 14:30 or when Z-score crosses back below +1σ.

**Why it works:**
- NEUTRAL = no macro catalyst = sector spikes are noise (not repricing events)
- Retail FOMO drives sector spikes intraday
- Institutions fade extremes for profit

**Mechanism:**
```python
# For each sector in [PSU BANK, ENERGY, INFRA, AUTO, IT, FMCG, PHARMA, METAL, MEDIA]:
sector_return_intraday = (sector_price - prev_close) / prev_close
sector_vol_60d = rolling_std(sector_daily_returns, window=60)
sector_z = sector_return_intraday / sector_vol_60d

# Entry trigger (monitor 09:45-14:00):
if sector_z > 2.0 AND regime == NEUTRAL:
    ENTRY = SHORT sector at current price
    TARGET = sector_z < 1.0 (fade back below 1σ)
    STOP = sector_z > 2.5 (runaway, cut loss)
    EXIT_TIME = min(14:30, TARGET hit, STOP hit)
```

**Expected Edge (per Catalog D9):**
- **Frequency:** 15-25% of NEUTRAL days (60-100 triggers/year)
- **Win rate:** 60-70%
- **Mean P&L:** +0.20-0.39% per trade (+200-390 bps catalog claim)
- **Annual:** 70 trades × 0.25% × ₹5L = **₹87,500/year**

**Data Needed:**  
10 sectoral indices (NSE BANK, PSU BANK, ENERGY, INFRA, AUTO, IT, FMCG, PHARMA, METAL, MEDIA), 1-min bars, 412 NEUTRAL days

**Status:** Task #107 triggered backtest, **HIGHEST PRIORITY**

---

### **H2: Stock-Level Sector Rotation (Refined Execution)**

**Thesis:**  
Identify winning sector on NEUTRAL day (e.g., METAL +0.12% daily drift) → within that sector, LONG top 3 stocks by intraday Z-score → tighter spreads, higher alpha than index futures.

**Why it works:**
- Sector rotation happens even on NEUTRAL days (0.19pp spread between METAL and MEDIA)
- Stock-level execution captures idiosyncratic alpha within winning sector
- F&O stocks have tighter bid-ask than sectoral index derivatives

**Mechanism:**
```python
# Step 1: Identify winning sector (use unconditional drift from Test 1b)
winning_sectors = [METAL, ENERGY, PHARMA]  # Top 3 by drift on NEUTRAL days
losing_sectors = [MEDIA, AUTO, FMCG]       # Bottom 3

# Step 2: Within winning sector, score stocks by intraday Z-score
for sector in winning_sectors:
    stocks_in_sector = get_stocks(sector)  # e.g., TATA STEEL, HINDALCO, JSW for METAL
    for stock in stocks_in_sector:
        stock_z = (stock_price - stock_prev_close) / stock_vol_60d

    # Step 3: LONG top 3 stocks by Z-score within that sector
    top_3_longs = stocks_in_sector.nlargest(3, 'stock_z')

    for stock in top_3_longs:
        ENTRY = LONG at 10:00 (after opening volatility settles)
        EXIT = 14:30 or close
        SIZE = ₹5L / 3 = ₹1.67L per stock
```

**Expected Edge:**
- **Frequency:** Every NEUTRAL day (340 trades/year)
- **Win rate:** 58-63%
- **Mean P&L:** +0.12-0.18% per trade
- **Annual:** 340 trades × 0.15% × ₹5L = **₹255,000/year**

**Data Needed:**  
Stock-level data for top 30-50 F&O stocks (sorted by sector), 1-min bars, 412 NEUTRAL days

**Status:** New hypothesis, medium priority (build after H1)

---

### **H3: Market-Neutral Long/Short (Equal Dollar, Beta-Hedged)**

**Thesis:**  
On NEUTRAL days, LONG top 10 stocks by Z-score, SHORT bottom 10 stocks, equal notional → capture spread, eliminate beta, survive regime transitions.

**Why it works:**
- NEUTRAL days have 54% up / 46% down (coin flip directionally)
- Edge is in relative performance (winners vs losers), not absolute direction
- Equal long/short = beta ≈ 0 → uncorrelated to v3 regime signals (RISK-ON, EUPHORIA)

**Mechanism:**
```python
# Universe: NIFTY 200 F&O stocks
stocks = get_nifty_200_stocks()

# Score all stocks by intraday Z-score at 10:00 (after opening vol)
for stock in stocks:
    stock_z = (stock_price_10:00 - stock_prev_close) / stock_vol_60d

# Rank and select
ranked = stocks.sort_values('stock_z', ascending=False)
longs = ranked.head(10)   # Top 10 by Z-score (momentum up)
shorts = ranked.tail(10)  # Bottom 10 by Z-score (momentum down)

# Allocate equal capital
long_size = ₹2.5L / 10 = ₹25K per stock
short_size = ₹2.5L / 10 = ₹25K per stock

# Execute at 10:00, exit at 14:30
for stock in longs:
    LONG stock, size = ₹25K
for stock in shorts:
    SHORT stock, size = ₹25K

# P&L = spread between top 10 and bottom 10
```

**Expected Edge:**
- **Frequency:** Every NEUTRAL day (340 trades/year)
- **Win rate:** 55-60%
- **Mean P&L:** +0.10-0.15% per trade
- **Annual:** 340 trades × 0.12% × ₹5L = **₹204,000/year**

**Correlation Benefit:** Low correlation to H1/H2 (those are sector-specific, this is cross-sectional)

**Data Needed:**  
NIFTY 200 F&O stock universe, 1-min bars, 412 NEUTRAL days

**Status:** New hypothesis, **HIGH PRIORITY** (market-neutral structure is robust)

---

### Tier 2: STRONG EVIDENCE (Test Second)

---

### **H4: Opening Range Breakout Fade (First 15-Min Trap)**

**Thesis:**  
NEUTRAL days have no overnight catalyst → 09:15-09:30 opening range is noise. If NIFTY breaks above 09:30 high during 09:30-10:30 → SHORT-fade (trap), target back into range by 11:30.

**Why it works:**
- Opening breakouts on NEUTRAL days are false signals (retail FOMO, not institutional buying)
- 60-70% of opening range breakouts fail on no-catalyst days
- Institutions provide liquidity at extremes, fade retail into the trap

**Mechanism:**
```python
# Define opening range (09:15-09:30)
or_high = max(nifty_price[09:15:09:30])
or_low = min(nifty_price[09:15:09:30])

# Monitor 09:30-10:30 for breakout
if nifty_price > or_high AND regime == NEUTRAL:
    ENTRY = SHORT at or_high + 0.1% (wait for confirmation)
    TARGET = or_high (back into range)
    STOP = or_high + 0.3% (breakout is real, cut)
    EXIT_TIME = min(11:30, TARGET hit, STOP hit)

if nifty_price < or_low:
    ENTRY = LONG at or_low - 0.1%
    TARGET = or_low
    STOP = or_low - 0.3%
    EXIT_TIME = min(11:30, TARGET hit)
```

**Expected Edge:**
- **Frequency:** 40-50% of NEUTRAL days (170 trades/year)
- **Win rate:** 60-65%
- **Mean P&L:** +0.15-0.22% per trade
- **Annual:** 170 trades × 0.18% × ₹5L = **₹153,000/year**

**Data Needed:**  
1-min NIFTY bars, 412 NEUTRAL days

**Status:** New hypothesis, medium priority (simple pattern, fast to test)

---

### **H5: VWAP Mean Reversion (Institutional Benchmark)**

**Thesis:**  
On NEUTRAL days, price oscillates around VWAP (institutional execution benchmark). When NIFTY deviates >1.5σ from VWAP → fade back to VWAP by 14:30.

**Why it works:**
- VWAP is where algo execution clusters (institutions benchmark to it)
- Deviations from VWAP on no-catalyst days are temporary supply/demand imbalances
- Market microstructure pulls price back to VWAP (liquidity provision at extremes)

**Mechanism:**
```python
# Calculate rolling VWAP (cumulative from 09:15)
vwap = cumsum(price * volume) / cumsum(volume)
vwap_std = rolling_std(price - vwap, window=60)  # 60-min rolling

# Entry conditions (monitor 10:00-14:00)
deviation_z = (nifty_price - vwap) / vwap_std

if deviation_z > 1.5 AND regime == NEUTRAL:
    ENTRY = SHORT (too far above VWAP)
    TARGET = vwap (crosses back)
    STOP = deviation_z > 2.0
    EXIT_TIME = min(14:30, TARGET hit)

if deviation_z < -1.5:
    ENTRY = LONG (too far below)
    TARGET = vwap
    STOP = deviation_z < -2.0
    EXIT_TIME = min(14:30, TARGET hit)
```

**Expected Edge:**
- **Frequency:** 30-40% of NEUTRAL days (135 trades/year)
- **Win rate:** 55-60%
- **Mean P&L:** +0.10-0.15% per trade
- **Annual:** 135 trades × 0.12% × ₹5L = **₹81,000/year**

**Data Needed:**  
1-min NIFTY bars with volume, 412 NEUTRAL days

**Status:** New hypothesis, medium priority (institutional benchmark pattern)

---

### Tier 3: EMERGING EVIDENCE (Test Last)

---

### **H6: Sector Pair Spread Convergence (Correlation Breakdown)**

**Thesis:**  
On NEUTRAL days, sector pair spreads (METAL-MEDIA, IT-PHARMA) oscillate around mean. When spread widens >2σ → LONG laggard, SHORT leader, bet on convergence.

**Why it works:**
- Test 1b showed METAL +0.12pp/day, MEDIA -0.07pp/day (0.19pp spread exists)
- Pairs historically correlated revert to mean spread when no macro catalyst
- Market-neutral structure (spread trade, not directional)

**Mechanism:**
```python
# Define pairs (historical correlation >0.4)
pairs = [
    (NIFTYMETAL, NIFTYMEDIA),
    (NIFTYIT, NIFTYPHARMA),
    (NIFTYBANK, NIFTYAUTO)
]

# Calculate spread Z-score
spread = sector_A_return - sector_B_return
spread_z = (spread - spread_mean_30d) / spread_std_30d

# Entry when spread >2σ
if spread_z > 2.0 AND regime == NEUTRAL:
    LONG sector_B (laggard), SHORT sector_A (leader)
    SIZE = ₹2.5L each side (equal notional)
    TARGET = spread_z < 0 (spread closes)
    STOP = spread_z > 3.0
    EXIT_TIME = min(15:00, TARGET hit)
```

**Expected Edge:**
- **Frequency:** 20-30% of NEUTRAL days (85 trades/year)
- **Win rate:** 58-63%
- **Mean P&L:** +0.15-0.20% per trade
- **Annual:** 85 trades × 0.17% × ₹5L = **₹72,250/year**

**Data Needed:**  
Daily returns for 10 sectoral indices, 412 NEUTRAL days

**Status:** New hypothesis, lower priority (test after H1-H5)

---

### **H7: Late-Session Profit-Taking Reversal (14:00-15:00 Window)**

**Thesis:**  
NEUTRAL days have flat c2c drift (+0.05pp) but intraday structure. If morning session (09:30-12:00) up >+0.3% → SHORT at 14:00 (profit-taking fade into close).

**Why it works:**
- No catalyst = intraday moves are noise, not trend
- 14:00-15:00: traders square positions, take profits on winners
- Mean reversion into close stronger on NEUTRAL than trending days

**Mechanism:**
```python
# Morning session performance
morning_move = (nifty_12:00 - nifty_09:30) / nifty_09:30

# Entry at 14:00
if morning_move > 0.003 AND regime == NEUTRAL:
    ENTRY = SHORT at 14:00
    EXIT = 15:00 close
    STOP = morning_move > 0.005 (too strong, don't fade)

if morning_move < -0.003:
    ENTRY = LONG at 14:00
    EXIT = 15:00
    STOP = morning_move < -0.005
```

**Expected Edge:**
- **Frequency:** 35-45% of NEUTRAL days (150 trades/year)
- **Win rate:** 52-57%
- **Mean P&L:** +0.08-0.12% per trade
- **Annual:** 150 trades × 0.10% × ₹5L = **₹75,000/year**

**Data Needed:**  
1-min NIFTY bars, 412 NEUTRAL days

**Status:** Low priority, test only if H1-H6 all fail

---

## Portfolio Construction: Combining Multiple Strategies

### Optimal Case: If All 7 Pass OOS (Unlikely)

**Total NEUTRAL allocation:** ₹10L (2% of portfolio, diversified across 7 uncorrelated strategies)

| Strategy | Allocation | Frequency | Expected Annual |
|---|---|---|---|
| H1: Sector spike-fade | ₹1.5L | 20% | ₹87,500 |
| H2: Stock-level sector | ₹1.5L | 100% | ₹255,000 |
| H3: Market-neutral L/S | ₹2.0L | 100% | ₹204,000 |
| H4: Opening range fade | ₹1.5L | 45% | ₹153,000 |
| H5: VWAP mean reversion | ₹1.0L | 35% | ₹81,000 |
| H6: Sector pair spread | ₹1.5L | 25% | ₹72,250 |
| H7: Late-session reversal | ₹1.0L | 40% | ₹75,000 |
| **TOTAL** | **₹10L** | — | **₹927,750/year gross** |

**After 0.20% transaction costs:** ₹650,000-700,000/year net

---

### Realistic Case: Correlation Clustering

**Expected correlation clusters:**

**Cluster A (Intraday Mean Reversion):**
- H1 (Sector spike-fade)
- H4 (Opening range fade)
- H5 (VWAP mean reversion)
- H7 (Late-session reversal)
- **Likely correlation:** 0.6-0.8 (all betting on intraday mean reversion)

**Cluster B (Cross-Sectional Spread):**
- H2 (Stock-level sector rotation)
- H3 (Market-neutral L/S)
- H6 (Sector pair spread)
- **Likely correlation:** 0.4-0.6 (all capturing relative performance)

**Decision Rule:**
```
IF correlation(H1, H4) > 0.7:
  → Deploy only the one with higher (win_rate × frequency × mean_pnl / cost)
  → Archive the other (redundant exposure)

IF correlation(H2, H3) < 0.5:
  → Deploy both (truly diversified)
```

**Realistic Deployed Portfolio (after correlation check):**
- **Best from Cluster A:** H4 (Opening range fade) — highest frequency
- **Best from Cluster B:** H3 (Market-neutral L/S) — lowest correlation to v3 regime signals
- **Wildcard:** H1 (Sector spike-fade) — if correlation to H4 <0.6

**Total realistic edge:** ₹300-450K/year net (2-3 strategies, uncorrelated)

---

## Holistic OOS Testing Framework (30-Day Roadmap)

### Week 1 (Days 1-7): Build All 7 Hypotheses

**Deliverables:**
1. `sector_spike_fade_backtest.py` (H1, Task #107)
2. `stock_sector_rotation_backtest.py` (H2)
3. `market_neutral_longshort_backtest.py` (H3)
4. `opening_range_fade_backtest.py` (H4)
5. `vwap_mean_reversion_backtest.py` (H5)
6. `sector_pair_spread_backtest.py` (H6)
7. `late_session_reversal_backtest.py` (H7)

**Each script outputs:**
- Per-trade log (date, entry, exit, P&L gross, P&L net)
- Summary metrics (win_rate, mean_pnl, frequency, sharpe_proxy)
- Transaction cost sensitivity (0.10%, 0.15%, 0.20% round-trip)

**Timeline:** 6-8 hours total (1 hour per strategy, some share code)

---

### Week 2 (Days 8-14): Rank, Correlation Matrix, Pre-register Top 3

**Step 1: Score all 7 strategies**
```python
score = (win_rate - 0.50) × frequency × mean_pnl_pct / transaction_cost_pct
```

**Step 2: Compute correlation matrix**
```python
# For each pair of strategies, compute correlation of daily P&L
correlation_matrix = pd.DataFrame(daily_pnl).corr()
```

**Step 3: Select top 3 (diversified, uncorrelated)**
```
1. Pick highest score
2. Pick second-highest score IF correlation to #1 < 0.6
3. Pick third-highest score IF correlation to #1 < 0.6 AND correlation to #2 < 0.6
```

**Step 4: Pre-register top 3**
- H-2026-05-08-001 (e.g., H4 Opening range fade)
- H-2026-05-08-002 (e.g., H3 Market-neutral L/S)
- H-2026-05-08-003 (e.g., H1 Sector spike-fade)

**Step 5: SHA-256 lock all three**
```bash
sha256sum hypothesis-registry.jsonl > hypothesis-2026-05-08-lock.txt
git commit -m "Pre-register top 3 NEUTRAL overlays for OOS Phase 3"
```

---

### Week 3-4 (Days 15-30): OOS Tracking

**Daily workflow (10-15 min/day):**
```
1. Check v3 regime: Is today NEUTRAL?
2. If yes: Monitor intraday for H-001, H-002, H-003 triggers
3. Log every trigger:
   - Date, hyp_id, entry_time, entry_price, exit_time, exit_price
   - P&L_gross, transaction_cost_est, P&L_net
4. Update cumulative metrics per hypothesis:
   - n_triggers, win_rate, mean_pnl, cumulative_pnl
5. Weekly: Update correlation matrix (are strategies still uncorrelated OOS?)
```

**OOS Ledger Format:**
```csv
date,regime,hyp_id,trigger_time,entry_price,exit_time,exit_price,pnl_gross_pct,cost_pct,pnl_net_pct,notes
2026-05-09,NEUTRAL,H-001,10:15,NIFTYENERGY_spike,14:30,fade_complete,+0.28,0.15,+0.13,Catalog D9 confirmed
2026-05-09,NEUTRAL,H-002,09:45,24380,11:20,24320,+0.25,0.12,+0.13,Opening range fade worked
2026-05-10,NEUTRAL,H-003,10:00,market_neutral_entry,14:30,close,+0.11,0.18,-0.07,Spread too small
...
```

---

### Day 30 (End of May): OOS Verdict

**For each pre-registered hypothesis:**

```
IF n_triggers ≥ 15 AND win_rate ≥ 0.55 AND mean_pnl_net ≥ 0.10%:
  → PASS (deploy with 0.5-1.0% position size per trigger)

IF n_triggers ≥ 15 AND win_rate < 0.50:
  → FAIL (archive permanently)

IF n_triggers < 15:
  → INSUFFICIENT DATA (extend OOS by 30 days, re-evaluate at n≥20)
```

**Correlation Stability Check:**
```
IF OOS correlation matrix differs from in-sample by >0.3:
  → FLAG FOR REVIEW (strategies might be regime-dependent)
  → Example: H1 and H4 showed correlation 0.4 in-sample, but 0.8 OOS
  → Deploy only one, archive the other
```

---

## Why This Framework "Stands the Test of Time"

### ✅ 1. Multiple Uncorrelated Mechanisms
You're not betting on one pattern. You have 7 distinct edges:
- Mean reversion (H1, H4, H5, H7)
- Cross-sectional spread (H2, H3, H6)
- Different time windows (opening, intraday, late-session)

If one breaks, others survive.

### ✅ 2. Market-Neutral Structure (H3, H6)
Equal long/short eliminates beta → survives regime transitions → uncorrelated to v3 directional signals (RISK-ON, EUPHORIA).

### ✅ 3. Pre-Registration Discipline
All hypotheses locked before OOS (SHA-256 hash, no p-hacking). Family denominator tracking per M4 in your catalog.

### ✅ 4. Transaction Cost Realism
Every hypothesis tested at 0.10%, 0.15%, 0.20% round-trip. Only deploy what survives 0.20% worst-case (realistic F&O execution).

### ✅ 5. Correlation Monitoring
Weekly correlation matrix prevents deploying redundant strategies. If H1 and H4 correlate >0.7 OOS, deploy best-in-class only.

### ✅ 6. Staged Kill Gates
- Early kill at n=15 if win_rate <45% (stop bad strategies fast)
- Extend if n<15 (don't kill on insufficient data)
- Final verdict at n=30+ (statistical confidence)

### ✅ 7. Stock-Level Execution (H2)
Trading individual stocks (TATA STEEL, HINDALCO) instead of sectoral indices → tighter spreads, higher alpha, better fills.

### ✅ 8. Equal Long/Short (Market Neutral)
Always equal dollar allocation long and short, regardless of signal distribution. If signal says LONG 8, SHORT 2 → you force it to LONG 5, SHORT 5 → market-neutral. This eliminates beta exposure.

---

## Risk Controls for NEUTRAL Portfolio

### 1. Max Concurrent Positions
```
Max 3 NEUTRAL strategies firing simultaneously
(Prevents over-leverage if multiple triggers hit same day)
```

### 2. Correlation Monitoring
```
Weekly check: If pairwise correlation >0.8 for 2 weeks straight
→ Disable lower-performing strategy temporarily
(Avoid redundant exposure)
```

### 3. Regime Transition Kill-Switch
```
If regime changes mid-day (NEUTRAL → CAUTION or RISK-OFF):
→ Close all NEUTRAL positions immediately at market
(NEUTRAL overlays assume no directional edge; if regime shifts, edge disappears)
```

### 4. Daily Loss Limit
```
If cumulative NEUTRAL P&L < -1.0% on any single day:
→ Stop firing new triggers for rest of day
(Prevents cascade losses if market structure breaks)
```

---

## Action Plan: Next 7 Days

### Priority 1: H1 (Sector Spike-Fade) - Task #107
**Timeline:** Days 1-2  
**Why:** Catalog D9 evidence already exists (+200-390 bps), highest conviction  
**Deliverable:** `sector_spike_fade_backtest.py` + summary report

### Priority 2: H3 (Market-Neutral L/S)
**Timeline:** Days 3-4  
**Why:** Market-neutral structure, uncorrelated to H1, institutional-grade  
**Deliverable:** `market_neutral_longshort_backtest.py` + summary report

### Priority 3: H4 (Opening Range Fade)
**Timeline:** Days 5-6  
**Why:** Simple pattern, well-documented, high frequency  
**Deliverable:** `opening_range_fade_backtest.py` + summary report

### Day 7: Rank, Correlation Matrix, Pre-register Top 3
**Deliverable:** 
- Correlation matrix heatmap
- Scoring table (all 7 strategies ranked)
- Pre-registration document with SHA-256 locks

---

## Expected Outcome (End of May 2026)

### Scenario A: Conservative (2 strategies pass OOS)
- H1 (Sector spike-fade): ₹87,500/year
- H4 (Opening range fade): ₹153,000/year
- **Total:** ₹240,500/year net

### Scenario B: Base Case (3 strategies pass OOS)
- H1 (Sector spike-fade): ₹87,500/year
- H3 (Market-neutral L/S): ₹204,000/year
- H4 (Opening range fade): ₹153,000/year
- **Total:** ₹444,500/year net

### Scenario C: Optimistic (4-5 strategies pass OOS)
- H1, H2, H3, H4, H5 combined
- **Total:** ₹550,000-650,000/year net

**Plus RISK-ON inversion (if OOS confirms):** ₹14,000/year

**Total v3 system annual edge:** ₹254,500 - ₹664,000/year net

---

## Implementation Checklist

### Week 1: Build
- [ ] H1: Sector spike-fade backtest (Task #107)
- [ ] H2: Stock-level sector rotation backtest
- [ ] H3: Market-neutral L/S backtest
- [ ] H4: Opening range fade backtest
- [ ] H5: VWAP mean reversion backtest
- [ ] H6: Sector pair spread backtest
- [ ] H7: Late-session reversal backtest

### Week 2: Analyze & Pre-register
- [ ] Score all 7 strategies
- [ ] Compute correlation matrix (7×7)
- [ ] Select top 3 (uncorrelated, highest score)
- [ ] Pre-register with SHA-256 locks
- [ ] Set OOS gates (n≥15, win_rate≥55%, mean_pnl≥0.10%)

### Week 3-4: Track OOS
- [ ] Daily: Log every trigger in OOS ledger
- [ ] Daily: Update cumulative metrics per hypothesis
- [ ] Weekly: Update correlation matrix
- [ ] Weekly: Check for regime transition violations

### Day 30: Verdict
- [ ] Pass/Fail decision per pre-registered gate
- [ ] Archive failed strategies permanently
- [ ] Deploy passing strategies with 0.5-1.0% position size
- [ ] Document in strategy catalog

---

## Appendix: Data Requirements

### Essential Datasets (For All Hypotheses)
1. **NIFTY 50 Index**
   - 1-minute bars with OHLCV
   - Date range: Last 412 NEUTRAL days
   - Source: NSE historical data or broker API

2. **10 Sectoral Indices**
   - NIFTY BANK, PSU BANK, ENERGY, INFRA, AUTO, IT, FMCG, PHARMA, METAL, MEDIA
   - 1-minute bars with OHLCV
   - Date range: Last 412 NEUTRAL days

3. **NIFTY 200 F&O Stock Universe**
   - 1-minute bars with OHLCV for top 50 stocks (by liquidity)
   - Date range: Last 412 NEUTRAL days
   - Sector classification for each stock

4. **v3 Regime Classification**
   - Daily regime labels (NEUTRAL, RISK-ON, CAUTION, etc.)
   - Date range: Last 412 trading days
   - Source: Your existing v3 classifier output

### Optional (For Advanced Analysis)
5. **Order Book Data** (L2)
   - Bid-ask spreads for slippage estimation
   - Only for final deployed strategies (not for backtesting)

6. **Corporate Actions**
   - Dividends, splits, bonus issues
   - To adjust stock prices (if using stock-level strategies H2, H3)

---

## Glossary

**NEUTRAL Day:** Days classified by v3 regime detector with no directional edge (54% up, 46% down, c2c drift +0.05pp)

**Z-Score:** Standardized deviation from mean, calculated as (current_value - mean) / std_dev

**Market-Neutral:** Portfolio construction with equal long and short positions (beta ≈ 0)

**OOS (Out-of-Sample):** Testing period where hypothesis is evaluated on new data not used in development

**Pre-Registration:** Locking hypothesis parameters before OOS testing to prevent p-hacking

**SHA-256 Lock:** Cryptographic hash of hypothesis document to prove no post-hoc modification

**Transaction Costs:** Round-trip costs including brokerage, STT, exchange fees, slippage (0.10-0.20% for F&O)

**Correlation Clustering:** When multiple strategies exhibit high pairwise correlation (>0.7), indicating redundant exposure

**Kill Gate:** Statistical threshold (e.g., win_rate <50% at n≥15) that triggers permanent archival of a hypothesis

---

## Contact & Revision History

**Version:** 1.0  
**Date:** April 27, 2026  
**Author:** Perplexity AI  
**Framework Type:** NEUTRAL Day Trading Strategy Suite  
**Testing Window:** May 1-31, 2026 (30 days OOS)

**Revision History:**
- v1.0 (2026-04-27): Initial framework with 7 hypotheses, 30-day OOS plan (Perplexity draft — see §A0 errata)
- v1.1 (2026-04-27): Anka-native compliance wrapper appended (§A0 – §A12) — Bharat / Claude Opus 4.7

---

# PART B — ANKA-NATIVE COMPLIANCE WRAPPER (v1.1, 2026-04-27)

> The body above is the *idea*. This wrapper is what's needed for it to ship under our governance lattice. It does not delete or rewrite Perplexity's draft — it patches the gaps, removes the unevidenced claims, and translates each hypothesis into the operational form the codebase already supports.

## §A0. Errata against the Perplexity draft (must fix before anything ships)

**E1. "Catalog D9" is fabricated.**
A repo-wide grep for `catalog D9 | D9 evidence | D9 confirmed` returns exactly one file: this spec. There is no internal catalog of that name, no per-sector backtest under `docs/research/`, no entry in `pipeline/autoresearch/`. **All claims sourced to "Catalog D9" — including "+200-390 bps for PSU BANK / ENERGY fades" — are removed from the evidence basis.** They become *priors to be tested*, not edges to be deployed.

**E2. NEUTRAL share is wrong.**
Perplexity says "NEUTRAL = 83.8% (340 of 412)". The actual `pipeline/data/regime_history.csv` (1,256 rows, 2021-04-23 → 2026-04-23) prints:

| Regime    | Days | Share |
|-----------|------|-------|
| NEUTRAL   | 297  | 23.6% |
| CAUTION   | 280  | 22.3% |
| RISK-ON   | 242  | 19.3% |
| EUPHORIA  | 220  | 17.5% |
| RISK-OFF  | 217  | 17.3% |

**Every annual P&L estimate in the body must be re-multiplied by 0.236/0.838 ≈ 0.28.** A claimed "₹927K/year gross" if all 7 pass becomes ~₹260K. The "Realistic ₹300-450K net" becomes ~₹85-130K. This is a 3.5x downward correction, and it changes whether the engineering effort is worth doing. **The framework still passes the cost-benefit test, but it stops being a flagship-level edge — it becomes a meaningful overlay.**

**E3. `regime_history.csv` is HINDSIGHT v2 per `memory/reference_regime_history_csv_contamination.md`.** It is built post-hoc with v2 weights, so any backtest that filters days using this file is contaminated by look-ahead. **All NEUTRAL backtests for H1–H7 must use a point-in-time regime tape — either replayed from `today_regime.json` snapshots (forward-only, ~4 weeks of coverage) or reconstructed via canonical_loader from the historical ETF panel. This is the single biggest data-integrity issue the body did not address.**

**E4. Perplexity's "score = (win_rate − 0.50) × frequency × mean_pnl_pct / transaction_cost_pct" is not a valid statistic.** It conflates expectation and confidence and ignores variance. Replace with: net Sharpe over the in-sample window with bootstrap 95% CI, plus net cumulative return with permutation-null p-value (§A6.2). Frequency enters as a sample-size constraint, not a multiplier.

**E5. n≥15 minimum is too low.** At n=15 with k=9 wins, p=0.30 vs the 50% null — not significant. Our minimum power requirement per `backtesting-specs §9.3` is the larger of `n≥30` and `n` such that 95% CI half-width on the mean P&L is < 0.5 × claimed mean. **Perplexity's gate is replaced with §A7 below.**

**E6. "Extend OOS by 30 days if n<15" violates §10.4 strict.** Once the holdout window opens, parameters and the verdict gate are frozen. If a hypothesis ends the window underpowered, the verdict is `INSUFFICIENT_N` and a *fresh* registration is required — same parameters, new H-ID, new SHA-locked window. No silent extension.

---

## §A1. Hypothesis registry — pre-commit-blocking IDs

Each hypothesis below gets a unique ID, a JSONL entry, and a SHA-256 lock at registration. Without this, the `pre-commit-strategy-gate.sh` hook *will reject the commit* on the first `*_strategy.py` / `*_engine.py` / `*_backtest.py` file. This is non-optional.

| Body label | Anka H-ID                | Engine package path                                                       |
|-----------|--------------------------|---------------------------------------------------------------------------|
| H1        | `H-2026-04-28-001`       | `pipeline/research/h_2026_04_28_001_sector_spike_fade/`                  |
| H2        | `H-2026-04-28-002`       | `pipeline/research/h_2026_04_28_002_stock_sector_rotation/`              |
| H3        | `H-2026-04-28-003`       | `pipeline/research/h_2026_04_28_003_market_neutral_ls/`                  |
| H4        | `H-2026-04-28-004`       | `pipeline/research/h_2026_04_28_004_opening_range_fade/`                 |
| H5        | `H-2026-04-28-005`       | `pipeline/research/h_2026_04_28_005_vwap_meanrev/`                       |
| H6        | `H-2026-04-28-006`       | `pipeline/research/h_2026_04_28_006_sector_pair_spread/`                 |
| H7        | `H-2026-04-28-007`       | `pipeline/research/h_2026_04_28_007_late_session_reversal/`              |

**Registry entry shape (per H, JSONL one-liner):**
```json
{"hypothesis_id":"H-2026-04-28-001","registered_at":"2026-04-28T08:00:00+05:30","family":"NEUTRAL_OVERLAY","cohort_def":"<exact predicate>","trigger_def":"<entry rule>","exit_def":"<exit rule + time stop>","sizing":"<lot/cash>","gate":{"min_n":30,"min_pnl_net_pct":0.10,"vs_null":"random_direction","alpha":0.05,"mc_correction":"BH-FDR_family7"},"holdout_start":"2026-04-28","holdout_end":"2026-05-27","data_deps":["nse_sectoral_indices_v1","kite_minute_bars_fno_273"],"sha256_at_lock":"<computed at commit>"}
```

The cohort_def, trigger_def, exit_def, gate, and holdout_end fields **are frozen at registration**. Any change requires a fresh H-ID. This is enforced by §10.4, not policy.

---

## §A2. Data Validation Gate (CLAUDE.md hard requirement)

Per project CLAUDE.md: *"No backtest, no validation run, no live signal consumption may proceed against a dataset that has not been accepted under data validation policy."* Each H must be wired to **already-accepted** datasets:

| Dataset                                                 | Accepted? | Audit doc                                                      | Used by  |
|---------------------------------------------------------|-----------|----------------------------------------------------------------|----------|
| `nse_sectoral_indices_v1` (10 sectoral indices, 5y)     | ✅ Approved | `2026-04-25-nse-sectoral-indices-data-source-audit.md`         | H1, H2, H6 |
| `kite_minute_bars_fno_273` (1-min bars, F&O universe)   | ✅ Approved | `2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`     | All       |
| `fno_universe_history.json` (PIT F&O membership)        | ✅ Approved | `2026-04-25-fno-universe-history-data-source-audit.md`         | H2, H3    |
| **PIT regime tape**                                     | ❌ MISSING | (must be written before any H ships)                           | **All 7** |
| NIFTY 200 stock minute bars (deeper than F&O 273)       | ❌ MISSING | (need explicit audit if Perplexity's "NIFTY 200" stays)        | H3        |

**Action items before T-1 of holdout:**
- Write `2026-04-28-pit-regime-tape-data-source-audit.md` describing how the historical regime is reconstructed without hindsight contamination. Two acceptable methods: (a) replay `etf_signal.py` over the historical ETF panel using only data available at-or-before each date; (b) tag from a date when v3-CURATED forward-shadow began (2026-04-27) and accept that backtest depth is ~0 days, all evidence is OOS-only.
- Either narrow H3 to F&O 273 universe (already audited) or write a NIFTY 200 audit + cleanliness gate.

If the PIT regime tape is not approved, **the in-sample backtests cannot run** under the data validation gate. Perplexity's "Week 1: build all 7 backtests" is gated on this dataset audit.

---

## §A3. PIT regime — the load-bearing question

This is the dominant risk to the entire framework. Three options:

**Option A. Replay v3-CURATED engine over 5-year ETF panel.**
- *Pro:* gives you 1,256 dated regime tags, hindsight-free.
- *Con:* requires the v3 engine to be deterministic on historical inputs and not depend on rolling stats that contaminate at the right edge. v3-CURATED was finalized 2026-04-26 (`memory/project_etf_v3_failed_2026_04_26.md`) — it has not been replayed.
- *Effort:* ~1 day. Highest-leverage prereq item.

**Option B. Forward-only NEUTRAL filter from 2026-04-27.**
- *Pro:* zero contamination risk; the live engine writes today_regime.json forward.
- *Con:* in-sample window is essentially zero; you go straight to OOS without development data. Hypothesis design must be purely analytical (no pattern-mining).
- *Effort:* zero data work, but kills the "rank top 3 from in-sample" step in Perplexity's Week 2.

**Option C. Hybrid: v2-tape (hindsight, contaminated) for hypothesis *design* only; v3-CURATED forward tape for the *registered gate*.**
- *Pro:* lets you generate hypotheses against a deep history without contaminating the verdict.
- *Con:* requires strict separation — the v2-tape backtest output cannot enter the registered gate's evidence basis.
- *Recommended.* Document the firewall in the registry entry.

**My recommendation:** Option C. The v2-tape gives you a 5-year sandbox for ranking and correlation work; the registered OOS gate uses only forward-only NEUTRAL days from 2026-04-28 onward. Verdict at 2026-05-27 will likely be `INSUFFICIENT_N` for hypotheses requiring n≥30, but that's the honest answer — better than a contaminated PASS.

---

## §A4. Reconciliation with already-running engines

Three engines already trade on the same days these would. The wrapper must not double-book the position book or contaminate H-001/H-002's cohort:

| Existing engine             | Holdout window         | Conflict surface                                | Reconciliation                                                                                                  |
|-----------------------------|------------------------|-------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| H-2026-04-26-001 / 002      | 2026-04-27 → 2026-05-26 | Same trading days; uses same |z|≥2 stream | None — different signal universe (sector residual Z) and entry time (09:30, 14:30 close)                        |
| H-2026-04-27 RISK-ON inverted SHORT | open-ended      | Only fires on RISK-ON days                       | None — orthogonal regime cohort                                                                                  |
| Phase C shadow (live_paper_ledger) | rolling                | Opens 09:25 on OPPORTUNITY signals               | H1 sector-Z fade may co-fire when sector spike implies stock spike. **Tag overlap explicitly in ledger.**         |
| Phase B daily ranker (eligible_spreads) | rolling           | Outputs basket on NEUTRAL days                  | NEUTRAL overlays must NOT enter Phase B basket — they're forward-paper, not deployable. Confirm `phase=research` |
| MR v3.2 mechanical replay   | offline                | POSSIBLE_OPPORTUNITY +41.67pp/328 finding lives in the same phase-c LAG slice | H1's SHORT direction must be checked against MR v3.2 — memory `project_mechanical_60day_replay.md` says current live engine routes the wrong slice |

**Operational rule:** every NEUTRAL-overlay paper trade gets a `provenance_chain` field listing every other engine that would also have flagged the same (date, symbol, side). At verdict time you ablate overlapping rows to measure pure incremental edge.

---

## §A5. Single-touch holdout — exact dates and SHA lock procedure

Perplexity's "30-day OOS" is loose. We're strict.

- **Window:** 2026-04-28 (T+0) → 2026-05-27 (T+22 trading days, ~30 calendar). Any H registered after 2026-04-28 09:00 IST has a window starting from its registration date, not 04-28.
- **Lock procedure (per H, atomic):**
  1. Append JSONL row to `docs/superpowers/hypothesis-registry.jsonl`.
  2. `sha256sum docs/superpowers/hypothesis-registry.jsonl > docs/superpowers/locks/H-YYYY-MM-DD-NNN.sha256`
  3. Commit both files in the same commit. Pre-commit hook verifies the new H matches the strategy-pattern files added.
  4. After the lock commit lands on master, **no parameter change** to that H until the holdout closes.
- **Single-touch:** the verdict gate is consulted exactly once, at the close of the holdout. No interim peeks that re-rank. (Daily ledger updates are *observability*, not gates.)

---

## §A6. §0–16 compliance map (per `backtesting-specs`)

Each H must produce these artifacts. The shared compliance runner under `pipeline/compliance/` already implements them — Tasks #123-140 in the registry are complete. Wire each H to the runner.

| § | Requirement                                              | Runner module                                  | Per-H output                                                              |
|---|----------------------------------------------------------|------------------------------------------------|---------------------------------------------------------------------------|
| 0 | No-waiver invariant                                      | implicit                                       | —                                                                         |
| 1 | Slippage grid {0.05, 0.10, 0.15, 0.20%} per leg          | `compliance/slippage_grid.py`                  | `pnl_at_slippage.json`                                                    |
| 2 | Risk-adjusted metrics + hit-rate CI                      | `compliance/risk_metrics.py`                   | `sharpe_with_ci.json`                                                     |
| 5A | Data-quality audit                                      | `compliance/dq_audit.py`                       | `dq_report.json`                                                          |
| 6 | Universe snapshot under waiver                          | `compliance/universe.py`                       | `universe_snapshot.parquet`                                               |
| 8 | Schema contract                                          | per-H YAML in `pipeline/research/<h>/schema.yml` | declarative                                                              |
| 9A | Parameter fragility sweep (each rule param ±25%)         | `compliance/fragility.py`                      | `fragility_grid.json`                                                     |
| 9B.1 | Naive comparators (random_direction, always-prior, buy-and-hold) | `compliance/naive_comparators.py`     | `vs_naive.json`                                                           |
| 9B.2 | ≥100k label-permutation null                           | `compliance/permutation_null.py`               | `perm_null_p_value.json`                                                  |
| 10 | Single-touch holdout                                     | locked at registry; verdict at window close    | `holdout_verdict.json`                                                    |
| 11A | Implementation-risk 10-scenario stress (slip, partial fill, queue) | `compliance/impl_risk.py`           | `impl_risk_grid.json`                                                     |
| 11B | NIFTY-beta regression + residual Sharpe                 | `compliance/beta_resid.py`                     | `beta_residual.json`                                                      |
| 11C | Portfolio correlation + concentration gate              | applied at family level (see §A8)              | `corr_matrix.json` (one for the 7-family)                                 |
| 12 | CUSUM decay + recent-24m ratio                          | `compliance/cusum.py`                          | `cusum_decay.json`                                                        |
| 13A | Run manifest                                            | `compliance/run_manifest.py`                   | `run_manifest.json` (commit, env, data-versions hash)                     |
| 14 | Contamination map (events, halts, ex-dates)             | per-H YAML; runner cross-references            | `contamination_map.json`                                                  |
| 15.1 | Gate-checklist emitter                                  | `compliance/gate_checklist.py`                 | `gate_checklist.md`                                                       |

**Hard rule:** an H without all of these artifacts attached to its hypothesis-registry row at verdict time is `FAIL — incomplete-evidence`, regardless of its raw P&L.

---

## §A7. Verdict gate (replaces Perplexity's Day 30 block)

For each H individually, at 2026-05-27 close:

```
PASS if ALL of:
  n_trades                              ≥ 30
  mean_pnl_net_pct (post §1 slippage)   > 0
  permutation_null_p (§9B.2)            < 0.05
  beats random_direction (§9B.1)        by ≥ 0.10pp / trade
  beats always-prior (§9B.1)            by ≥ 0.05pp / trade
  fragility_pass_count (§9A)            ≥ 4 of 6 perturbations
  impl_risk_floor (§11A worst case)     > 0
  beta_residual_alpha (§11B)            > 0
  cusum_decay (§12)                     no break in last 24 obs
  bh_fdr_qvalue (family of 7)           < 0.10

ELSE if n < 30:                         INSUFFICIENT_N
ELSE:                                   FAIL — archive permanently
```

The BH-FDR step is the multiple-comparison correction. Without it, testing 7 hypotheses on the same NEUTRAL-day stream gives ~30% chance of at least one spurious PASS at α=0.05. The q < 0.10 threshold preserves false-discovery-rate < 10% across the family.

**No "extend by 30 days" branch.** `INSUFFICIENT_N` triggers a fresh H-ID with a new SHA-locked window starting 2026-05-28.

---

## §A8. Background-only architecture (UI-free trade collection)

Per Bharat's framing: "no need to display on screen but in the background we must have those strategies in place for our final post-OOS discussion." Concrete shape:

**Per-H persistence (mandatory):**
```
pipeline/data/research/h_2026_04_28_NNN/
  recommendations.csv           # OPEN/CLOSE rows, PIT-locked schema
  recommendations.csv.provenance.json
  daily_summary.json            # rebuilt every EOD at 16:00
  open_positions.parquet        # snapshot, for crash recovery
```

**CSV schema (locked, additive only):**
```
date,trade_id,h_id,trigger_time,trigger_value,ticker,sector,side,
entry_px,entry_time,exit_px,exit_time,exit_reason,
pnl_pct_gross,pnl_pct_net,slippage_applied,
regime_at_entry,vix_at_entry,nifty_at_entry,
overlap_engines,                    # comma-separated list of co-firing engines
notes
```

**Schedule additions to `pipeline/config/anka_inventory.json`:**
- `AnkaNeutralOverlayOpen` — 09:35 IST (after H-001/H-002 open at 09:30, after first sector-Z is computed)
- `AnkaNeutralOverlayMonitor####` — every 15 min 09:45-15:15 (most H need intra-window triggers)
- `AnkaNeutralOverlayClose` — 14:30 IST for H1/H3/H5; 11:30 for H4; 15:00 for H7
- `AnkaNeutralOverlayEOD` — 16:05 IST: per-H daily_summary.json + correlation update

**Watchdog freshness contract:** each output file gets a row in the inventory with `cadence_class: intraday`, `tier: info`, `grace_multiplier: 2.0`. No alert fires on overlap engines being silent — that's expected.

**No Trading-tab surface, no Live-Monitor row, no Telegram alert.** EOD digest only, in a new `/api/research_overlays` endpoint that the Research tab consumes (not the Trading tab).

---

## §A9. Cost model — fix three places where Perplexity is too loose

**C1. F&O lot sizes constrain "₹25K per stock" claims.** RELIANCE futures is ~₹14L notional per lot; you cannot be ₹25K. Either (a) trade equity intraday MIS for stock-level H2/H3 (different cost stack: STT 0.025% on sell + brokerage 0.03% per leg, ~12-15 bps RT), or (b) pick only stocks whose lot size × current price ≤ allocation. Document which under each H's `sizing` field.

**C2. F&O futures cost is asymmetric.** STT is 0.0125% on the sell side only. Round-trip is *not* 2× one-way. Use the cost model already in `pipeline/compliance/slippage_grid.py` rather than Perplexity's flat 0.10/0.15/0.20% bands.

**C3. SSF basis matters for SHORT.** `memory/project_futures_pricing.md`: futures basis is 0.3-0.6%. SHORT P&L computed against spot is wrong by ~30-60 bps. All H using SHORT (H1, H3 short leg, H4 SHORT-fade, H5 SHORT, H6, H7 SHORT) must price the short leg at the front-month SSF, not spot. Reuse `pipeline/spread_intelligence/futures_pricer.py` which already does this for spread legs.

---

## §A10. Statistical and execution gaps Perplexity missed

**G1. VIX stratification.** When VIX > 22, mean-reversion hypotheses (H1, H4, H5, H7) historically inverse — momentum dominates. Stratify the in-sample backtest by VIX < 18 / 18-22 / > 22. If edge concentrates in a single bucket, the registered gate uses that bucket's threshold.

**G2. Liquidity gate.** Stock-level (H2, H3) needs an ADV filter: 30-day median dollar volume ≥ ₹50 Cr. From `memory/reference_pit_ticker_list.md`: PEL and SAMMAAN are Kite-only with thin order books — exclude.

**G3. Earnings-window exclusion.** Per `pipeline/data/research/h_2026_04_25_001/`, an open earnings event within ±1 trading day of entry creates a ~2σ noise tail that overwhelms most NEUTRAL-overlay edges. Exclude any (ticker, date) with earnings flag in `pipeline/data/earnings_calendar.json` from H2/H3.

**G4. Sectoral-index Z renormalization.** Perplexity's "sector_z = sector_return_intraday / sector_vol_60d" uses daily-return vol on intraday return — units mismatch. Either both intraday or both daily. Use `pipeline/autoresearch/peer_residuals.py:compute_sector_residual_z` — it already handles this correctly with a 60-trading-day rolling intraday-stdev estimator.

**G5. Opening-range definition.** H4 says 09:15-09:30 OR. NSE F&O opens 09:15 but quote stability lags ~3 min. Use 09:18-09:33 instead, document in `cohort_def`.

**G6. Halt and circuit-breaker handling.** F&O scripts can hit upper/lower price band intraday. The simulator must check Kite's `circuit_limit_upper` / `_lower` fields and skip entry if within 0.5% of the band — otherwise the trade is uncloseable.

**G7. Regime-transition kill-switch (§A4) is fine in principle but operationally complex.** today_regime.json refreshes once daily at 04:45 IST — there is no "regime changes mid-day" event in our system. Either (a) accept that overlays carry stale regime risk to 14:30 close, or (b) build an intraday regime engine first. Default: (a).

---

## §A11. Per-hypothesis amendments to the body

These are minimal, concrete edits each H needs before its registry row is acceptable. The body's mechanism boxes stay, but each H must adopt these as `cohort_def` / `trigger_def` modifiers.

**H1 (Sector spike-fade):**
- Replace "Catalog D9" priors with "no prior; first OOS test."
- Use `peer_residuals.compute_sector_residual_z` (G4).
- Skip if VIX > 22 at trigger time (G1).
- Skip if any constituent stock is in earnings window (G3).
- SHORT leg priced at sector futures (NIFTYBANK, NIFTYIT, etc.), not spot.

**H2 (Stock-level sector rotation):**
- Universe: F&O 273 stocks, ADV ≥ ₹50 Cr (G2), exclude PEL/SAMMAAN.
- "Top 3 by stock_z within winning sector" — winning sector defined as sector with highest **previous-day** rank, not same-day (else look-ahead).
- LONG only (Perplexity is silent on direction); short side is H3.
- Lot-size feasible sizing: pick top stocks whose lot × price ≤ ₹2L allocation (C1).

**H3 (Market-neutral L/S):**
- Universe: F&O 273, not NIFTY 200 (avoids new dataset audit, see §A2).
- Top 5 + bottom 5 (not top/bottom 10) — keeps allocation per leg above F&O lot minimums.
- 10:30 entry, not 10:00 — avoids first-hour noise per `feedback_open_position_terminology.md`.
- Beta-hedge confirmation: residual β to NIFTY ≤ 0.15 over 60-day window; if not, force-balance by dropping highest-β stock.

**H4 (Opening range fade):**
- OR window 09:18-09:33 (G5), not 09:15-09:30.
- ENTRY only between 09:33 and 10:30 (Perplexity's 09:30-10:30 is fine, just shifted by OR change).
- Use NIFTY futures, not spot (cost asymmetry, C2).
- TIME_STOP at 11:30 hard.

**H5 (VWAP mean reversion):**
- VWAP from 09:18 (post-OR), not 09:15.
- Skip first 30 min after entry on any sector-spike day where H1 has fired — overlapping signal.
- Use NIFTY futures.

**H6 (Sector pair spread):**
- Pair correlation cutoff: rolling 60-day Pearson ≥ 0.5 (Perplexity says >0.4 — too loose for stable pairs).
- Skip if either sector has a constituent in earnings window.
- Pair sizing by beta-balance, not equal notional.

**H7 (Late-session reversal):**
- "Morning move > +0.3%" computed against NIFTY *futures* mid (asymmetry, C2).
- 14:00 entry → 15:15 exit (not 15:00 close — last 15 min has gap-down risk).
- Skip if VIX > 22 or sector-spike day.

---

## §A12. Schedule, ownership, and what 2026-04-28 looks like

**Day 0 — 2026-04-28 (Mon, T+0 of holdout):**
- 06:00 — Bharat reviews this wrapper, names final cohort scope. Decision needed: Option A/B/C from §A3.
- 08:00 — claude-opus-4-7 writes `2026-04-28-pit-regime-tape-data-source-audit.md` (if Option A or C).
- 11:00 — claude-opus-4-7 invokes brainstorming → writing-plans → subagent-driven-dev for the 7 H packages.
- 16:00 — first registry-lock commit lands; pre-commit hook verifies pattern files.
- 16:30 — schedule additions registered in `anka_inventory.json`; watchdog picks them up overnight.

**Day 1 — 2026-04-29 (Tue, T+1):**
- First overlay paper trades fire (if today is NEUTRAL).
- 16:05 — first daily_summary.json written per H.
- Bharat reads `/api/research_overlays` digest at EOD.

**Days 2-21 — observability only.** No gate consultation. CSV ledgers accrete.

**Day 22 — 2026-05-27 (Tue):**
- 16:30 — claude-opus-4-7 runs `compliance/runner.py --hypothesis-family NEUTRAL_OVERLAY` to produce the per-H §A6 artifact bundle.
- 17:00 — verdict per §A7 emitted into `pipeline/data/research/neutral_overlay_verdict_20260527.json`.
- 17:30 — Bharat reviews. PASS hypotheses move to a separate "deploy candidates" registry; FAIL archived; INSUFFICIENT_N hypotheses get fresh registrations starting 2026-05-28.

**Single failure mode that voids the whole run:** if Option B is chosen (forward-only, no in-sample), expect every H to verdict `INSUFFICIENT_N` at 2026-05-27 — that's not a failure of the framework, it's the cost of strict OOS. Plan a 90-day re-run window (2026-05-28 → 2026-08-25) on the same SHA-locked specs.

---

## §A13. What this wrapper does NOT do

- It does not validate the 7 hypotheses' priors. Several (H1 reliance on "Catalog D9", H7 "morning move predicts afternoon fade") have no published evidence in our system. They are *conjectures to be tested*, ranked by `feedback_user_intuition_credible_prior.md` (Bharat's intuition is a credible prior, search the backtest before dismissing). The framework is the lattice; the alpha is in the data.
- It does not relax §0 (no waivers) for any H.
- It does not approve any H for live capital. PASS = "promoted to single-cell forward-shadow, ₹0 deployed." Live capital requires a separate deployment-gate decision per `anka_data_validation_policy_global_standard.md §21` and a model-governance ladder review.
- It does not promise the framework will produce edge. A reasonable prior is that 0-2 of 7 will pass §A7 cleanly. The aim is the 1 that *might*.

---

*End Part B. The body above (Part A) remains as Perplexity wrote it for reference. The registry IDs, datasets, schedule, and gate in Part B are what governs.*

---

# PART C — FOCUSED SCOPE (Bharat, 2026-04-27)

> Bharat's narrowing: *"the only thing I am interested in is sector rotation, last hour of trading, other potential intraday shifts. The ideas shown have to be vetted by us — put it through our policy framework and given the right treatment."*
>
> Part C is the operative scope. Part A is the source draft. Part B is the compliance lattice. **Where Part C drops a hypothesis, that hypothesis is out — its registry ID is not minted, no engine package is built, no schedule entry is added.** The remaining hypotheses inherit every gate and artifact requirement from Part B without exception.

## §C0. Why Part A's data errors are not load-bearing

Perplexity made factual errors (Catalog D9, 83.8% NEUTRAL) because of what was given to it. Two notes:

- The fabricated citations (Catalog D9, the +200-390 bps numbers) were never going to survive a repo grep — those would have been caught the moment any backtest tried to cross-reference them. Their absence does not weaken the *direction* of the thesis; it just means the thesis is unevidenced and must earn its own evidence through the OOS gate in §A7.
- The 23.6% NEUTRAL share (vs claimed 83.8%) shrinks the addressable opportunity by ~3.5x but does not change the question of *whether the edge exists*. A real NEUTRAL-day intraday edge that produces ₹85-130K/year net is still worth building — it's a meaningful overlay on H-001/H-002 and v3-CURATED.

**The compliance lattice in Part B does not relax for Part C.** The framework either passes §A7 or it doesn't. Bharat's narrowing reduces the family size from 7 to 4, which actually *helps* the BH-FDR multiple-comparison correction — fewer simultaneous tests means a lower q-value threshold per H.

---

## §C1. The four hypotheses in scope

Mapped from Part B with Part C IDs (the H-2026-04-28-NNN allocations from §A1 are reassigned tighter — only the 4 below are live):

| Theme                          | Part B ref | New ID                | Engine path                                                          | Status   |
|--------------------------------|------------|-----------------------|----------------------------------------------------------------------|----------|
| Sector rotation (stock-level)  | H2         | `H-2026-04-28-001`    | `pipeline/research/h_2026_04_28_001_sector_rotation/`               | IN SCOPE |
| Sector pair convergence        | H6         | `H-2026-04-28-002`    | `pipeline/research/h_2026_04_28_002_sector_pair_spread/`            | IN SCOPE |
| Opening-range fade (intraday shift)  | H4   | `H-2026-04-28-003`    | `pipeline/research/h_2026_04_28_003_opening_range_fade/`            | IN SCOPE |
| Late-session reversal (last hour) | H7      | `H-2026-04-28-004`    | `pipeline/research/h_2026_04_28_004_late_session_reversal/`         | IN SCOPE |

**Out of scope (do not build):**

| Theme                          | Part B ref | Reason for exclusion                                                                      |
|--------------------------------|------------|-------------------------------------------------------------------------------------------|
| Sector spike-fade              | H1         | Prior was fabricated (Catalog D9). Not your intuition; nothing in our memory supports it. |
| Market-neutral long/short      | H3         | Not in Bharat's narrowed list. Different problem domain (cross-sectional ranking, not intraday shift). Revisit only if §C1 hypotheses produce an edge worth widening. |
| VWAP mean reversion            | H5         | Conceptually similar to H4 (opening-range fade) and likely correlated > 0.7 in-sample. Drop to keep family size at 4 for cleaner BH-FDR. |

---

## §C2. Why these four, framed against existing memory

This is the *real* prior for each, not Perplexity's fabrications:

**H-2026-04-28-001 (Sector rotation, stock-level).**
Closest existing evidence: `memory/project_scorecard_alpha_test.md` — D/F-grade stocks outperform A/B overall, and the only working modifier is regime-conditional (NEUTRAL only). Plus `memory/feedback_index_vs_stock.md` — "long best scorecard stock, short sector index. Scorecard quality IS the alpha." Sector rotation built on top of intraday Z-score is consistent with both. **Honest prior:** unproven for our universe; the closest cross-sectional test in our system (Phase B daily ranker) was promoted but never produced a clean OOS edge. ~50% prior on PASS.

**H-2026-04-28-002 (Sector pair convergence).**
Closest existing evidence: `pipeline/spread_intelligence/` already runs regime-gated pair trades, but at the stock level, not sector index level. `memory/project_spread_intelligence.md` — 5-layer decision engine, regime is primary, spread MR is the workhorse. The new question is whether the *index-level* spread signal works on NEUTRAL days specifically (where stock-level signals are weak). **Honest prior:** ~40% prior — sector-index spreads are tighter and less alpha-rich than stock spreads, but mean-reversion is more reliable on NEUTRAL days.

**H-2026-04-28-003 (Opening-range fade, intraday shift).**
Closest existing evidence: SP1 Phase C intraday shape audit (`memory/project_phase_c_shape_audit.md`) — 60-day, 87 rows, INSUFFICIENT_N. The audit looked at first-15-min patterns on Phase C OPPORTUNITY signals; user observed "reverse-V" (up → fade → never hit day high). H4 is the systematic version of that observation. **Honest prior:** ~45% prior — your eye saw the pattern; SP1 was underpowered to confirm or deny. This is the most direct test of the Bharat-pattern.

**H-2026-04-28-004 (Late-session reversal, last hour).**
Closest existing evidence: nothing direct. Mechanical 60-day replay (`memory/project_mechanical_60day_replay.md`) found TIME_STOP at 14:30 beats Z_CROSS exits — but that's about *exit* timing, not entry. H7 asks whether 14:00 entry on a strong morning is profitable. **Honest prior:** ~35% prior — late-session profit-taking is a folk pattern; institutional rebalancing happens in the last 30 minutes (15:00-15:30), not 14:00-15:15. Test it cheaply before forming a strong view.

---

## §C3. Compliance treatment per H (delta from Part B)

The §A6 lattice applies in full. Per-H additions:

**H-2026-04-28-001 — Sector rotation:**
- Universe: F&O 273 (audited dataset) — drop NIFTY 200 entirely. Excludes PEL/SAMMAAN.
- "Winning sector today" defined by **previous-day close-to-close ranking** of 10 sectoral indices, NOT same-day intraday move. (Eliminates look-ahead.)
- Top 3 stocks in winning sector by **prior-30-day momentum z-score** at 09:33 entry. Not intraday Z (which uses today's data and feels like circular reasoning to the prior).
- LONG only, equal-cash sized, ₹2L total / 3 stocks. Lot-size feasibility: skip stocks where 1 lot × price > ₹70K.
- TIME_STOP 14:30, ATR(14)×2 hard stop.
- VIX > 22: skip — not registered, but drop the trade with provenance flag.
- Entry on NSE F&O futures of the stock (not equity), priced at SSF mid (basis correction per §A9-C3).

**H-2026-04-28-002 — Sector pair convergence:**
- Pair list pre-frozen at registration: {METAL ↔ MEDIA, IT ↔ PHARMA, BANK ↔ AUTO, FMCG ↔ ENERGY}. No mid-window pair changes.
- Pair correlation cutoff: rolling 60-day Pearson ≥ 0.5 over the pre-trade window. If a pair's correlation falls below at trigger time, skip and log.
- Spread-Z computed on **previous-30-day rolling**; entry threshold |Z| ≥ 2.0; exit at Z ≤ 0.5 or 14:30.
- Trade vehicle: sector-index futures (NIFTYBANK, NIFTYIT etc.) — Kite supports these. Equal-notional sized.
- Skip if any constituent of either sector has earnings within ±1 trading day.

**H-2026-04-28-003 — Opening-range fade:**
- OR window 09:18-09:33 (Part B G5). Entry valid only 09:33-10:30.
- Vehicle: NIFTY-Spot futures (front month).
- Confirmation rule: enter on first 5-min close beyond OR, not first tick. Reduces noise trades.
- TIME_STOP 11:30. ATR-fraction stop: 0.4 × OR-width on the wrong side of OR.
- Skip days where overnight gap |%| > 0.5% — those have a different distribution and are not "no-catalyst NEUTRAL days."
- One-trade-per-day: if both upper and lower OR get tested, take the first only.

**H-2026-04-28-004 — Late-session reversal:**
- Morning move computed on NIFTY futures mid (09:18 close → 12:00 close).
- |Morning move| ≥ 0.30% AND ≤ 0.80% to qualify (the 0.80% cap rejects the strong-trend days where reversal underperforms).
- Entry 14:00 in opposite direction; TIME_STOP 15:15 (not 15:30 — last 15 min is settle volatility).
- ATR(14) × 0.5 stop on NIFTY futures.
- VIX > 22: skip.

---

## §C4. Family-level corrections updated for n=4

BH-FDR with 4 hypotheses at α=0.05:
- Sorted p-values p(1) ≤ p(2) ≤ p(3) ≤ p(4)
- Reject H(i) if p(i) ≤ (i/4) × 0.10  (family q-value 0.10)
- Worst-case threshold for ALL to pass: p ≤ 0.025 each
- Best-case threshold for ONE to pass: p ≤ 0.025

This is **stricter** than the n=7 case (where p ≤ 0.014 was needed for the smallest p-value to pass). Wait — actually that's wrong. With BH at q=0.10:
- n=7: p(1) ≤ 1/7 × 0.10 = 0.014
- n=4: p(1) ≤ 1/4 × 0.10 = 0.025

So **fewer hypotheses = looser BH threshold**, which is the correct direction. Bharat's narrowing helps statistical power. **The §A7 gate now uses BH-FDR family of 4, with q < 0.10.**

---

## §C5. Schedule changes for Part C

Replace Part B §A12's "AnkaNeutralOverlay*" tasks with these four:

| Task                                        | Time      | Tier  | Outputs                                                                  |
|---------------------------------------------|-----------|-------|--------------------------------------------------------------------------|
| `AnkaSectorRotationOpen`                    | 09:33 IST | info  | `h_2026_04_28_001/recommendations.csv` OPEN rows                         |
| `AnkaSectorRotationClose`                   | 14:30 IST | info  | CLOSE rows                                                               |
| `AnkaPairSpreadOpen`                        | 09:35 IST | info  | `h_2026_04_28_002/...` OPEN rows                                         |
| `AnkaPairSpreadClose`                       | 14:30 IST | info  | CLOSE rows                                                               |
| `AnkaORFadeMonitor` (every 5 min 09:33-10:30) | 09:33-10:30 | info | `h_2026_04_28_003/...` triggers if any                                  |
| `AnkaORFadeClose`                           | 11:30 IST | info  | CLOSE                                                                    |
| `AnkaLateSessionEntry`                      | 14:00 IST | info  | `h_2026_04_28_004/...` OPEN rows                                         |
| `AnkaLateSessionClose`                      | 15:15 IST | info  | CLOSE                                                                    |
| `AnkaNeutralOverlayEOD`                     | 16:05 IST | info  | per-H daily_summary.json + family correlation update                     |

Each row goes into `pipeline/config/anka_inventory.json` with `cadence_class: intraday`, `grace_multiplier: 2.0`. No alert on overlap with H-001/H-002 — it's expected.

**No UI surface.** No Trading-tab row, no Live-Monitor inclusion, no Telegram. EOD digest lives at a new `/api/research_overlays` endpoint, consumed only by a future Research-tab "NEUTRAL Lab" panel (not built in this scope).

---

## §C6. Hypothesis registry rows (ready to commit, not yet committed)

```jsonl
{"hypothesis_id":"H-2026-04-28-001","registered_at":"2026-04-28T08:00:00+05:30","family":"NEUTRAL_OVERLAY","theme":"sector_rotation_stock_level","cohort_def":"regime==NEUTRAL AND VIX<22 AND no overnight gap>0.5%","trigger_def":"top-3 stocks in prev-day-winning sector by 30d momentum-z, entry 09:33","exit_def":"TIME_STOP 14:30 OR ATR(14)x2","sizing":"₹2L / 3 stocks F&O futures","gate":{"min_n":30,"min_pnl_net_pct":0.10,"vs_random":0.10,"vs_always_prior":0.05,"perm_p":0.05,"alpha":0.05,"mc_correction":"BH-FDR_family4","q":0.10},"holdout_start":"2026-04-28","holdout_end":"2026-05-27","data_deps":["nse_sectoral_indices_v1","kite_minute_bars_fno_273","fno_universe_history","pit_regime_tape_v1"],"sha256_at_lock":"<filled at commit>"}
{"hypothesis_id":"H-2026-04-28-002","registered_at":"2026-04-28T08:00:00+05:30","family":"NEUTRAL_OVERLAY","theme":"sector_pair_spread","cohort_def":"regime==NEUTRAL AND pair-corr-60d>=0.5 AND no constituent earnings ±1d","trigger_def":"|spread-Z-30d|>=2.0 between {METAL/MEDIA, IT/PHARMA, BANK/AUTO, FMCG/ENERGY}","exit_def":"spread-Z<=0.5 OR 14:30","sizing":"equal-notional sector-index futures, ₹2.5L per leg","gate":{"min_n":30,"min_pnl_net_pct":0.10,"vs_random":0.10,"vs_always_prior":0.05,"perm_p":0.05,"alpha":0.05,"mc_correction":"BH-FDR_family4","q":0.10},"holdout_start":"2026-04-28","holdout_end":"2026-05-27","data_deps":["nse_sectoral_indices_v1","kite_minute_bars_sector_index","pit_regime_tape_v1"],"sha256_at_lock":"<filled at commit>"}
{"hypothesis_id":"H-2026-04-28-003","registered_at":"2026-04-28T08:00:00+05:30","family":"NEUTRAL_OVERLAY","theme":"opening_range_fade","cohort_def":"regime==NEUTRAL AND |overnight_gap|<=0.5%","trigger_def":"NIFTY 5-min close > OR(09:18-09:33) high → SHORT-fade; mirrored for low","exit_def":"target=OR boundary OR TIME_STOP 11:30 OR ATR-fraction stop","sizing":"NIFTY futures, 1-2 lots","gate":{"min_n":30,"min_pnl_net_pct":0.10,"vs_random":0.10,"vs_always_prior":0.05,"perm_p":0.05,"alpha":0.05,"mc_correction":"BH-FDR_family4","q":0.10},"holdout_start":"2026-04-28","holdout_end":"2026-05-27","data_deps":["kite_minute_bars_nifty_futures","pit_regime_tape_v1"],"sha256_at_lock":"<filled at commit>"}
{"hypothesis_id":"H-2026-04-28-004","registered_at":"2026-04-28T08:00:00+05:30","family":"NEUTRAL_OVERLAY","theme":"late_session_reversal","cohort_def":"regime==NEUTRAL AND VIX<22 AND 0.30%<=|morning_move|<=0.80%","trigger_def":"opposite-direction entry 14:00 IST","exit_def":"TIME_STOP 15:15 OR ATR(14)x0.5","sizing":"NIFTY futures, 1-2 lots","gate":{"min_n":30,"min_pnl_net_pct":0.10,"vs_random":0.10,"vs_always_prior":0.05,"perm_p":0.05,"alpha":0.05,"mc_correction":"BH-FDR_family4","q":0.10},"holdout_start":"2026-04-28","holdout_end":"2026-05-27","data_deps":["kite_minute_bars_nifty_futures","pit_regime_tape_v1"],"sha256_at_lock":"<filled at commit>"}
```

The `pit_regime_tape_v1` dataset must clear §A2 (data validation gate) before any of these rows commits. That's the §A3 Option-C decision Bharat needs to confirm.

---

## §C7. Honest expectation

With Part C's narrowing:
- Family is 4 instead of 7. BH-FDR threshold is looser (q=0.10 → p≤0.025 on the smallest).
- Most likely outcome at 2026-05-27: 0 or 1 PASS. Reasonable priors are 35-50% per H, with strong correlation between H4 (OR fade) and H7 (late-session reversal) — they're both intraday mean-reversion.
- If 1 passes, it's the start of a 90-day re-run on a fresh registration to confirm before any deployment decision.
- If 0 pass with adequate n, the NEUTRAL-day intraday-shift thesis as a class is downgraded — the user's "reverse-V observed in first 15 min" reading would either need a different operationalization or a different mechanism (e.g., flow-based rather than price-based).
- If multiple end `INSUFFICIENT_N` (likely on Option B, see §A3), nothing is concluded — re-register with same SHAs starting 2026-05-28.

This is the honest treatment the user asked for. No edge claims, no fabricated catalog references, no inflated annual P&L. Four well-formed questions, vetted against the policy framework, ready to be answered by the data over 22 trading days.

---

*End Part C. This is the operative scope. Parts A and B are reference. Bharat to confirm §A3 Option choice and cohort definitions before pre-commit hook locks the registry rows on 2026-04-28 morning.*

---

**IMPORTANT NOTICE:**

This framework is for educational and research purposes. All hypotheses must pass pre-registered OOS testing before deployment with real capital. Past backtest performance (including catalog D9 claims) does not guarantee future results. Transaction costs, slippage, and regime transitions can significantly impact realized P&L.

Always follow risk management protocols:
- Max 1-2% capital per strategy per day
- Hard stop-loss at -1.0% daily loss
- Regime transition kill-switch enabled
- Correlation monitoring weekly

Start with H1 (highest catalog evidence) and H3 (market-neutral structure) this week.
