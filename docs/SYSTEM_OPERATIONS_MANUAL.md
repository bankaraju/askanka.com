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

    +------------------+    +------------------+
    | AnkaEODReview    |    | AnkaEODTrackRec  |
    | (16:00)          |    | (16:15)          |
    |                  |    |                  |
    | Dashboard of     |    | Official P&L     |
    | today's signals  |--->| calculation      |
    | win/loss/open    |    | Writes track     |
    | Sends to Telegram|    | record JSON      |
    | + website_export |    | + website_export |
    +------------------+    +------------------+
                                     |
                                     v
    +------------------+    track_record.json
    | AnkaEODNews      |    (feeds website +
    | (16:20)          |     next day)
    |                  |
    | Backtest today's |    Note: website_exporter.py
    | news events:     |    runs from morning_scan, every
    | did the stock    |    intraday cycle, eod_review,
    | move as expected?|    eod_track_record, and
    |                  |    daily_dump — not a separate
    | Writes:          |    scheduled task.
    | news_verdicts    |
    +------------------+


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

**MSI intraday refresh (added 2026-04-22)** — Morning `regime_scanner.py` persists raw FII flow into `today_regime.json.msi_cached_inputs`. Each 15-min intraday cycle calls `pipeline/msi_refresh.py`, which reuses the cached FII and re-fetches live VIX, USD/INR, Nifty 30d return, and crude to recompute MSI. On any failure the script exits 2 and leaves `today_regime.json` untouched — morning MSI is held and the watchdog flags `today_regime.json` as stale after `grace_multiplier × 15 min`. The `/api/regime` response now returns two timestamps: `updated_at` for the ETF regime and `msi_updated_at` for MSI specifically.

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

**Schema note (2026-04-22):** `today_regime.json` emits two equivalent keys: `zone` (canonical — read by all UI/API consumers including regime-banner.js, scenario-strip.js, `/api/regime`, `/api/candidates`) and `regime` (legacy alias retained for one release cycle for backward compat). Both always carry the same ETF-derived regime string (e.g., `"RISK-OFF"`). New consumers should read `.zone`; old consumers reading `.regime` are safe.

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
| `oi_scanner.py` | Kite API (Zerodha) | OI, PCR, max-pain, pinning + CE/PE walls for all 215 F&O stocks, both near + next-month expiries. Runs every 15 min via `intraday_scan.bat`; EOD snapshot archived by `eod_review.bat --archive-only`. Terminal consumer: `/api/oi/{ticker}`. |
| `news_scanner.py` | News APIs | Corporate announcements, global events |
| `news_intelligence.py` | News + history | Impact classification (high/medium/low). Attributes stocks via (a) literal ticker match in title, (b) alias lookup against `pipeline/config/news_aliases.json` so subsidiaries/common names (`"HDB Financial Services"`, `"Dr Reddy's"`, `"Hindustan Aeronautics"`) resolve to the parent F&O ticker. Added 2026-04-22 after 99% of events were writing `matched_stocks: []`. |
| `news_backtest.py` | `news_events_today.json` + history | Writes `news_verdicts.json`. Events without a `categories` list are dropped at verdict-write time (added 2026-04-22): `website_exporter._build_news_recs` joins on `(symbol, category)`, so verdicts with empty category silently fail the join and blank the News panel. |

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

The sequence inside `intraday_scan.bat` is: technicals → OI → news → fno_news → news_intel → spread_intel → **msi_refresh** → correlation_breaks → website_exporter. MSI refresh is soft: its exit code 2 on partial-fetch failure does not stop downstream scanners. A visible amber dot next to the MSI value in the terminal banner signals >30-min staleness.

**Files updated every 15 min:**
- `data/open_signals.json` — currently active signals
- `data/closed_signals.json` — signals that hit target/stop today

### Station 8: Post-Close Processing (15:30-16:45)

**What it does:** End-of-day wrap-up.

| Time | Task | Purpose |
|------|------|---------|
| 16:00 | AnkaEODReview | Dashboard → Telegram, archive OI, run website_exporter |
| 16:15 | AnkaEODTrackRecord | Calculate P&L, write `track_record.json`, run website_exporter |
| 16:20 | AnkaEODNews | Backtest news events: did the stock react as expected? |

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

