# Anka Research — System Operations Manual

> **What this document is:** A plain-English explanation of the entire Anka Research
> algorithmic trading system — what it does, how the pieces connect, what runs when,
> and what keeps it healthy. Written so anyone can understand it without touching code.

---

## 1. What Is Anka Research?

Anka Research is an **automated trading intelligence system** for the Indian stock market.
It watches 213 stocks in the F&O (Futures & Options) segment of NSE.

Every day, the system:
- Figures out what kind of market we're in (regime detection)
- Scores how trustworthy each company's management is (trust scores)
- Reads news and detects unusual options activity (news + OI scanning)
- Finds pairs of stocks where one is cheap and the other expensive (spread intelligence)
- Generates trade recommendations with conviction scores (signals)
- Tracks whether those recommendations worked (track record)

All of this runs automatically on a Windows PC via scheduled tasks. The outputs go to:
- **Telegram** — real-time alerts during market hours
- **Website** (askanka.com) — public-facing marketing page
- **Terminal** — detailed dashboard for the operator (you)

---

## 2. The System Diagram

```
                        ANKA RESEARCH — COMPLETE SYSTEM FLOW
                        ====================================

    OVERNIGHT (04:30 IST)                    PRE-MARKET (07:30-09:25 IST)
    =====================                    ============================

    +------------------+                     +-------------------+
    | AnkaDailyDump    |                     | AnkaMorningBrief  |
    | (04:30)          |                     | (07:30)           |
    |                  |                     |                   |
    | Fetches:         |                     | Reads:            |
    | - US close       |                     | - Asian corr data |
    | - Commodities    |                     | Sends:            |
    | - Currencies     |                     | - Telegram brief  |
    | - FII/DII flows  |                     +-------------------+
    |                  |                              |
    | Writes:          |                              v
    | daily_prices     |                     +-------------------+
    | fundamentals     |                     | AnkaRefreshKite   |
    | fii_flows        |                     | (09:00)           |
    +--------+---------+                     | Refreshes broker  |
             |                               | API session       |
             v                               +-------------------+
    +------------------+                              |
    | AnkaReverseRegime|                              v
    | Profile (04:45)  |                     +-------------------+
    |                  |                     | AnkaOpenCapture   |
    | Reads:           |                     | (09:16)           |
    | - 3yr historical |                     | Captures today's  |
    | - ETF weights    |                     | opening prices    |
    |                  |                     +-------------------+
    | Writes:          |                              |
    | reverse_regime   |                              v
    | _profile.json    |  +----------> +============================+
    +------------------+  |            | AnkaMorningScan (09:25)    |
                          |            | THE CENTRAL MORNING ENGINE |
    +------------------+  |            |                            |
    | AnkaDailyArticles|  |            | 7 sequential steps:        |
    | (04:45)          |  |            |                            |
    | Generates daily  |  |            | 1. regime_scanner.py       |
    | research articles|  |            |    VIX -> regime zone      |
    +------------------+  |            |    (EUPHORIA/RISK-ON/      |
                          |            |     NEUTRAL/CAUTION/       |
                          |            |     RISK-OFF)              |
                          |            |                            |
    FILES FROM OVERNIGHT--+            | 2. technical_scanner.py    |
    feed into morning                  |    chart patterns,         |
    scan as inputs                     |    breakouts, S/R          |
                                       |                            |
                                       | 3. oi_scanner.py           |
                                       |    options OI, PCR,        |
                                       |    gamma bands             |
                                       |                            |
                                       | 4. news_scanner.py         |
                                       |    corp announcements,     |
                                       |    global events           |
                                       |                            |
                                       | 5. news_intelligence.py    |
                                       |    classify news impact    |
                                       |                            |
                                       | 6. spread_intelligence.py  |
                                       |    which pairs to trade    |
                                       |    today (regime-gated)    |
                                       |                            |
                                       | 7. reverse_regime_ranker   |
                                       |    top 5 longs + 5 shorts |
                                       +============================+
                                                    |
                        +---------------------------+---------------------------+
                        |                           |                           |
                        v                           v                           v
               today_regime.json          recommendations.json      regime_ranker_state.json
               technicals.json            (spread signals)           (stock signals)
               positioning.json
               news.json


    MARKET HOURS (09:30-15:30, every 15 min)
    =========================================

    +=======================================+
    |  INTRADAY LOOP (25 cycles per day)    |
    |                                       |
    |  AnkaIntraday#### runs:               |
    |  - Re-scan technicals                 |
    |  - Re-scan OI/PCR                     |
    |  - Re-scan news                       |
    |  - Update spread signals              |
    |  - Detect correlation breaks          |
    |    (Phase C: stock doing opposite     |
    |     of what regime predicts)          |
    |                                       |
    |  AnkaSignal#### runs:                 |
    |  - Score each signal (conviction)     |
    |  - Apply trust score gates            |
    |  - Send alerts to Telegram            |
    |  - Track open positions               |
    +=======================================+
              |                    |
              v                    v
     open_signals.json    Telegram alerts
     closed_signals.json


    POST-CLOSE (15:30-16:45 IST)
    =============================

    +------------------+    +------------------+    +------------------+
    | AnkaCloseCapture |    | AnkaEODReview    |    | AnkaEODTrackRec  |
    | (15:35)          |    | (16:00)          |    | (16:15)          |
    |                  |    |                  |    |                  |
    | Captures closing |    | Dashboard of     |    | Official P&L     |
    | prices for all   |--->| today's signals  |--->| calculation      |
    | 213 stocks       |    | win/loss/open    |    | Writes track     |
    |                  |    | Sends to Telegram|    | record JSON      |
    +------------------+    +------------------+    +------------------+
                                                             |
                                                             v
    +------------------+                            track_record.json
    | AnkaEODNews      |                            (feeds website +
    | (16:20)          |                             next day)
    |                  |
    | Backtest today's |    +------------------+
    | news events:     |    | AnkaWebExport    |
    | did the stock    |    | (16:30)          |
    | move as expected?|    |                  |
    |                  |    | Export all data   |
    | Writes:          |    | to website JSONs |
    | news_verdicts    |    | for askanka.com  |
    +------------------+    +------------------+


    OVERNIGHT AGAIN (04:30 IST next day)
    =====================================
    The cycle repeats. Yesterday's track_record.json,
    news_verdicts.json, and regime state carry forward
    as inputs to the next morning scan.
```

