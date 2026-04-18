# Golden Goose Architecture — Design Specification

> **Purpose:** Transform the Anka Research pipeline from a prototype with frozen
> components into a fully autonomous, self-validating, evidence-backed trading
> intelligence system capable of handling institutional-scale capital with zero
> emotional or operational slippage.

> **Audience:** This spec serves dual purpose:
> 1. Internal implementation blueprint (for Claude/developer sessions)
> 2. Client-facing transparency document (ships with the terminal product)

> **Date:** 2026-04-18
> **Status:** Approved (all 3 design sections approved by user)

---

## 1. Problem Statement

### Current State

The Anka Research pipeline has working individual components but critical gaps
prevent it from operating as a self-sustaining system:

| Component | Status | Impact |
|-----------|--------|--------|
| ETF Regime Engine | **FROZEN** — weights from Apr 8, regime from Apr 14 | Central brain stale; all downstream recommendations based on 4+ day old regime |
| Trust Score Coverage | **80.9%** — 174/215 scored, 41 stocks unscored | Backtest and shadow P&L only valid for partial universe |
| Feedback Loop | **MISSING** — signal outcomes don't feed back into scoring | System never learns from its own results |
| Portfolio Risk | **PARTIAL** — per-signal stops exist, no portfolio-level drawdown limit | No circuit breaker for cascading losses |
| Realized P&L | **MISSING** — no shadow trading, no forward test | No proof of alpha for investor deck or self-validation |
| Documentation Sync | **BROKEN** — docs, code, inventory frequently out of sync | Knowledge lost between sessions; same problems rediscovered daily |

### Target State

A system that:
1. Refreshes its own brain weekly (ETF reoptimization with Indian data)
2. Validates itself continuously (716-day backtest every Sunday)
3. Proves its edge in real-time (shadow P&L with transparent methodology)
4. Protects capital automatically (portfolio-level circuit breakers)
5. Documents every decision traceably (full data provenance)
6. Maintains knowledge across sessions (doc sync mandate)

---

## 2. Architecture Overview

### The 8-Layer Pipeline

```
Layer 1: ETF REGIME ENGINE (the brain)
  28 global ETFs + Indian market data → regime zone
  Weekly reoptimization (Saturday night)
  Daily signal computation (04:45)
        ↓
Layer 2: TRUST SCORES (management credibility)
  OPUS ANKA: 215 F&O stocks, grades A+ to F
  Batch re-scored when new transcripts available
        ↓
Layer 3: SPREAD INTELLIGENCE (pair selection)
  Regime-gated spreads with per-spread sizing multipliers
  Sized by Karpathy optimizer based on historical Sharpe
        ↓
Layer 4: REVERSE REGIME (stock selection)
  Phase A: Overnight playbook (gap/drift patterns)
  Phase B: Morning ranker (top 5 longs + 5 shorts)
  Phase C: Intraday correlation breaks (z-score detection)
        ↓
Layer 5: TECHNICALS + OI/PCR (confirmation)
  Chart patterns, breakouts, support/resistance
  Options open interest, put-call ratio, gamma bands
  Accentuate conviction (+/- points, never override regime)
        ↓
Layer 6: SIGNAL GENERATION (conviction scoring)
  Combine all layers → conviction score 0-100
  Trust score gates: block long on C or worse, block short on A/A+
  Signal enrichment: attach rigour trail from all sources
        ↓
Layer 7: SHADOW P&L (paper trading)
  Full simulation with stops/targets at real prices
  Every trade logged to closed_signals.json
  Daily visual track record (win/loss strip)
        ↓
Layer 8: TRACK RECORD + ACCEPTANCE GATE
  Forward test scorecard (weekly)
  Shadow P&L vs backtest confidence interval
  Must pass 5 criteria before live capital deployed
```

### The Weekend Cycle

```
Saturday 22:00 IST — ETF Reoptimization
  Inputs:  28 global ETFs + Indian close data + market technicals
  Method:  Karpathy random search (2000+ iterations)
  Output:  etf_optimal_weights.json + regime_trade_map.json (with sizing)

Sunday 00:00 IST — Unified Backtest (Statistical Referee)
  Inputs:  716 days of historical data + new weights
  Method:  Replay full 5-layer logic day by day
  Output:  backtest_results.json + backtest_summary.json
  Gate:    If new weights produce worse results → keep old weights

Daily 04:45 IST — Fresh Signal Computation
  Inputs:  Stored weights + today's ETF/Indian prices
  Output:  Fresh today_zone in regime_trade_map.json
```