**Per-ticker ATR stops for correlation-break trades (added 2026-04-22)** — Single-ticker directional signals generated by `pipeline/break_signal_generator.py` are no longer routed through the `spread_statistics` fallback (which defaulted to `avg_favorable_move=2.0 → -1.00%` for any name not in the spread catalog). Each signal now carries `_atr_stop = {stop_pct, stop_price, atr_14, stop_source}`, computed at creation time from yfinance 14-day ATR × 2.0. If yfinance fetch fails, `stop_source="fallback"` and the legacy `-1.00%` is used; the Open Positions table renders a muted `◦` next to such stops so the trader can tell real stops from fallbacks. `signal_tracker.check_signal_status()` prefers `_atr_stop.stop_pct` when `source == "CORRELATION_BREAK"` and the stop was ATR-derived. Pair-spread trades continue to use `spread_statistics`. Retrofit: only signals created after 2026-04-22 get ATR stops — three positions open at the time of rollout (YESBANK/IEX/BHEL) kept their `-1.00%` fallback values.

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
| 09:25 | AnkaPhaseCShadowOpen | F3 live shadow: record OPEN rows for today's OPPORTUNITY signals | info |

### Market Hours (09:30-15:30)

Every 15 minutes, two tasks run as a pair:

| Task Pattern | What It Does |
|-------------|-------------|
| AnkaIntraday#### | Re-scan technicals, OI, news, spreads, correlation breaks |
| AnkaSignal#### | Score signals, apply gates, send Telegram alerts |
| AnkaWatchdogIntraday | (every 15 min) Check critical task freshness |
| AnkaCorrelationBreaks | (every 15 min) Phase C: detect regime-stock divergence |
| AnkaPhaseCShadowClose | 14:30 IST — mechanical close of F3 live shadow positions (TIME_STOP) |

That's 25 intraday cycles x 4 tasks = 100 task executions per market day.

### Post-Close

| Time (IST) | Task Name | What It Does | Critical? |
|------------|-----------|-------------|-----------|
| 16:00 | AnkaEODReview | P&L dashboard → Telegram, archive OI, push website JSONs | CRITICAL |
| 16:15 | AnkaEODTrackRecord | Write official track record, push website JSONs | warn |
| 16:20 | AnkaEODNews | Backtest news predictions | warn |
| 16:35 | AnkaTrustEOD | OPUS ANKA EOD review + next-day outlook | warn |
| 16:45 | AnkaWatchdogGate | Watchdog gate run — check everything | warn |