---

## 3. The Data Chain — What Feeds What

Think of the system as a factory assembly line. Each station takes inputs from the
previous station and produces outputs for the next one.

### Station 1: Raw Data Collection (AnkaDailyDump, 04:30)

**What it does:** Fetches yesterday's closing data from the rest of the world.

| Data | Source | File Written |
|------|--------|-------------|
| US market close (S&P, NASDAQ, etc.) | EODHD API / yfinance | `data/daily/YYYY-MM-DD.json` |
| Commodities (crude oil, gold) | EODHD API / yfinance | same file |
| Currency rates (USD/INR) | EODHD API / yfinance | same file |
| Indian stock fundamentals | yfinance | `data/daily/YYYY-MM-DD_fundamentals.json` |
| FII/DII fund flows | NSE public endpoint | `data/flows/YYYY-MM-DD.json` |

**Why it matters:** This is the raw material. If the daily dump fails, everything
downstream runs on stale data. The watchdog flags this as CRITICAL.

### Station 2: Regime Determination — The ETF Engine + Morning Scan

**What it does:** Answers the question: "What kind of market are we in today?"

**This is a TWO-STEP process with a critical gap:**

#### Step 2a: ETF Weight Optimizer (OFFLINE — runs manually, NOT scheduled)

The foundation. Uses 28 global ETFs (US sectors, emerging markets, commodities,
bonds, currencies) to build a composite signal that predicts next-day Nifty direction
with 62.3% accuracy (vs 51.6% random).

**How it works:**
- Takes daily returns of 28 ETFs (financials, innovation, treasury, VIX, developed
  markets, bonds, euro, Japan, S&P 500, India ETF, China, emerging markets, etc.)