### The Daily Cycle

```
04:30  AnkaDailyDump        → prices, fundamentals, FII flows
04:45  AnkaETFSignal         → fresh regime using stored weights
04:45  AnkaReverseRegimeProf → Phase A playbook refresh
04:45  AnkaDailyArticles     → research articles
07:30  AnkaMorningBrief      → Telegram briefing
09:00  AnkaRefreshKite       → broker session
09:16  AnkaOpenCapture       → opening prices
09:25  AnkaMorningScan       → regime + tech + OI + news + signals

09:30-15:30 (every 15 min):
       AnkaIntraday####      → re-scan all layers
       AnkaSignal####        → score signals, shadow execute, Telegram
       AnkaCorrelationBreaks → Phase C divergence detection
       AnkaWatchdogIntraday  → freshness monitoring

15:35  AnkaCloseCapture      → closing prices
16:00  AnkaEODReview         → P&L dashboard → Telegram
16:15  AnkaEODTrackRecord    → write track_record.json
16:20  AnkaEODNews           → backtest news predictions
16:30  AnkaWebExport         → push all data to website
16:30  AnkaDailyTrackRecord  → visual strip + scorecard update
16:45  AnkaWatchdogGate      → full system health check
```

---

## 3. Component Specifications

### 3.1 ETF Engine V2 — Live Brain

**New script:** `autoresearch/etf_reoptimize.py`

**Inputs (expanded from current 28 global ETFs):**

| Category | Inputs | Source |
|----------|--------|--------|
| Global ETFs (28) | Financials, tech, treasury, VIX, EM, commodities, currencies, etc. | yfinance |
| Indian close data | FII/DII net flows (Rs crore) | `data/flows/YYYY-MM-DD.json` |
| Indian close data | India VIX close | `data/daily/YYYY-MM-DD.json` |
| Indian close data | Nifty close, Bank Nifty close | `data/daily/YYYY-MM-DD.json` |
| Indian close data | Aggregate PCR | `data/positioning.json` |
| Market technicals | Nifty RSI (14-day) | Computed from daily prices |
| Market technicals | % F&O stocks above 200 DMA | Computed from daily prices |
| Market technicals | % F&O stocks above 50 DMA | Computed from daily prices |
| Market technicals | Sector breadth (sectors trending up vs down) | Computed from daily prices |

**Optimizer (Karpathy random search):**
- 2,000+ iterations of random weight perturbation
- Seed weights from correlation analysis
- 70/30 train-test split to prevent overfitting
- Optimizes TWO objectives simultaneously:
  1. **Regime accuracy:** Which weight mix best predicts next-week Nifty direction
  2. **Per-spread sizing:** For each regime zone, optimal allocation multiplier (0.5x-3x)
     per spread based on historical hit rate and Sharpe ratio

**Outputs:**
- `autoresearch/etf_optimal_weights.json` — weight vector + accuracy metrics + timestamp
- `autoresearch/regime_trade_map.json` — `today_zone` + per-regime spread definitions with
  sizing multipliers

**Safety: Weight Rollback Gate**
If new weights produce a LOWER backtest Sharpe than the previous weights (tested in
Sunday night backtest), the system:
1. Keeps the old weights
2. Logs a WARNING with comparison metrics
3. Sends Telegram alert: "Reoptimization produced worse weights — rollback applied"
4. Retries next Saturday with fresh data

**Scheduled task:** `AnkaETFReoptimize` — Saturday 22:00 IST
- Tier: critical
- Cadence: weekly
- Outputs: `autoresearch/etf_optimal_weights.json`, `autoresearch/regime_trade_map.json`

---

### 3.2 Daily Signal Computation

**Modified script:** `autoresearch/regime_to_trades.py`