Note: `website_exporter.py` is folded into morning_scan, every intraday cycle, eod_review, eod_track_record, and daily_dump — it is not a standalone scheduled task. Auto-pushes data/*.json to the GitHub Pages branch.

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
| `positioning.json` | oi_scanner | spread_intel, signals, terminal | Per-stock OI/PCR/max-pain/pinning (215 F&O stocks) |
| `oi_history_stocks/YYYY-MM-DD.json` | oi_scanner --archive-only (eod_review.bat) | future backtests | Daily EOD snapshot of positioning.json |
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
| `fno_news.json` | F&O news feed — derived by `website_exporter.export_fno_news()` from `pipeline/data/news_verdicts.json`; only HIGH_IMPACT + MODERATE verdicts with ADD/CUT recommendations are included, sorted by impact tier then \|hit_rate\| descending. |

---

## 7. Anka Terminal

The trading intelligence terminal is a local web application that provides a visual interface over the pipeline data.

### Usage

```bash
python -m pipeline.terminal              # start on localhost:8501, opens browser
python -m pipeline.terminal --port 9000  # custom port
python -m pipeline.terminal --no-open    # don't auto-open browser
```

### Architecture

- **Backend:** FastAPI serving REST APIs from pipeline JSON files
- **Frontend:** Vanilla JS + Lightweight Charts (TradingView) + Lucide icons
- **Data flow:** Pipeline scheduled tasks → JSON files → FastAPI → Browser
- **No database:** reads directly from `pipeline/data/` and `data/`

### Tabs (post 2026-04-20 restructure)

10 visible tabs in the sidebar, each answering one question with one feed. Keyboard shortcuts `1`–`9` map to the first nine; `0` jumps to Track Record. Settings is mouse-only.

| # | Tab | Question it answers | Feed |
|---|-----|--------------------|------|
| 1 | Dashboard | What's open right now? (live positions, stops, targets, P&L) | `/api/signals` (positions array) |
| 2 | Trading | What's tradeable today? (browser over `tradeable_candidates[]`, filter chips, expandable narration drawer) | `/api/candidates` (tradeable_candidates) |
| 3 | Regime | Where is the market? (ETF zone + score, MSI secondary, Phase A/B/C) | `/api/regime` + `/api/research/digest` + `/api/candidates` |
| 4 | Scanner | What anomalies fired? (read-only events: TA fingerprints, OI spikes, correlation breaks) | `/api/candidates` (signals array) |
| 5 | Trust | Which managements pass? | `/api/trust-scores` |
| 6 | News | What just happened? | `/api/news/macro` |
| 7 | Options | What's the synthetic leverage? | `/api/research/digest` leverage_matrices |
| 8 | Risk | Am I within bounds? | `/api/risk-gates` + `/api/risk/regime-flip` (p95 drawdown from historical calm_breaks; replaced the hardcoded `-2%/position` placeholder on 2026-04-22) |
| 9 | Research | Full intelligence digest | `/api/research/digest` |
| 0 | Track Record | Realised P&L, equity curve, closed trades | `/api/track-record` |
|   | Settings | Broker, alerts, display | local config |

The old `Intelligence` tab (Trust + News + Research + Options sub-tabs) was deleted; each sub-tab is now a top-level page. The old `Trading` page also lost its Charts/TA sub-tabs — the candidate drawer absorbs the narration role; standalone Charts/TA can be re-homed in a follow-up.

#### `/api/candidates` (new endpoint)

Composes a dual-array schema from existing files (no new pipeline writers, no scheduled tasks):

- `tradeable_candidates[]` — things you could open today: `static_config` spreads (`today_regime.eligible_spreads`), `dynamic_pair_engine` (forward-compat — file doesn't exist yet), `regime_engine` Phase B picks (`today_recommendations.json`). Each carries legs, conviction, score, sizing basis, horizon, narration.
- `signals[]` — events that fired but aren't directly tradeable: `ta_scanner` fingerprint hits, `correlation_break` Phase C events, future `oi_anomaly` items. Each carries ticker, event_type, source, fired_at, context dict.
- `updated_at` — provenance timestamp from `today_regime.timestamp`.

Source: `pipeline/terminal/api/candidates.py`. Trading consumes `tradeable_candidates`; Scanner consumes `signals`; Regime uses both for snapshot panes.

#### `/api/live_ltp` (new 2026-04-22)

`GET /api/live_ltp?tickers=HAL,BEL,TCS` → `{"HAL": 4284.30, "BEL": 449.85, "TCS": 2576.70}`.

Backend for a future 5s poll that patches the Dashboard's `current` column between 15-min batches. Backed by `signal_tracker.fetch_current_prices` (same Kite session the batch uses). Unknown tickers return `null` so the frontend falls back to the `live_status.json` snapshot rather than painting a fake `₹0.00`. Input is capped at 50 tickers per request. Frontend JS poller is a deferred follow-up. Source: `pipeline/terminal/api/live.py`.

#### `/api/risk/regime-flip` (new 2026-04-22)

`GET /api/risk/regime-flip?to_zone=RISK-OFF&percentile=95` → `{n_flips, worst_drawdown_pct, median_drawdown_pct, sample_returns, percentile, source, data_file}`.

Replaces the hardcoded `-2%/position` placeholder on the Risk tab with a real percentile computed from `pipeline/autoresearch/regime_persistence_results.json`'s `calm_breaks` list. Data is `nifty_5d_after` (Nifty-index proxy, clearly labelled in the `source` field); per-spread P&L replacement awaits a daily portfolio series from `unified_backtest`. Source: `pipeline/terminal/api/risk.py` + `pipeline/autoresearch/regime_flip_analyzer.py`.

### Design System

Design tokens defined in `pipeline/terminal/static/css/terminal.css`. Locked: DM Serif Display + Inter + JetBrains Mono, dark theme with gold accents.

---

## 8. Known Gaps and Limitations

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

### Gap 2 (FIXED): Shadow P&L + Risk Guardrails Not Wired

**FIXED (2026-04-18, Golden Goose Plans 3-4):**
- `pipeline/risk_guardrails.py` — portfolio circuit breaker (L1: -10% reduce, L2: -15% pause)
- `pipeline/shadow_pnl.py` — paper trading engine with stops/targets/expiry
- Both wired into `run_signals.py` — risk gates checked before every new entry,
  shadow trades created with full metadata (regime, conviction, z-score)
- Shadow trades logged to `data/signals/shadow_trades.json`
- 29 tests covering all exit modes and risk levels

### Gap 3: Trust Scores Don't Auto-Refresh
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

## 9. How to Check System Health

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

## 10. Glossary

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