- Runs 2,000 random weight combinations to find the mix that best predicts Nifty
- Optimizes by Sharpe ratio (risk-adjusted return)
- Top weights: Financials (+0.39), Innovation (+0.31), Treasury (+0.25), VIX (-0.20)
- Outputs a single composite number → maps to regime zone

**Output:** `autoresearch/etf_optimal_weights.json`

**STATUS: SCHEDULED. AnkaETFReoptimize runs Saturday 22:00 IST (weekly).
Now includes Indian data: FII flows, India VIX, Nifty close, PCR.
Deployed 2026-04-18 as part of Golden Goose Plan 1.**

#### Step 2b: Regime Trade Map Builder (OFFLINE — runs manually, NOT scheduled)

Takes the ETF regime zones and backtests which spread trades work in each zone.

**Output:** `autoresearch/regime_trade_map.json` — contains `today_zone` (the ETF
engine's regime call) and a mapping of spreads per regime.

**STATUS: SCHEDULED. AnkaETFSignal runs daily 04:45 IST (after daily dump at 04:30).
Applies stored weights to fresh ETF + Indian data to compute today's zone.
Deployed 2026-04-18 as part of Golden Goose Plan 1.**

#### Step 2c: Morning Regime Scanner (09:25 daily — SCHEDULED, runs daily)

**This is what actually runs every morning.** It reads the trade map and applies
hysteresis.

**Inputs:**
- `regime_trade_map.json` → reads `today_zone` as the PRIMARY regime (from ETF engine)
- MSI (5-input heuristic: VIX + crude + USD/INR + Nifty + FII flows) as SECONDARY context
- `data/prev_regime.json` → yesterday's regime for hysteresis

**The problem:** The morning scanner reads `today_zone` from `regime_trade_map.json`,
but that file was last computed on April 14. So every morning since then, the system
has been using April 14's regime determination. The MSI runs live but only provides
context — it does NOT override the ETF regime.

**Regime zones:**
- EUPHORIA (markets too calm, reversal risk)
- RISK-ON (bullish)
- NEUTRAL (no clear direction)
- CAUTION (defensive)
- RISK-OFF (crisis mode)

**Safety feature:** 2-day hysteresis. The regime doesn't flip on a single day.
It needs 2 consecutive days in a new zone before it officially changes.
This prevents whipsawing.

**Output:** `data/today_regime.json` — the single most important file in the system.
Everything downstream reads this to decide what to recommend.

### Station 3: Regime-to-Trades Mapping

**What it does:** Given today's regime, which spread trades are eligible?

**Inputs:**
- `data/today_regime.json` (from Station 2c)
- `autoresearch/regime_trade_map.json` (FROZEN reference: which spreads work in which regime)
- `autoresearch/reverse_regime_profile.json` (from overnight Phase A: historical gap/drift patterns)

**Logic:**
- In RISK-ON: favour long-biased spreads (e.g., LONG defence vs SHORT IT)
- In RISK-OFF: favour short-biased spreads (e.g., LONG pharma vs SHORT realty)
- In NEUTRAL: focus on mean-reversion spreads (pairs that stretched too far)

**Key file:** `regime_trade_map.json` is a FROZEN file. It was last computed on
April 14, 2026 and defines which spreads belong to which regime. It does NOT update
daily or weekly. This is the single biggest gap in the system — the central brain
is not refreshing.

### Station 4: Technicals + OI + News (Morning Scan Steps 2-5, 09:25)

**What it does:** Three independent scanners run in parallel to gather confirming evidence.

| Scanner | What it reads | What it produces |
|---------|--------------|-----------------|
| `technical_scanner.py` | Price history | Chart patterns, breakouts, support/resistance levels |
| `oi_scanner.py` | Kite API (Zerodha) | Options open interest, put-call ratio, gamma bands |
| `news_scanner.py` | News APIs | Corporate announcements, global events |
| `news_intelligence.py` | News + history | Impact classification (high/medium/low) |

**Output files:**
- `data/technicals.json`
- `data/positioning.json`
- `data/oi_anomalies.json`
- `data/news.json`

### Station 5: Signal Generation (Morning Scan Steps 6-7, 09:25)

**What it does:** Combines everything into actual trade recommendations.

**Spread Intelligence** (`spread_intelligence.py`):
1. Load yesterday's active spreads from `data/recommendations.json`
2. Check each spread against today's regime — is it still eligible?
3. Check the Z-score — has the spread stretched far enough from its mean?
4. Apply modifiers from technicals, OI, and news
5. Score each spread → action (ENTER / HOLD / EXIT) + conviction (1-5)

**Reverse Regime Ranker** (`reverse_regime_ranker.py`):
1. Load overnight regime profile (which stocks drift up/down in each regime)
2. If regime changed: rank stocks by expected drift → top 5 longs + 5 shorts
3. If regime same: hold existing positions

**Output:**
- `data/recommendations.json` — spread trade signals
- `data/regime_ranker_state.json` — individual stock signals

### Station 6: Conviction Scoring and Signal Gating

**What it does:** Before any signal reaches Telegram, it passes through gates.

**Gate 1 — Trust Score:** If you're going LONG a stock with a trust grade of C or
worse (management can't be trusted), the signal is BLOCKED. If you're going SHORT a
stock with trust grade A or A+ (management is excellent), the signal is BLOCKED.

**Gate 2 — OI Confirmation:** Does the options flow confirm the direction? Call buildup
on a long signal = bonus conviction. Put buildup on a long signal = penalty.

**Gate 3 — Correlation Break:** Is the stock doing the OPPOSITE of what the regime
predicts? These are the highest-conviction signals (something unusual is happening).

**Output:** Each signal gets a conviction score (0-100). Only signals above a threshold
get sent to Telegram.

### Station 7: Intraday Tracking (09:30-15:30)

**What it does:** Every 15 minutes during market hours, the system:
1. Re-runs all scanners with live data
2. Checks if existing signals hit their targets or stop-losses
3. Detects new correlation breaks (Phase C)
4. Sends updates to Telegram

**Files updated every 15 min:**
- `data/open_signals.json` — currently active signals
- `data/closed_signals.json` — signals that hit target/stop today

### Station 8: Post-Close Processing (15:30-16:45)

**What it does:** End-of-day wrap-up.

| Time | Task | Purpose |
|------|------|---------|
| 15:35 | AnkaCloseCapture | Capture official closing prices |
| 16:00 | AnkaEODReview | Dashboard: wins/losses/open positions → Telegram |
| 16:15 | AnkaEODTrackRecord | Calculate P&L, write `track_record.json` |
| 16:20 | AnkaEODNews | Backtest news events: did the stock react as expected? |
| 16:30 | AnkaWebExport | Push all data to website JSON files |

**What carries forward to tomorrow:**
- `data/track_record.json` — cumulative performance history
- `data/news_verdicts.json` — which news predictions were correct
- `data/prev_regime.json` — today's regime (for hysteresis)
- `data/regime_ranker_state.json` — active stock positions
- `data/recommendations.json` — active spread positions

---

## 3b. The Reverse Regime Engine — How Stock Picks Are Made

The "reverse regime" engine is a 3-phase system that turns regime changes into
specific stock picks. It's called "reverse" because instead of predicting the
regime from stocks, it predicts stock behaviour FROM the regime.

### Phase A — Build the Playbook (overnight, 04:45)

**Script:** `autoresearch/reverse_regime_analysis.py`
**Scheduled:** Yes — runs daily via AnkaReverseRegimeProfile

Goes through 3+ years of history and finds every date where the regime changed
(e.g., NEUTRAL to RISK-OFF). For each date and each of the 213 F&O stocks, it
measures:

- **Gap:** How much did the stock jump at the open? (overnight reaction)
- **Drift 1d/3d/5d:** How much did it move over the next 1, 3, and 5 days?
- **Tradeable?** Did the 5-day drift outweigh the gap? (is there post-gap alpha?)
- **Persistent?** Did the drift continue in the gap's direction? (momentum)
- **Hit rate:** What % of the time was a long trade profitable?

Example: "When regime shifts NEUTRAL to RISK-OFF, HDFCBANK has drifted -2.3% over
5 days in 18 out of 23 episodes (78% hit rate)."

**Output:** `autoresearch/reverse_regime_profile.json` — the complete playbook.

### Phase B — Pick Today's Trades (morning, 09:25)

**Script:** `autoresearch/reverse_regime_ranker.py`
**Scheduled:** Yes — runs as part of AnkaMorningScan

Every morning, checks: did the regime change since yesterday?

- **No change:** Hold existing positions. Do nothing.
- **Regime changed:** Open the playbook. Rank all stocks by expected 5-day drift
  in the NEW regime. Pick top 5 longs + top 5 shorts. Filter by hit rate (>55%)
  and minimum episodes (>10). Positions expire after 5 trading days.

Confidence levels:
- HIGH: 20+ episodes, 65%+ hit rate
- MEDIUM: 10+ episodes, 55%+ hit rate
- LOW: filtered out

**Output:** `data/regime_ranker_state.json`

### Phase C — Intraday Correlation Breaks (every 15 min)

**Script:** `autoresearch/reverse_regime_breaks.py`
**Scheduled:** Yes — runs via AnkaCorrelationBreaks every 15 min

During the day, watches for stocks doing the OPPOSITE of what the playbook predicts.

- Computes z-score: (actual return - expected return) / historical volatility
- Breaks trigger when |z-score| > 1.5 standard deviations
- Cross-references with OI/PCR data for confirmation

Decision matrix:
- Stock dropping + put buildup heavy → CONFIRMED WARNING (exit/reduce)
- Stock dropping + call buildup heavy → POSSIBLE OPPORTUNITY (someone buying the dip)
- Stock rising against expectations + call buildup → CONFIRMED OPPORTUNITY (add)

**Output:** `data/correlation_breaks.json`

### How Phases Connect

```
Phase A (overnight)     Phase B (morning)       Phase C (intraday)
==================      =================       ==================
3yr history             Did regime change?      Is stock behaving
    ↓                        |                  as expected?
Build playbook          YES → rank stocks            |
of what happens              ↓                  NO → correlation
at each regime          Top 5 long              break detected
transition              Top 5 short                  ↓
    ↓                        ↓                  Cross-check with
reverse_regime          regime_ranker           OI/PCR data
_profile.json           _state.json                  ↓
                                                correlation
                                                _breaks.json
```

---

## 4. The Watchdog — What It Is and Why It Exists

### The Problem It Solves

The system has 71 scheduled tasks running on Windows Task Scheduler. Any one of them
can silently fail — the script crashes, a file path is wrong, an API key expires, the
PC was asleep. When a task fails silently, the data it produces goes stale. Everything
downstream then runs on old data, producing wrong recommendations. You wouldn't know
until you manually check.

### What the Watchdog Does

The watchdog (`pipeline/watchdog.py`) is an automated health monitor. It runs on its
own schedule and checks three things:

**Check 1 — File Freshness:**
For each task in the inventory, the watchdog looks at the output file that task should
produce. Is the file fresh enough?

Example: `AnkaIntraday0930` should produce `data/technicals.json`. If it's 3 hours old
and the task runs every 15 minutes, something is wrong. The watchdog raises an
`OUTPUT_STALE` alert.

**Check 2 — Task Liveness:**
The watchdog asks Windows Task Scheduler: "Did this task actually run recently? What was
the exit code?" If a task hasn't run in 2x its expected interval, or if it ran but
returned an error code, the watchdog raises a `TASK_STALE_RUN` or `TASK_STALE_RESULT`
alert.

**Check 3 — Drift Detection:**
The watchdog compares the inventory (what SHOULD exist) against the live scheduler
(what DOES exist):
- **Orphan tasks:** In the scheduler but not in the inventory. Someone added a task
  manually without registering it.
- **Ghost tasks:** In the inventory but not in the scheduler. A task was deleted from
  the scheduler but the inventory still expects it.

### The Inventory File

`pipeline/config/anka_inventory.json` is the watchdog's source of truth. Every task
is registered with:

| Field | Meaning |
|-------|---------|
| `task_name` | Exact name in Windows Task Scheduler |
| `tier` | `critical` / `warn` / `info` — determines alert urgency |
| `cadence_class` | `intraday` / `daily` / `weekly` — how often it runs |
| `outputs` | List of files this task should produce |
| `grace_multiplier` | How much staleness slack to allow (e.g., 2.0 = twice the expected interval) |

### How Alerts Work

When the watchdog finds issues:
1. It builds a digest (summary of all problems)
2. It checks a state file (`data/watchdog_state.json`) — has this issue been reported before?
3. New issues get sent to Telegram immediately
4. Repeat issues are suppressed (you only get alerted once per issue)
5. When an issue resolves, you get a "RESOLVED" notification

### Watchdog Schedule

| Time | Mode | What it checks |
|------|------|---------------|
| 04:45 | Gate run (`--all`) | ALL tasks + drift detection |
| 09:30-15:30 (every 15 min) | Intraday (`--tier critical`) | Critical tasks only |
| 16:45 | Gate run (`--all`) | ALL tasks + drift detection |

---

## 5. Complete Schedule — Every Task, Every Time

### Overnight Batch (no market)

| Time (IST) | Task Name | What It Does | Critical? |
|------------|-----------|-------------|-----------|
| 04:30 | AnkaDailyDump | Fetch global prices, fundamentals, FII flows | CRITICAL |
| 04:45 | AnkaETFSignal | Compute daily regime zone from stored ETF weights | CRITICAL |
| 04:45 | AnkaReverseRegimeProfile | Compute regime transition patterns (Phase A) | CRITICAL |
| 04:45 | AnkaDailyArticles | Generate research articles | warn |
| 04:45 | AnkaWatchdogGate | Watchdog gate run — check everything | warn |

### Pre-Market

| Time (IST) | Task Name | What It Does | Critical? |
|------------|-----------|-------------|-----------|
| 07:15 | AnkaCorrelationScan | Asian market correlation check | info |
| 07:30 | AnkaMorningBrief0730 | Morning briefing → Telegram | warn |
| 08:30 | AnkaGapPredictor | Overnight gap risk analysis | info |
| 09:00 | AnkaRefreshKite | Refresh Zerodha broker session | CRITICAL |
| 09:16 | AnkaOpenCapture | Capture today's opening prices | CRITICAL |
| 09:25 | AnkaMorningScan | THE BIG ONE — regime + tech + OI + news + signals | CRITICAL |

### Market Hours (09:30-15:30)

Every 15 minutes, two tasks run as a pair:

| Task Pattern | What It Does |
|-------------|-------------|
| AnkaIntraday#### | Re-scan technicals, OI, news, spreads, correlation breaks |
| AnkaSignal#### | Score signals, apply gates, send Telegram alerts |
| AnkaWatchdogIntraday | (every 15 min) Check critical task freshness |
| AnkaCorrelationBreaks | (every 15 min) Phase C: detect regime-stock divergence |

That's 25 intraday cycles x 4 tasks = 100 task executions per market day.

### Post-Close

| Time (IST) | Task Name | What It Does | Critical? |
|------------|-----------|-------------|-----------|
| 15:35 | AnkaCloseCapture | Capture official closing prices | CRITICAL |
| 15:35 | AnkaTAScanner | Run TA fingerprint scan | info |
| 16:00 | AnkaEODReview | P&L dashboard → Telegram | CRITICAL |
| 16:15 | AnkaEODTrackRecord | Write official track record | warn |
| 16:20 | AnkaEODNews | Backtest news predictions | warn |
| 16:30 | AnkaWebExport | Push data to website | warn |
| 16:45 | AnkaWatchdogGate | Watchdog gate run — check everything | warn |

### Weekly

| Day/Time | Task Name | What It Does |
|----------|-----------|-------------|
| Saturday 22:00 | AnkaETFReoptimize | Reoptimize ETF weights with Indian data (Karpathy) | CRITICAL |
| Sunday 22:00 | AnkaWeeklyAgg | Aggregate weekly spread statistics |
| Friday 16:00 | AnkaWeeklyReport | Weekly performance report → Telegram |

---

## 6. The Data Files — What Lives Where

### `pipeline/data/` — Runtime data (changes daily)

| File | Written By | Read By | Purpose |
|------|-----------|---------|---------|
| `today_regime.json` | regime_scanner | spread_intel, ranker, signals | Today's regime zone |
| `prev_regime.json` | regime_scanner | regime_scanner (next day) | Hysteresis state |
| `technicals.json` | technical_scanner | spread_intel, signals | Chart patterns |
| `positioning.json` | oi_scanner | spread_intel, signals | OI/PCR state |
| `oi_anomalies.json` | oi_scanner | signal_enrichment | Unusual OI activity |
| `news.json` | news_scanner | spread_intel, signals | Today's events |
| `news_verdicts.json` | news_backtest | next-day news_intel | Event outcome grading |
| `recommendations.json` | spread_intel | signals, next-day spread_intel | Spread trade signals |
| `regime_ranker_state.json` | reverse_regime_ranker | signals, next-day ranker | Stock trade signals |
| `correlation_breaks.json` | reverse_regime_breaks | signal_enrichment | Phase C divergences |
| `open_signals.json` | run_signals | eod_review, next intraday | Active positions |
| `closed_signals.json` | run_signals | eod_review, track_record | Closed positions |
| `track_record.json` | website_exporter | website, morning brief | Cumulative P&L |
| `watchdog_state.json` | watchdog | watchdog (next run) | Alert dedup state |

### `pipeline/data/daily/` — Historical snapshots

| File Pattern | Purpose |
|-------------|---------|
| `YYYY-MM-DD.json` | EOD prices for that date |
| `YYYY-MM-DD_fundamentals.json` | Valuation metrics for that date |

### `pipeline/autoresearch/` — Research engine outputs

| File | Purpose |
|------|---------|
| `regime_trade_map.json` | STATIC: which spreads work in which regime |
| `reverse_regime_profile.json` | Phase A: gap/drift patterns per regime transition |
| `etf_optimal_weights.json` | 31-ETF composite weights for regime detection |

### `data/` — Website JSON files (served to askanka.com)

| File | Purpose |
|------|---------|
| `articles_index.json` | List of published articles |
| `global_regime.json` | Current regime for website display |
| `live_status.json` | System health status |
| `track_record.json` | Performance history |
| `trust_scores.json` | Stock trust grades |
| `fno_news.json` | F&O news feed |

---

## 7. Known Gaps and Limitations

### Gap 1 (CRITICAL): ETF Engine and Regime Trade Map Are Frozen

The entire system's regime determination rests on two files that are NOT scheduled:

| File | What it does | Last run | Scheduled? |
|------|-------------|----------|-----------|
| `etf_optimal_weights.json` | 28-ETF composite → Nifty direction | **Apr 8** | NO |
| `regime_trade_map.json` | ETF regime → eligible spreads + sizing | **Apr 14** | NO |

The morning scanner reads `today_zone` from the trade map every day, but that field
has been stuck at "NEUTRAL" since April 14. If the real market shifted to RISK-OFF,
the system would still recommend NEUTRAL spreads.

**Impact:** The central brain of the system is frozen. Every downstream recommendation
(spreads, stock picks, correlation breaks) is based on a 4+ day old regime call.

**Target architecture (ETF Engine V2):**

```
SATURDAY NIGHT — Weekly Reoptimization
======================================

Indian close data (from daily dump):
  - FII/DII flows
  - India VIX close
  - Nifty/BankNifty close
  - Sector index closes
  - PCR (put-call ratio)
         +
28 Global ETFs (current):
  - US sectors, EM, commodities
  - Bonds, currencies
         |
         v
  Karpathy Random Search (2000+ iterations)
         |
    Optimizes TWO things:
         |
    1. REGIME ACCURACY
    |  "Which mix of global + Indian inputs
    |   best predicts next-week Nifty direction?"
    |
    2. PER-SPREAD SIZING
       "In each regime, which spreads deserve
        bigger allocations? Defence vs IT gets 2x
        in RISK-OFF (65% hit rate), Coal vs OMCs
        gets 0.5x (51% hit rate)"
         |
         v
  etf_optimal_weights.json (updated weekly)
  regime_trade_map.json (updated weekly, with sizing multipliers)


DAILY 04:45 — Fresh Signal Computation
=======================================

  Stored weights (from Saturday)
         +
  Today's ETF prices + Indian overnight data
         |
         v
  Compute today_zone: RISK-OFF / NEUTRAL / etc.
  Compute per-spread size multipliers
         |
         v
  regime_trade_map.json (today_zone updated daily)


DAILY 09:25 — Morning Scan (already works)
==========================================

  Reads fresh today_zone → picks eligible spreads
  Applies sizing multipliers → sizes each position
  Technicals + OI/PCR accentuate conviction
```

**FIXED (2026-04-18, Golden Goose Plan 1):**
1. Indian market data (FII, VIX, Nifty, PCR) added as inputs to ETF optimizer
2. AnkaETFReoptimize scheduled Saturday 22:00 IST (weekly reoptimization)
3. AnkaETFSignal scheduled daily 04:45 IST (fresh signal computation)
4. 8 tests passing, end-to-end pipeline verified

**Still TODO (Plans 2-5):**
- Extend optimizer to output per-spread sizing multipliers
- Unified backtest (Sunday night) for continuous validation
- Forward test loop: compare weekly predictions to actual outcomes

### Gap 2: Trust Scores Don't Auto-Refresh
Trust scores are batch-computed and stored as static JSON files. When a company
publishes new earnings, the score doesn't automatically update.

**Impact:** Trust gates may block/allow trades based on outdated management assessments.

**Fix needed:** Trigger re-scoring when new concall transcripts are detected.

### Gap 3: Kite Session Requires Manual Login
The Zerodha Kite API session token expires daily. `AnkaRefreshKite` at 09:00
refreshes it, but the initial login requires manual browser interaction.

**Impact:** If the token fully expires (not just daily refresh), OI scanning stops
silently.

### Gap 4: No Redundancy
The entire system runs on one Windows PC. If the PC is off, asleep, or restarting
during a scheduled task, that cycle is missed.

**Impact:** Missing the 09:25 morning scan means no recommendations for the day.

---

## 8. How to Check System Health

### Quick health check (run anytime):
```bash
python pipeline/watchdog.py --all --dry-run
```
This prints a full diagnostic without sending Telegram alerts.

### Check specific tier:
```bash
python pipeline/watchdog.py --tier critical --dry-run
```

### Check trust scores:
```bash
python pipeline/trust_score_terminal.py --top 20
```

### Check today's regime:
```bash
cat pipeline/data/today_regime.json | python -m json.tool
```

### Check active signals:
```bash
cat pipeline/data/signals/open_signals.json | python -m json.tool
```

---

## 9. Glossary

| Term | Meaning |
|------|---------|
| **Regime** | The current market environment (risk-on, risk-off, etc.) based on VIX |
| **Spread** | A pair trade: long one stock, short another in the same sector |
| **Trust Score** | OPUS ANKA's grade (A+ to F) for management credibility |
| **Phase A** | Overnight: compute which stocks move during regime transitions |
| **Phase B** | Morning: rank stocks and spreads for today's regime |
| **Phase C** | Intraday: detect stocks diverging from regime expectations |
| **Correlation Break** | A stock doing the opposite of what the regime predicts |
| **OI** | Open Interest — how many options contracts are outstanding |
| **PCR** | Put-Call Ratio — ratio of put OI to call OI |
| **Conviction** | How confident the system is in a signal (0-100) |
| **Hysteresis** | 2-day delay before officially changing regime (prevents whipsawing) |
| **Watchdog** | Automated monitor that checks if all tasks ran and files are fresh |
| **Gate** | A blocking rule that can prevent a signal from being sent |
| **F&O** | Futures & Options segment of NSE (213 liquid stocks) |
| **VIX** | India Volatility Index — measures market fear/greed |

---

*Document version: 2026-04-18. Auto-generated from code trace of askanka.com pipeline.*