**What changes:** Currently this script computes the regime AND the trade map. After
V2, the trade map (spread definitions + sizing) comes from the weekly optimizer.
This daily script only needs to:
1. Load stored weights from `etf_optimal_weights.json`
2. Fetch today's ETF prices + Indian close data via yfinance
3. Compute composite signal using stored weights
4. Map signal to regime zone (EUPHORIA/RISK-ON/NEUTRAL/CAUTION/RISK-OFF)
5. Write fresh `today_zone` into `regime_trade_map.json` (preserve spread definitions)

**Scheduled task:** `AnkaETFSignal` — daily 04:45 IST
- Tier: critical
- Cadence: daily
- Outputs: `autoresearch/regime_trade_map.json` (today_zone field updated)

---

### 3.3 Unified Backtest (Statistical Referee)

**New script:** `autoresearch/unified_backtest.py`

**What it does:** Replays the full 5-layer decision logic across 716+ days of
historical data using the current weights:

```
For each historical trading day (2023-04-01 to present):
  1. REGIME: Compute ETF composite signal → zone (using current weights)
  2. SPREADS: Which spreads eligible + what sizing (from current trade map)
  3. TECHNICALS: Did TA patterns confirm entry (from historical prices)
  4. OI/PCR: Did options flow confirm (from historical OI where available)
  5. NEWS: Was there a material event (from news_events_history.json)
  
  → Simulated entry at day's open (or signal time)
  → Apply trailing stop and target rules
  → Record P&L per trade
```

**Walk-forward integrity:** Each day's decision uses ONLY data available at that
time. No lookahead bias. Costs of 0.05% round-trip applied.

**Outputs:**
- `autoresearch/backtest_results.json`:
  ```json
  {
    "period": "2023-04-01 to 2026-04-18",
    "trading_days": 716,
    "total_trades": 1247,
    "win_rate": 0.63,
    "avg_return_per_trade": 0.008,
    "sharpe": 1.8,
    "max_drawdown": -0.12,
    "calmar": 2.1,
    "per_spread": {
      "Defence vs IT": {"trades": 89, "win_rate": 0.65, "sharpe": 1.4, "sizing": 2.0},
      "Pharma vs Banks": {"trades": 72, "win_rate": 0.58, "sharpe": 1.1, "sizing": 1.0}
    },
    "per_regime": {
      "RISK-ON": {"days": 210, "accuracy": 0.68, "avg_return": 0.012},
      "NEUTRAL": {"days": 285, "accuracy": 0.61, "avg_return": 0.006}
    },
    "confidence_interval_95": [0.004, 0.012],
    "weights_used": "etf_optimal_weights.json hash abc123",
    "computed_at": "2026-04-20T00:15:00+05:30"
  }
  ```
- `autoresearch/backtest_summary.json` — condensed version for display

**Weight Validation Gate:**
After backtest completes, compare new-weight Sharpe vs old-weight Sharpe:
- New >= Old: Deploy new weights (already written Saturday night)
- New < Old: Rollback to old weights, alert operator

**Scheduled task:** `AnkaUnifiedBacktest` — Sunday 00:00 IST
- Tier: critical
- Cadence: weekly
- Outputs: `autoresearch/backtest_results.json`, `autoresearch/backtest_summary.json`

---

### 3.4 Shadow P&L Engine

**Modified script:** `pipeline/run_signals.py` (extend shadow execution mode)

**Shadow execution flow:**
1. Signal generated (from spread intelligence, regime ranker, or correlation break)
2. Record entry price at signal time from Kite live feed (or yfinance if Kite unavailable)
3. Assign:
   - Stop-loss: Dynamic trailing stop based on ATR
   - Target: Based on backtest avg return for this spread × 1.5
   - Expiry: 5 trading days
   - Sizing: From regime_trade_map.json sizing multiplier
4. Every 15-min intraday cycle: update mark-to-market P&L
5. Close conditions:
   - Trailing stop breached → close, log loss with reason
   - Target hit → close, log gain with reason
   - Expiry reached → close at market, log with reason
6. Write to `data/signals/closed_signals.json` (same file website/Telegram already read)

