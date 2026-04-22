# Spread Intelligence Engine — Design Spec

**Date:** 2026-04-13
**Status:** Approved (revised with NotebookLM review feedback)
**Depends on:** Signal Universe v2 (2026-04-02), autoresearch ETF engine, config.INDIA_SPREAD_PAIRS

---

## Goal

Build a unified trading decision engine that combines five concurrent signal layers into a single actionable recommendation per spread. Replaces manual analysis with an automated morning scan and intraday alerts. Futures-only execution, equal-weight legs, regime-gated entry.

---

## The Five Signal Layers

These are **concurrent inputs, not sequential steps.** All five feed into the recommendation simultaneously.

| Layer | What it provides | Source | Frequency |
|---|---|---|---|
| 1. Regime | Which spread categories are active today | autoresearch/ ETF engine (20 ETFs, ML-optimized) | Overnight |
| 2. Spread Divergence | Where is the spread vs its regime-specific history | 5yr EODHD daily prices, z-score per regime | Weekly recompute, daily check |
| 3. Technicals | Is the move overextended or confirming | RSI(14), 20DMA, 50DMA per stock | Every 15 min |
| 4. OI/PCR | Institutional positioning, pre-news anomaly detection | Kite options chain, near-ATM OI | Every 15 min |
| 5. News/Policy | Catalysts that explain or predict moves | RSS feeds (MoneyControl, ET, LiveMint), indianapi.in announcements | Every 15 min |

---

## Architecture (Pipeline B — Independent Modules)

```
OVERNIGHT (weekly or on-demand):
  spread_statistics.py    → data/spread_stats.json
    - 5yr daily prices for all 22 spread stocks (EODHD)
    - Reconstruct daily spread returns (equal weight Rs 1L per leg)
    - Tag each historical day with regime from ETF engine
    - Per spread per regime: mean, σ, percentiles, max drawdown
    - Refreshed weekly (Sunday night) or on config change

PRE-MARKET 9:00 AM:
  regime_scanner.py       → data/today_regime.json
    - Reads autoresearch/ latest regime output
    - Maps regime → eligible spreads via regime_trade_map.json
    - Fetches Asian pre-market: Nikkei, Kospi, SGX Nifty, Brent, Gold, VIX
    - Checks overnight futures for indication of results/political news

MORNING SCAN 9:25 AM (first actionable prices, 10 min after open):
  technical_scanner.py    → data/technicals.json
    - RSI(14), vs 20DMA %, vs 50DMA %, 5-day trend for all spread stocks
    - Signal classification: OVERBOUGHT / BULLISH / NEUTRAL / BEARISH / OVERSOLD

  oi_scanner.py           → data/positioning.json
    - ATM ± 5% strikes OI for all spread stocks (nearest expiry)
    - PCR per stock, OI change vs 20-day avg
    - Anomaly flag when OI change > 2x 20-day avg daily change

  news_scanner.py         → data/news.json
    - RSS poll: MoneyControl, Economic Times, LiveMint, CNBC-TV18
    - indianapi.in /recent_announcements for spread stocks
    - Classify: sector tag, sentiment (positive/negative/neutral)
    - Flag policy events: RBI, SEBI, NBFC regulation, EV policy, tax reform, etc.

  spread_intelligence.py  → data/recommendations.json + Telegram
    - Reads all 5 JSON artifacts
    - Applies gate + modifier logic (see below)
    - Outputs ranked recommendations
    - Sends morning scan to Telegram

INTRADAY (every 15 min, 9:40 to 15:25):
  Same pipeline, lighter:
    - technical_scanner.py (re-run with latest prices)
    - oi_scanner.py (re-run OI)
    - news_scanner.py (re-run RSS)
    - spread_intelligence.py (re-evaluate)
  Telegram alerts ONLY on state changes:
    - Spread crosses entry threshold (was WATCH → now ENTER)
    - Spread hits exit threshold (was HOLD → now EXIT)
    - OI anomaly detected (new flag)
    - Regime change intraday (rare but possible)
  No spam — if nothing changed, no message.

EOD 15:35:
  run_eod_report.py (already built) → Telegram track record + P&L snapshot
```

---

## Gate + Modifier Decision Logic

### Gates (must BOTH pass, or spread is skipped)

**Gate 1 — Regime Active:**
- Read today's regime from `data/today_regime.json`
- Look up `regime_trade_map.json` for eligible spreads in this regime
- Spread not in today's regime → INACTIVE, skip entirely