**Signal metadata (stored with each trade):**
```json
{
  "signal_id": "SIG-2026-04-21-001",
  "type": "spread",
  "spread_name": "Defence vs IT",
  "direction": "LONG Defence / SHORT IT",
  "regime_at_entry": "RISK-ON",
  "regime_source": "etf_engine",
  "conviction": 72,
  "sizing_multiplier": 2.0,
  "entry_price": 1.32,
  "entry_time": "2026-04-21T09:30:00+05:30",
  "stop_loss": 1.28,
  "target": 1.38,
  "expiry": "2026-04-28",
  "confirmation": {
    "technical": "Defence RSI 42 (not overbought)",
    "oi_pcr": "Call buildup HAL/BEL, PCR 0.72 bullish",
    "news": "Defence budget allocation announced",
    "trust_score": "HAL=A, BEL=B+"
  },
  "backtest_context": {
    "similar_setups": 47,
    "historical_win_rate": 0.65,
    "historical_avg_return": 0.0103,
    "confidence_interval_95": [0.004, 0.018]
  },
  "close_price": null,
  "close_time": null,
  "close_reason": null,
  "pnl_pct": null
}
```

---

### 3.5 Daily Client Track Record

**Modified scripts:**
- `pipeline/website_exporter.py` — enhanced track_record.json with visual strip
- `pipeline/telegram_bot.py` — condensed daily strip in EOD message
- `pipeline/trust_score_terminal.py` — extended with track record view

**Track record format (written to `data/track_record.json`):**

```json
{
  "updated_at": "2026-04-21T16:30:00+05:30",
  "shadow_start_date": "2026-04-21",
  "trading_days": 15,
  "summary": {
    "total_trades": 42,
    "wins": 29,
    "losses": 13,
    "win_rate": 0.69,
    "avg_return": 0.009,
    "cumulative_return": 0.135,
    "max_drawdown": -0.021,
    "sharpe": 2.1,
    "calmar": 6.4
  },
  "daily_strip": [
    {"date": "2026-04-21", "pnl": 0.012, "result": "WIN", "trades": 3},
    {"date": "2026-04-22", "pnl": 0.008, "result": "WIN", "trades": 2},
    {"date": "2026-04-23", "pnl": -0.006, "result": "LOSS", "trades": 4}
  ],
  "weekly_scorecard": {
    "week_of": "2026-04-21",
    "shadow_pnl": 0.032,
    "backtest_prediction": 0.028,
    "confidence_interval": [0.015, 0.041],
    "within_ci": true,
    "regime_accuracy": 0.80,
    "best_spread": "Defence vs IT (+1.8%)",
    "worst_spread": "Coal vs OMCs (-0.6%)"
  },
  "backtest_baseline": {
    "period": "2023-04-01 to 2026-04-18",
    "trading_days": 716,
    "total_trades": 1247,
    "win_rate": 0.63,
    "sharpe": 1.8
  }
}
```

**Display formats:**

Website (askanka.com):
```
TRACK RECORD
🟩🟩🟥🟩🟩🟩🟥🟩🟩🟩🟩🟥🟩🟩🟩
Win: 80% | Avg: +0.9% | Sharpe: 2.1 | 15 days
```

Telegram EOD (16:00):
```
📊 ANKA DAILY SCORECARD
Today: 🟩 +1.2% (3 trades, 2 wins)
Week:  +3.2% (within backtest CI ✓)
Rolling 15d: 80% win rate | Sharpe 2.1
```

Terminal (full detail):
```
ANKA TRACK RECORD — SHADOW P&L
================================
Day  Date        P&L    Trades  Regime     Best Trade
 1   2026-04-21  +1.2%  3/2W    RISK-ON    Defence vs IT +1.8%
 2   2026-04-22  +0.8%  2/2W    RISK-ON    Pharma vs Banks +0.9%
 3   2026-04-23  -0.6%  4/1W    RISK-ON    Coal vs OMCs -1.2% (stopped)
...
Rolling: Win 80% | Avg +0.9% | Max DD -2.1% | Sharpe 2.1
Backtest: Win 63% | Avg +0.8% | Sharpe 1.8 (716 days)
Status: Shadow P&L WITHIN backtest CI ✓
```

---

### 3.6 Forward Test Scorecard

**New script:** `pipeline/forward_test_scorecard.py`

**Generated:** Sunday night, after unified backtest completes

**Content:**
```
ANKA RESEARCH — WEEKLY FORWARD TEST SCORECARD
================================================
Week ending: 2026-04-25
Regime this week: RISK-ON (5/5 days)

SHADOW P&L vs BACKTEST
  Shadow this week:     +3.2% (8 trades, 6 wins)
  Backtest prediction:  +2.8% [CI: +1.5% to +4.1%]
  Verdict:              ✓ WITHIN CI

REGIME ACCURACY
  Predicted direction:  UP on 4 days, FLAT on 1 day
  Actual Nifty:         UP on 4 days, DOWN on 1 day
  Accuracy:             80% (4/5)

PER-SPREAD PERFORMANCE
  Defence vs IT:        +1.8% (sized 2.0x) — 65% backtest hit rate
  Pharma vs Banks:      +0.9% (sized 1.0x) — 58% backtest hit rate
  Coal vs OMCs:         -0.6% (sized 0.5x) — 51% backtest hit rate ← review sizing

WEIGHT CHANGES (from reoptimization)
  Financials:           +0.39 → +0.41 (+0.02)
  Treasury:             +0.25 → +0.23 (-0.02)
  FII flows (NEW):      +0.15 (newly significant)

DATA QUALITY
  Trust scores:         207/215 (96.3%)
  Regime stability:     5 consecutive days (stable)
  OI data coverage:     98% (2 stocks missing Kite data)
  Watchdog issues:      0 critical, 1 warn (AnkaSignal0942 stale result)

ACCEPTANCE GATE STATUS
  ☑ Shadow trading > 15 days
  ☑ Win rate > 55% (currently 80%)
  ☑ Sharpe > 1.0 (currently 2.1)
  ☑ No circuit breaker triggered
  ☑ Shadow P&L within CI for 2 consecutive weeks
  STATUS: ALL CRITERIA MET — eligible for live capital
```

**Distributed to:**
- `data/forward_test_scorecard.json` (website)
- Telegram weekly message (Sunday night)
- Terminal display

---

### 3.7 Risk Guardrails

**New script:** `pipeline/risk_guardrails.py`

**Portfolio-Level Circuit Breaker:**

| Trigger | Action | Alert |
|---------|--------|-------|
| Cumulative P&L < -10% over rolling 20 days | Reduce ALL new position sizes by 50% | Telegram: "CIRCUIT BREAKER L1: reducing exposure" |
| Cumulative P&L < -15% over rolling 20 days | Pause ALL new entries (hold existing, let stops work) | Telegram: "CIRCUIT BREAKER L2: pausing new entries" |
| 3 consecutive weeks shadow P&L outside backtest CI | Flag model drift, trigger early reoptimization | Telegram: "MODEL DRIFT: shadow diverging from backtest" |

**Per-Signal Risk Limits:**

| Rule | Limit | Enforcement |
|------|-------|-------------|
| Max concurrent open signals | 10 | New signals queued if at limit |
| Max sizing multiplier per signal | 3.0x | Capped by optimizer |
| Max exposure per single sector | 4 signals | New same-sector signals blocked |
| Trailing stop | Dynamic (ATR-based) | Applied at signal creation |
| Max hold period | 5 trading days | Forced close at expiry |
| Min conviction for entry | 50/100 | Below threshold → signal logged but not executed |

**Implementation:** `risk_guardrails.py` is called by `run_signals.py` before any
shadow execution. It returns `(allowed: bool, reason: str, adjusted_size: float)`.

---

### 3.8 Acceptance Gate for Live Capital

Before transitioning from Layer 7 (shadow) to Layer 8 (live execution):

| Criterion | Threshold | Measured Over |
|-----------|-----------|--------------|
| Shadow trading days | >= 15 | Continuous |
| Win rate | > 55% | Rolling 15 days |
| Sharpe ratio | > 1.0 | Rolling 15 days |
| Circuit breaker | Not triggered | During entire shadow window |
| Backtest CI alignment | Shadow within CI | 2 consecutive weeks |

**ALL 5 criteria must be met simultaneously.** If any criterion fails, the counter
resets and the 15-day window restarts.

---

## 4. Data Provenance (Client-Facing)

This section ships with the terminal as `docs/DATA_PROVENANCE.md`:

### Data Sources