**Gate 2 — Spread Diverging:**
- Compute today's spread return: avg(long leg returns) − avg(short leg returns)
- Equal weight: Rs 1,00,000 per leg
- Load regime-specific distribution from `data/spread_stats.json`
- Compute z-score = (today's spread − regime mean) / regime σ
- |z-score| > 1.0 → DIVERGING (opportunity exists)
- |z-score| ≤ 1.0 → AT MEAN (no edge), skip

### Modifiers (adjust conviction, don't block)

Each modifier adds or subtracts from a base conviction score of 50.

**Modifier 1 — Technicals (±15 each):**

| Condition | Effect |
|---|---|
| RSI < 30 on short-side stock | BOOST +15 (oversold short = good for our position) |
| RSI > 70 on long-side stock | CAUTION −15 (overbought long = risky entry) |
| Long side above 20DMA + short side below 20DMA | BOOST +15 (trend confirming) |
| Both sides same side of 20DMA | CAUTION −15 (no divergence in trend) |

**Modifier 2 — OI/PCR (±15 each):**

| Condition | Effect |
|---|---|
| Short-side PCR > 1.2 | BOOST +15 (puts stacking = more downside expected) |
| Long-side PCR < 0.5 | BOOST +15 (calls dominating = upside momentum) |
| OI change > 2x 20-day avg on any leg | FLAG ⚠️ (anomaly — institutional foreknowledge) |
| IV skew inversion on any leg (OTM put IV > ATM IV by 20%+) | FLAG ⚠️ (pre-news signal — stronger than OI alone) |
| Short-side PCR < 0.5 | CAUTION −15 (market expects short side to rally) |

**Modifier 3 — News/Policy (±15 each):**

| Condition | Effect |
|---|---|
| Policy event matches spread sector (e.g., NBFC regulation → PSU NBFC spread) | BOOST +15 |
| Policy event contradicts spread thesis | CAUTION −15 |
| No relevant news | No change |

### Conviction Score → Recommendation

| Score | Label | Action |
|---|---|---|
| 80+ | HIGH | **ENTER** — all signals aligning, deploy Rs 1L per leg |
| 50–79 | MEDIUM | **WATCH** — gates passed but wait for more confirmation |
| < 50 | LOW | **CAUTION** — gates passed but modifiers say wait |

### Anomaly Flags

OI anomaly flags (⚠️) are shown regardless of conviction score. An anomaly means institutional positioning is shifting — the headline hasn't dropped yet. Flag = "investigate this stock, something is happening."

---

## Position Management

### Sizing
- Rs 1,00,000 per leg, equal weight across all legs in a spread
- Maximum 4 concurrent spreads (≈ Rs 20L margin cap)
- If more than 4 spreads qualify, rank by conviction score, take top 4

### Entry
- First actionable prices at 9:25 AM (10 min after open, past auction noise)
- Futures contracts only (nearest month, all stocks are F&O)
- Market orders on futures (acceptable slippage for Rs 1L lots)

### Exit Rules (whichever triggers first)
1. **Regime change with hysteresis** — regime must stay changed for 2 consecutive sessions before triggering exit. Prevents whipsaw on noisy 1-day regime flips.
2. **Mean reversion** — z-score returns to 0 (spread returned to regime mean)
3. **Time stop** — 10 trading days max holding period
4. **Loss stop** — z-score exceeds ±3σ for this regime (historical extreme, thesis broken). Note: in extreme stress, 3σ may be too distant — audit historical data to validate.
5. **2-day stop** — spread moves against us for 2 consecutive days beyond daily stop level (from spread_statistics). Historical audit required: check if this stop triggers just before mean reversion (premature exit risk).

### Futures Rollover
- Roll positions 3 trading days before expiry
- Close current month, open next month at market
- Log the roll in P&L tracker (no artificial P&L break)

---

## Spread Statistics Computation (Weekly)

For each of 11 spreads × 5 regimes:

```python
# Pseudocode
for spread in config.INDIA_SPREAD_PAIRS:
    for regime in [RISK_OFF, CAUTION, NEUTRAL, RISK_ON, EUPHORIA]:
        daily_returns = []
        for day in last_5_years:
            if day.regime == regime:
                long_return = avg(stock.return for stock in spread.long)
                short_return = avg(stock.return for stock in spread.short)
                spread_return = long_return - short_return
                daily_returns.append(spread_return)
        
        stats[spread][regime] = {
            "mean": mean(daily_returns),
            "std": std(daily_returns),
            "percentiles": [5, 10, 25, 50, 75, 90, 95],
            "max_drawdown": max_drawdown(daily_returns),
            "count": len(daily_returns),  # days in this regime
            "avg_5day_return_from_divergence": ...,  # what happens after z>1
        }
```

**Regime reconstruction:** Run the ETF engine retroactively on 5 years of ETF data to classify each historical trading day into one of 5 regimes. This uses the same `etf_optimal_weights.json` and thresholds as the live engine.

**Equal weight assumption:** Each leg gets Rs 1,00,000 notional. Daily return = (close − prev_close) / prev_close. Spread return = avg(long returns) − avg(short returns). This makes all spreads comparable regardless of stock price or lot size.

**Leg correlation check (safety gate):** For each spread per regime, compute the Pearson correlation between long-side avg return and short-side avg return. If correlation > 0.8, the spread is effectively a single directional bet — flag as "CORRELATED, spread ineffective" and exclude from recommendations. In extreme stress regimes, most stocks correlate to 1.0, rendering spreads useless. This check prevents entering correlated spreads during market crashes.

**2-day stop historical audit:** During the weekly recompute, for each spread per regime, simulate the 2-day stop rule over 5 years. Report: (a) how often it triggers, (b) what the avg next-5-day return was AFTER the stop triggered. If the spread frequently reverts to profitability after the stop triggers, the stop is premature and the threshold should be widened for that specific spread/regime combo.

---

## OI/PCR Anomaly Detection

The options OI layer serves two purposes:
1. **Confirmation** — PCR confirms or contradicts the spread thesis
2. **Pre-news detection** — unusual OI shifts signal institutional foreknowledge

### What constitutes an anomaly
- OI daily change > 2× the 20-day average daily OI change for that stock
- PCR flips direction (was < 0.7, now > 1.2, or vice versa) in a single session
- IV skew inversion — OTM put IV exceeds ATM IV by 20%+ (stronger pre-news signal than OI alone, indicates institutional hedging ahead of announcements)
- Block deal detected on any spread stock (> Rs 10 Cr, from BSE bulk deal data)
- Delivery % spike > 2× 20-day average (institutional accumulation = high delivery)

### What the system does with anomalies
- Flag with ⚠️ in recommendations
- Log to `data/oi_anomalies.json` with timestamp, stock, OI change, PCR shift
- If anomaly on a spread stock that's already in WATCH → auto-promote to "INVESTIGATE"
- Does NOT auto-enter positions based on anomaly alone

---

## News/Policy Scanner

### Sources (RSS, polled every 15 min)
- MoneyControl RSS
- Economic Times Markets RSS
- LiveMint RSS
- CNBC-TV18 RSS

### Corporate Announcements (API, polled every 15 min)
- indianapi.in `/recent_announcements?stock_name=X` for all 22 spread stocks

### Event Classification
Pre-defined policy categories that map to spreads:

| Policy Category | Affected Spreads | Direction |
|---|---|---|
| RBI rate decision | PSU Banks vs Private, PSU NBFC vs Private | Rate cut = PSU bull |
| NBFC regulation | PSU NBFC vs Private Banks | Tightening = PSU bear |
| EV policy | EV Plays vs ICE Auto | Subsidy = EV bull |
| Defence procurement | Defence vs IT, Defence vs Auto | Order = defence bull |
| Oil policy / Iran / blockade | Upstream vs Downstream, Coal vs OMCs | Escalation = upstream bull |
| Tax reform | Infra Capex Beneficiaries | Stimulus = infra bull |
| SEBI regulation | Broad market impact | Case-by-case |
| Tariff / trade war | Pharma vs Cyclicals | Defensive rotation |

### Matching Logic
- RSS headline → keyword match against policy categories
- If match found → tag the relevant spread with BOOST or CAUTION
- If no match → no news modifier applied

---

## Telegram Output Format

### Morning Scan (9:25 AM)

```
━━━━━━━━━━━━━━━━━━━━━━
🎯 ANKA MORNING SCAN — 13 Apr 2026
━━━━━━━━━━━━━━━━━━━━━━
REGIME: 🔴 MACRO_STRESS (MSI 71)
VIX: 20.45 (+8.5%) | Brent: $102.20

ENTER — HIGH CONVICTION:
  🟢 Defence vs Auto [Score: 85]
     Divergence: +2.1σ (96th pctl)
     LONG: HAL (RSI 65, +7.6% vs 20DMA)
            BEL (RSI 57, +3.6% vs 20DMA)
     SHORT: MARUTI (RSI 59, -4.3% today)
             TMPV (neutral)
     OI: WIPRO PCR 0.35 (bearish) ✓
     News: Trump blockade → defence boost
     Margin: Rs 4.3L | 1% stop = Rs 10,881

WATCH — MEDIUM:
  🟡 Upstream vs Downstream [Score: 65]
     Divergence: +1.4σ (82nd pctl)
     ⚠️ ONGC RSI 70.1 (overbought)
     OI: BPCL PCR 1.21 (puts stacking) ✓

INACTIVE (wrong regime): 5 spreads
━━━━━━━━━━━━━━━━━━━━━━
```

### Intraday Alert (only on state change)

```
🔔 SPREAD ALERT — 11:25 IST
Defence vs Auto: WATCH → ENTER
  MARUTI now -5.1% (was -4.3%)
  z-score crossed +2.5σ
  Conviction: 80 (HIGH)
```

---

## File Layout

### New Files
| File | Module | Purpose |
|---|---|---|
| `pipeline/spread_statistics.py` | Statistics | 5yr regime-tagged spread distributions |
| `pipeline/technical_scanner.py` | Technicals | RSI, DMA for all spread stocks |
| `pipeline/oi_scanner.py` | OI/PCR | Options positioning + anomaly detection |
| `pipeline/news_scanner.py` | News | RSS + corporate announcements |
| `pipeline/spread_intelligence.py` | Orchestrator | Combines all layers → recommendations |
| `pipeline/scripts/morning_scan.bat` | Scheduler | 9:25 AM trigger |
| `pipeline/scripts/intraday_scan.bat` | Scheduler | Every 15 min 9:40-15:25 |

### New Data Files (runtime)
| File | Updated | Contents |
|---|---|---|
| `data/spread_stats.json` | Weekly | Per-spread per-regime distributions |
| `data/today_regime.json` | Daily 9:00 | Today's regime + eligible spreads |
| `data/technicals.json` | Every 15 min | RSI, DMA for 22 stocks |
| `data/positioning.json` | Every 15 min | OI, PCR, anomaly flags |
| `data/news.json` | Every 15 min | RSS headlines, announcements |
| `data/recommendations.json` | Every 15 min | Ranked recommendations with scores |
| `data/oi_anomalies.json` | Append-only | Historical anomaly log |

### Existing Files Used (DO NOT MODIFY)
| File | Used for |
|---|---|
| `autoresearch/etf_optimal_weights.json` | Regime engine weights |
| `autoresearch/regime_trade_map.json` | Regime → spread mapping |
| `config.py` — `INDIA_SPREAD_PAIRS` | 11 spread definitions |
| `kite_client.py` | Live prices, OI, historical data |
| `run_eod_report.py` | EOD capture (already wired) |

---

## Scheduling (Windows Task Scheduler)

| Task Name | Time | Script | Notes |
|---|---|---|---|
| AnkaRegimeScan | 09:00 | regime_scanner.py | Pre-market regime |
| AnkaMorningScan | 09:25 | morning_scan.bat | Full 5-layer scan |
| AnkaIntraday0940 | 09:40 | intraday_scan.bat | First intraday |
| AnkaIntraday0955 | 09:55 | intraday_scan.bat | |
| ... | every 15 min | ... | |
| AnkaIntraday1525 | 15:25 | intraday_scan.bat | Last intraday |
| AnkaEOD1535 | 15:35 | eod_track_record.bat | Already exists |
| AnkaSpreadStats | Sunday 22:00 | spread_statistics.py | Weekly recompute |

---

## Data Sources

| Data | Source | Frequency | Cost |
|---|---|---|---|
| 5yr daily prices (22 stocks) | EODHD `.NSE` | Weekly recompute | Paid (existing) |
| Live intraday prices | Kite Connect LTP | Every 15 min | Paid (existing) |
| Options OI/PCR | Kite Connect quote() | Every 15 min | Paid (existing) |
| RSI/DMA | Computed from Kite historical | Every 15 min | No additional cost |
| Regime | autoresearch/ ETF engine | Daily | Free (existing) |
| News (RSS) | MoneyControl, ET, LiveMint | Every 15 min | Free |
| Announcements | indianapi.in | Every 15 min | Paid (existing) |
| Sector indices | Kite Connect (NIFTY IT, BANK, etc.) | Every 15 min | Paid (existing) |

---

## Scorecard Integration (Phase 2 — after 211 batch)

When trust scores are available for all F&O stocks:
- Trust score A/B on long side → BOOST +10
- Trust score D/F on short side → BOOST +10
- Trust score D/F on long side → CAUTION −10 (we're long a bad company)
- Trust score A/B on short side → CAUTION −10 (we're short a good company)

This is a modifier, not a gate. A spread can still be entered without scorecard data.

---

## Non-Goals (explicitly out of scope)

- Sector index futures (only BANKNIFTY/FINNIFTY exist, no Nifty IT/Defence/Pharma)
- Options strategies (futures spreads only)
- Automated order execution via Kite (recommendations only, manual execution)
- Real-time tick-by-tick data (15-min intervals are sufficient for multi-day spreads)
- Backtesting framework for new spread hypotheses (separate project, overnight autoresearch)

---

## Success Criteria

1. Morning scan fires at 9:25 AM every trading day with actionable recommendations
2. Intraday alerts fire within 15 min of a spread crossing entry/exit threshold
3. No false recommendations — every ENTER has regime gate + divergence gate + score ≥ 80
4. Historical spread statistics cover 5 years × 5 regimes × 11 spreads with statistical significance (min 30 days per regime per spread)
5. OI anomaly detection flags at least 1 genuine pre-news event per week (measured retroactively)
6. Zero hallucinated data — all numbers from EODHD/Kite/RSS, never fabricated