| Data | Source | Update Frequency | History |
|------|--------|-----------------|---------|
| Indian stock prices | EODHD API (primary), yfinance (fallback), Kite API (live) | Daily + 15-min intraday | 2023-04-01 to present |
| Global ETF prices | yfinance | Daily | 2023-04-01 to present |
| FII/DII flows | NSE public endpoint | Daily | 2023-04-01 to present |
| Options OI/PCR | Zerodha Kite API | Every 15 min (market hours) | Limited history |
| News events | Multiple news APIs | Continuous | 2024-01-01 to present |
| Annual reports | BSE/NSE filings (PDFs) | Annual per company | 3-5 years per stock |
| Earnings transcripts | BSE/NSE/company websites | Quarterly per company | 8+ quarters per stock |
| Trust scores | OPUS ANKA engine (Gemini 2.5 Flash) | Batch-computed | 174/215 stocks scored |

### Methodology

**Regime Detection:**
- 28 global ETFs + 8 Indian market indicators combined via ML-optimized weights
- Karpathy random search: 2,000 iterations, 70/30 train-test split
- Directional accuracy: 62.3% (vs 51.6% random baseline)
- Reoptimized weekly (Saturday night)
- Validated against 716-day historical backtest (Sunday night)

**Trust Scores:**
- 12-step forensic pipeline per company
- Sources: Annual reports, earnings call transcripts, shareholding patterns
- Scoring: Management guidance extraction → promise vs delivery verification
- Grades: A+ (highest credibility) to F (lowest)
- Gate rules: Cannot long C or worse; cannot short A or A+

**Signal Generation:**
- 5-layer confirmation: Regime + Spread Z-score + Technicals + OI/PCR + News
- Conviction scoring: 0-100 scale with hard-block trust gates
- Position sizing: Karpathy-optimized per-spread multipliers (0.5x to 3.0x)

**Backtest:**
- Period: 716+ trading days (2023-04-01 to present)
- Walk-forward: No lookahead bias
- Costs: 0.05% round-trip (brokerage + STT + slippage estimate)
- Stops: Trailing stop (ATR-based) applied to all positions
- Regime: 2-day hysteresis to prevent whipsaw

**Shadow P&L:**
- Paper execution at actual signal prices (Kite live feed)
- Same stop/target/expiry rules as live trading
- Every trade logged with full metadata and backtest context
- Daily visual track record published to website and Telegram

---

## 5. New Scheduled Tasks

| Task Name | Time (IST) | Day | Script | Tier | Outputs |
|-----------|-----------|-----|--------|------|---------|
| AnkaETFReoptimize | 22:00 | Saturday | `autoresearch/etf_reoptimize.py` | critical | `etf_optimal_weights.json`, `regime_trade_map.json` |
| AnkaUnifiedBacktest | 00:00 | Sunday | `autoresearch/unified_backtest.py` | critical | `backtest_results.json`, `backtest_summary.json` |
| AnkaETFSignal | 04:45 | Daily | `autoresearch/regime_to_trades.py` | critical | `regime_trade_map.json` (today_zone updated) |
| AnkaForwardScorecard | 01:00 | Sunday | `pipeline/forward_test_scorecard.py` | warn | `data/forward_test_scorecard.json` |
| AnkaDailyTrackRecord | 16:30 | Daily | `pipeline/daily_track_record.py` | warn | `data/track_record.json` (visual strip updated) |

All tasks MUST be added to `pipeline/config/anka_inventory.json` before deployment.

---

## 6. New Files

| File | Type | Purpose |
|------|------|---------|
| `autoresearch/etf_reoptimize.py` | Script | Weekly ETF weight optimization with Indian data |
| `autoresearch/unified_backtest.py` | Script | 716-day historical replay with 5-layer logic |
| `pipeline/forward_test_scorecard.py` | Script | Weekly scorecard generation |
| `pipeline/daily_track_record.py` | Script | Daily visual strip update |
| `pipeline/risk_guardrails.py` | Script | Portfolio circuit breaker + per-signal limits |
| `docs/DATA_PROVENANCE.md` | Doc | Client-facing data sources and methodology |
| `autoresearch/backtest_results.json` | Data | Full trade log from backtest |
| `autoresearch/backtest_summary.json` | Data | Condensed backtest metrics |
| `data/forward_test_scorecard.json` | Data | Weekly scorecard for website |

### Modified Files

| File | Change |
|------|--------|
| `autoresearch/regime_to_trades.py` | Add daily signal computation using stored weights |
| `pipeline/run_signals.py` | Add shadow execution mode with full metadata logging |
| `pipeline/website_exporter.py` | Enhanced track_record.json with daily strip + backtest baseline |
| `pipeline/telegram_bot.py` | Add daily scorecard + weekly scorecard message formats |
| `pipeline/trust_score_terminal.py` | Add track record view |
| `pipeline/config/anka_inventory.json` | Add 5 new tasks |
| `docs/SYSTEM_OPERATIONS_MANUAL.md` | Update with new tasks, data flows, and architecture |
| `CLAUDE.md` | Already updated with architecture summary + doc sync mandate |

---

## 7. Implementation Sequence (Approach 1: Layered Build)

### Week 0 (Parallel): Data Hardening
- Score remaining 29 stocks (batch running as of 2026-04-18)
- Collect PDFs for LT, M&M, MCX and score them
- Target: 207+/215 scored (96%+ coverage)

### Week 1: Live Brain
- Build `etf_reoptimize.py` with Indian data inputs
- Modify `regime_to_trades.py` for daily signal computation
- Schedule AnkaETFReoptimize (Saturday) + AnkaETFSignal (daily)
- First Saturday run: validate weights improve over frozen baseline
- Update operations manual + inventory

### Week 2: Unified Backtest
- Build `unified_backtest.py` with walk-forward replay
- Build weight rollback gate
- Schedule AnkaUnifiedBacktest (Sunday)
- First Sunday run: validate 716-day backtest produces meaningful results
- Update operations manual + inventory

### Week 3: Shadow P&L + Track Record
- Extend `run_signals.py` with shadow execution + full metadata
- Build `daily_track_record.py` for visual strip
- Build `forward_test_scorecard.py` for weekly report
- Schedule AnkaDailyTrackRecord + AnkaForwardScorecard
- Write `docs/DATA_PROVENANCE.md` (client-facing)
- Update operations manual + inventory

### Week 4: Risk Guardrails
- Build `risk_guardrails.py` with circuit breakers
- Wire into `run_signals.py` (called before shadow execution)
- Add acceptance gate logic
- Update operations manual + inventory

### Week 5-6: Forward Test Window
- Shadow P&L accumulates for 15 trading days
- Weekly scorecards validate against backtest CI
- Monitor for circuit breaker triggers
- Acceptance gate evaluation at end of Week 6

### Week 7+: Live Capital Decision
- If ALL 5 acceptance criteria met: eligible for Layer 8 (Kite execution)
- If any criterion fails: extend shadow window, investigate

---

## 8. Documentation Sync Rule

**CRITICAL:** Every code change in this project MUST update ALL of these in the
SAME commit:

1. The code itself
2. `docs/SYSTEM_OPERATIONS_MANUAL.md` — the canonical system reference
3. `pipeline/config/anka_inventory.json` — if a scheduled task was added/changed
4. `CLAUDE.md` — if the architecture or schedule changed
5. Memory files — if a design decision was made

**Rationale:** The #1 recurring failure mode is knowledge loss between sessions.
Docs say one thing, code does another, inventory is out of date. This rule ensures
a single source of truth that every session can rely on.

---

## 9. Success Criteria

| Criterion | Target | Measured By |
|-----------|--------|-------------|
| Trust score coverage | >= 96% (207/215) | `trust_score_terminal.py` |
| ETF regime freshness | Updated daily by 05:00 | Watchdog file freshness |
| Backtest runs weekly | Every Sunday, no failures | Watchdog task liveness |
| Shadow P&L active | >= 15 trading days | `track_record.json` |
| Win rate | > 55% | Rolling 15-day track record |
| Sharpe ratio | > 1.0 | Rolling 15-day track record |
| Circuit breaker | Not triggered | `risk_guardrails.py` log |
| Shadow within backtest CI | 2 consecutive weeks | Weekly scorecard |
| Documentation sync | 100% | Every commit updates all docs |
| Watchdog issues | 0 critical tier | Daily gate run |

---

*Spec version: 1.0 | Created: 2026-04-18 | Author: Bharat Ankaraju + Claude*
