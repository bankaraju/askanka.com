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
bonds, currencies) to build a composite signal that maps to a regime zone.

> **⚠ KNOWN ISSUE — 62.3% accuracy claim superseded (2026-04-26 audit, REVISED)**
>
> The "62.3% accuracy vs 51.6% random" number was generated under a single
> 70/30 train/test split where the test-set Sharpe was the weight-selection
> criterion (i.e., the test set was effectively in-sample). Re-tested under
> rolling weekly refit on the same 24-feature panel that production uses
> (verdict at `pipeline/data/research/etf_v3/2026-04-26-etf-v3-verdict.md`):
>
> - **v2-faithful (production architecture):** 53.24% accuracy over 494 OOS
>   predictions, +1.62pp edge vs majority baseline, 95% CI [48.79%, 57.69%]
> - **v3 (engineered alternative):** 53.35% accuracy over 493 OOS, +1.62pp edge,
>   95% CI [48.88%, 57.81%]
> - **Both architectures match within bootstrap noise.** Neither hits 95%
>   significance — both CIs include the baseline. One-sided P(acc > base) ~75%.
>
> The honest production-cadence number is **~53.2% with a +1.6pp edge over
> majority class, not significant at 95%**. Cite this, not 62.3%.
>
> Year-on-year decay is the most concerning signal: 2024 ~58% → 2025 ~52% →
> 2026 YTD ~48-52%. If decay continues, even the +1.6pp full-window edge will
> disappear. The qualitative regime label (RISK-OFF / EUPHORIA ranking) may
> still have utility — see `regime_transition_overnight` overnight asymmetry.
>
> Deep-read v2 findings + 5 structural issues:
> `pipeline/data/research/etf_v3/2026-04-26-v2-deep-read-findings.md`

**How it works:**
- Takes daily returns of 28 ETFs (financials, innovation, treasury, VIX, developed
  markets, bonds, euro, Japan, S&P 500, India ETF, China, emerging markets, etc.)
- Runs 2,000 random weight combinations (Karpathy random search) to find the
  mix that best predicts next-day Nifty direction
- Optimizes by Sharpe ratio (risk-adjusted return)
- Outputs a single composite number → maps to regime zone (RISK-OFF / CAUTION /
  NEUTRAL / RISK-ON / EUPHORIA via thresholds in `_signal_to_zone`)

**Known structural limitations (2026-04-26 deep-read audit):**
- Indian features are joined as RAW LEVELS (vix close ~17, nifty close ~20000)
  to 1-day percentage returns without standardisation — Karpathy seed dominated
  by NIFTY level autocorrelation
- `etf_daily_signal` silently drops Indian feature weights at signal time
  (only fetches keys in `GLOBAL_ETFS` dict; Indian weights are zeroed). A
  WARNING now fires when this happens (added 2026-04-26)
- Production fit uses ~6 weeks of Indian data ffill'd over 3 years — Indian
  features are constant for ~94% of the fit window

**Output:** `autoresearch/etf_optimal_weights.json`

**STATUS: SCHEDULED. AnkaETFReoptimize runs Saturday 22:00 IST (weekly).
Indian feature weights stored but currently dropped at signal time (see above).
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

**Same-day spread bootstrap (added 2026-04-22):** After `eligible_spreads` is assembled, `regime_scanner.scan_regime()` calls `spread_bootstrap.ensure()` for each spread not already present in `pipeline/data/spread_stats.json`. This prevents the `INSUFFICIENT_DATA` stall that previously required waiting until Sunday 22:00 `AnkaWeeklyStats` to populate a new spread's historical stats. Bootstrap result (status / tier) is stored under each `eligible_spreads[name]["_bootstrap_result"]` for downstream consumers (e.g., Task B1 conviction annotator). See `pipeline/spread_bootstrap.py`.

**Gate annotation (added 2026-04-22, Task B1):** After bootstrap, each entry in `eligible_spreads` is annotated with four additional fields before `today_regime.json` is written:
- `conviction`: HIGH / MEDIUM / LOW / PROVISIONAL / NONE — classified by `_classify_conviction()` in `regime_scanner.py`. HIGH requires |z| >= 2.0 and best_win >= 65%; MEDIUM requires |z| >= 1.5 and best_win >= 55%; LOW is in-gate but below thresholds; PROVISIONAL means fewer than 30 regime-matched samples; NONE is returned for INSUFFICIENT_DATA / INACTIVE / no-return states.
- `z_score`: float or None — z-score of today's spread return vs the regime distribution, from `spread_intelligence.apply_gates()`. None before market close (no live price yet).
- `gate_status`: string from `apply_gates()` — ACTIVE (diverging), AT_MEAN (within 1σ), INSUFFICIENT_DATA, INACTIVE, NO_TODAY_RETURN (pre-close).
- `tier`: FULL (>= 30 samples) or PROVISIONAL (< 30 samples) — derived from the spread_stats regime bucket count.

Downstream consumers (`pipeline/terminal/api/candidates.py`) read these fields directly, ending the "Conviction: NONE" default in the Trading tab.

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

`apply_gates()` now calls `_maybe_bootstrap()` defensively when a spread's regime bucket is missing from `spread_stats`. This gives the same-day bootstrap a second chance within the intraday cycle. On-disk schema for each bucket stays `{count, mean, std, …}` — the `tier` label (FULL/PROVISIONAL/DROPPED) is derived read-time via `spread_bootstrap.tier_from_n(count)` and is never written to disk. Cross-reference: Sunday 22:00 `AnkaWeeklyStats` remains the authoritative full-history recompute.

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

**Gate 4 — News Verdict Modifier (Task B7):** At candidate scoring time, `apply_news_modifier`
(`pipeline/signal_enrichment.py`) looks up `pipeline/data/news_verdicts.json` for a matching
`(symbol, category)` row. If the verdict is `HIGH_IMPACT + ADD` aligned with direction → `+10`;
`MODERATE + ADD` aligned → `+5`; `HIGH_IMPACT + CUT` opposite → `-10`; `MODERATE + CUT`
opposite → `-5`; all other combinations (LOW, NO_IMPACT, NO_ACTION) → `0`. For spread signals
with multiple legs, per-leg deltas are summed and capped at `±15`. Result fields `news_modifier`
and adjusted `entry_score` are attached to every candidate returned by `GET /api/candidates`.
Today all 185 verdicts are `NO_IMPACT/NO_ACTION` (upstream tracking #37), so modifiers are
`0` — the wiring is live and will react immediately when upstream produces real verdicts.

**Gate 5 — Trust Grade Modifier (Task B8):** Applied immediately after the news modifier.
`apply_trust_modifier` (`pipeline/signal_enrichment.py`) is a **regime-conditional** modifier:
it only fires when the ETF-engine `zone` is `NEUTRAL`. The rule encodes the finding from
`memory/project_scorecard_alpha_test.md` — trust grade is NOT standalone alpha (D/F stocks
outperform A/B across the full sample), but within the NEUTRAL cohort specifically, grade
becomes useful: weak-trust longs are penalised and weak-trust shorts are rewarded.

| Grade | LONG in NEUTRAL | SHORT in NEUTRAL | Any non-NEUTRAL |
|-------|----------------|-----------------|-----------------|
| A, B  | 0              | 0               | 0               |
| C     | 0              | 0               | 0               |
| D, F  | −5             | +5              | 0               |

For spread signals, the rule is applied per leg, then summed and capped at `±10` (smaller cap
than news because trust signal is noisier). Per-leg breakdown is stored in
`trust_contributing_legs` for UI tooltip. Trust grades are sourced from
`data/trust_scores.json` (v2 format, `sector_grade` field, 210/213 stocks covered); missing
or `INSUFFICIENT_DATA` grades → 0. When the current regime is RISK-OFF or RISK-ON, all
modifiers are 0 regardless of grade — the wiring is proved by unit tests; live behaviour will
show `trust_modifier=0` on RISK-OFF days (correct).

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
| 16:30 | AnkaBulkDeals | Pull NSE rolling-today bulk + block deals → `pipeline/data/bulk_deals/<date>.parquet` (forward-only, see forensic card v2) |
| 18:30 | AnkaInsiderTrades | Pull NSE PIT (insider trading) disclosures, last 7 days → `pipeline/data/insider_trades/<YYYY-MM>.parquet` |

**What carries forward to tomorrow:**
- `data/track_record.json` — cumulative performance history
- `data/news_verdicts.json` — which news predictions were correct
- `data/prev_regime.json` — today's regime (for hysteresis)
- `data/regime_ranker_state.json` — active stock positions
- `data/recommendations.json` — active spread positions

### Station 9: Feature Coincidence Scorer

Added 2026-04-22. A 0-100 per-ticker attractiveness score that ranks
candidates within conviction bands. Does NOT gate trades.

**Schedule:**
- Weekly fit — `AnkaFeatureScorerFit`, Sunday 01:00 IST. Runs quarterly
  walk-forward validation on the F&O universe, writes
  `pipeline/data/ticker_feature_models.json` (models + metadata per ticker).
- Intraday apply — part of every `AnkaIntradayNNNN` cycle. Reads cached
  models, builds live feature vectors, writes `attractiveness_scores.json`
  and appends to `attractiveness_snapshots.jsonl`.

**Surfaces:** three UI surfaces reading the scores file via
`GET /api/attractiveness`:
- Trading tab — Attractiveness column between Score and Horizon
- Dashboard Positions table — "Attract NN ↑/↓/→" badge next to P&L
- Candidate drawer — feature contribution bar chart

**Health bands:** GREEN (mean AUC ≥ 0.55, min ≥ 0.50) / AMBER (≥ 0.52) /
RED / UNAVAILABLE. Tickers with <3 walk-forward folds fall back to
sector-cohort models.

**Register the task (one-time manual step):**
```
schtasks /create /tn "AnkaFeatureScorerFit" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\fit_feature_scorer.bat" /sc weekly /d SUN /st 01:00
```

**Spec:** `docs/superpowers/specs/2026-04-22-feature-coincidence-scorer-design.md`

**Status (2026-04-22): WIRED — awaiting first production fit.**

End-to-end smoke completed 2026-04-22:
- Unit tests: 45 passed across `pipeline/tests/feature_scorer` + `test_watchdog_feature_scorer` (2 slow-tagged tests skipped: universe-fit coverage until `download_fno_history --days 1825` extends depth to 5y, and 60-day forward validation until the snapshot ledger accumulates ~60 sessions).
- `/api/attractiveness` + `/api/attractiveness/{ticker}` respond with 200 on seeded scores and 404 on unknown tickers.
- Three UI surfaces (Trading column, Positions badge, Candidate drawer feature-contribution panel) render correctly against the seeded fixture.

Pending observation (not blocking):
- First `AnkaFeatureScorerFit` Sunday 01:00 run — will populate `ticker_feature_models.json`. Review coverage distribution afterward; rerun the `test_feature_scorer_universe_fit_coverage` test.
- Arrow-movement in the Positions badge across two adjacent intraday cycles (visual confirmation during market hours).
- `test_green_model_picks_beat_base_rate_by_5pp` stays skipped until snapshot history ≥ 60 days.

---

### Station 10: Unified Analysis Panel (UAP) v1

Added 2026-04-23. One shared terminal component renders all four analysis
engines (FCS, TA, Spread, Correlation Break) through a single envelope:
Verdict + Conviction (0–100) + Evidence + Model Health + Freshness +
Calibration tag. Replaces the engine-specific panels that preceded it.

**Data flow.** `pages/trading.js` parallel-fetches `/api/attractiveness`,
`/api/ta_attractiveness`, `/api/research/digest`, `/api/correlation_breaks`
via `Promise.allSettled`. Raw responses attach to each candidate as
`analyses_raw`. Drawer open → `components/analysis/panel.js` renders four
cards in frozen order `FCS → TA → Spread → Corr Break` via per-engine
adapters.

**Calibration tag.** `walk_forward` scores render gold; `heuristic` scores
render muted with dotted underline. Makes the no-hallucination mandate
visible: FCS/TA earn their scores via walk-forward AUC; Spread (gate
mapping) and Correlation Break (σ × 25) are asserted heuristics with no
calibration in v1.

**TA scorer inputs.**
`pipeline/data/fno_historical/RELIANCE.csv` +
`pipeline/data/india_historical/indices/NIFTYENERGY_daily.csv` +
`NIFTY_daily.csv`
→ `fit_universe.py` (Sunday 01:30 `AnkaTAScorerFit`)
→ `pipeline/data/ta_feature_models.json`
→ `score_universe.py` (daily 16:00 `AnkaTAScorerScore`)
→ `pipeline/data/ta_attractiveness_scores.json`.
Surfaced by `GET /api/ta_attractiveness` + `/ta_attractiveness/{ticker}`.

**Freshness contract.** Watchdog tracks `ta_feature_models.json` (weekly
warn, grace 2.0) and `ta_attractiveness_scores.json` (daily warn, grace
2.0). TA card in the UI shows previous-session 16:00 timestamp during
market hours — this is correct by design (daily bars, not intraday).

**Scope boundary.** v1 is ranking/research only — does NOT gate trades or
set size. RELIANCE-only TA pilot; 212/213 tickers show UNAVAILABLE card
until v2 rollout after 60-day forward uplift audit.

**Register the tasks (one-time manual step):**
```
schtasks /create /tn "AnkaTAScorerFit"   /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\fit_ta_scorer.bat"   /sc weekly /d SUN /st 01:30
schtasks /create /tn "AnkaTAScorerScore" /tr "C:\Users\Claude_Anka\askanka.com\pipeline\scripts\score_ta_scorer.bat" /sc daily /st 16:00
```

**Files of interest.**
- Backend: `pipeline/ta_scorer/*.py`, `pipeline/terminal/api/ta_attractiveness.py`
- Frontend: `pipeline/terminal/static/js/components/analysis/{panel,envelope,health}.js`, `adapters/{fcs,ta,spread,corr}.js`
- Design: `docs/superpowers/specs/2026-04-23-unified-analysis-panel-design.md`
- Plan: `docs/superpowers/plans/2026-04-23-unified-analysis-panel.md`

**Status (2026-04-23): WIRED — awaiting first `AnkaTAScorerFit` Sunday run.**

---

### Station 11: Regime-Aware Autoresearch Engine

Added 2026-04-24 (Tasks 0–9 of the 11-task plan). A human-in-loop DSL
proposal generator → in-sample evaluation → BH-FDR holdout gate →
forward-shadow predicate → live promotion pipeline, run per regime.
Exists because of §0.3 Posture C Disciplined-Pragmatic: no new
trading strategy ships outside this engine ever again. Every incumbent
either has a registry-backed statistical basis or is retired.

**Data artefacts (paths + refresh cadence).**
- `pipeline/data/regime_history.csv` — quantile-zoned regime labels (cutpoints frozen on 2018-01-01..2021-04-22 calibration window; daily refresh downstream of `AnkaETFSignal`)
- `pipeline/data/regime_cutpoints.json` — frozen q20/q40/q60/q80 cutpoints (write-once)
- `pipeline/data/vix_history.csv` — daily VIX series (daily refresh)
- `pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json` — single-stock-futures eligibility list (manual refresh)
- `pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json` — pair universe (manual refresh)
- `pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json` — in-sample cache; seeded with INSUFFICIENT_POWER placeholders
- `pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl` — append-only runtime log (every proposer call)
- `pipeline/autoresearch/regime_autoresearch/data/incumbent_audit_2026-04-24.json` — latest incumbent audit snapshot

**Run Mode 1 (human-in-loop NEUTRAL pilot):**
```
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_pilot --regime NEUTRAL
python -m pipeline.autoresearch.regime_autoresearch.scripts.run_pilot --regime NEUTRAL --auto-approve
```
See `pipeline/autoresearch/regime_autoresearch/README_PILOT.md` for the
full walk-through and interpretation guide.

**Run the incumbent audit:**
```
python -m pipeline.autoresearch.regime_autoresearch.scripts.audit_incumbents
```

**Lifecycle.** 7-state DSL: `PROPOSED → PRE_REGISTERED → HOLDOUT_PASS →
FORWARD_SHADOW → PROMOTED_LIVE`; `RETIRED` and `DEAD` are terminals.
Displacement + rate-limit (2-per-regime-per-quarter) + scarcity-fallback
hurdle (<3 clean incumbents → NIFTY buy-and-hold benchmark) defined in
the design spec at `docs/superpowers/specs/2026-04-24-regime-aware-autoresearch-design.md`.

**Hurdles.** `Δ_in = 0.15` (in-sample uplift over incumbent or scarcity benchmark),
`Δ_holdout = 0.10` (holdout replication threshold). BH-FDR q = 0.1 applied
on "whichever-first" batch trigger: 30 calendar days OR ≥10 accumulated
holdout candidates.

**Forward shadow predicate.** A candidate must accumulate 60 calendar
days AND 50 events in live shadow AND beat the incumbent by `Δ_holdout`
on that live sample before promotion.

**Kill switch.** Enforced by `pipeline/scripts/hooks/pre-commit-strategy-gate.sh`
(local pre-commit) and `.github/workflows/strategy-gate.yml` (CI on
pull_request). New files matching the strategy-file patterns must ship
with a matching `docs/superpowers/hypothesis-registry.jsonl` entry in
the same commit — see the kill-switch policy section of `CLAUDE.md`.

**Known limitations (open follow-ups).**
- #188 — research-zones vs live-engine-zones unification pending (research uses quantile cutpoints, live engine still on absolute thresholds)
- #190 — pair construction deferred (3 of 4 DSL-to-returns constructions shipped; pair wiring is future work)
- #191 — walk-forward folds not yet in the runner (current runner uses single train+val split)
- #195 — hurdle semantics (absolute uplift vs relative uplift) still under review
- #196 — pre-register best NEUTRAL pilot candidate (`days_from_52w_high` bottom_10, Sharpe +1.13)

**Status (2026-04-24): NEUTRAL Mode-1 pilot complete, 127 autoresearch tests green at `d8f0d2f`; 1 clean-positive candidate awaiting pre-registration.**

### v2 differences (2026-04-25)

v2 layered on the v1 infrastructure after the NEUTRAL pilot produced 0 survivors under the 3-gate verdict. v1 is parked at `09847ef`; v2 ships at commit chain `a1ce41c..2578e98` on `feat/phase-c-v5`.

- **Panel start**: `PANEL_START = 2020-04-23`, 252 trading days earlier than `TRAIN_VAL_START`. Fixes 252-bar fold-0-empty failure mode.
- **Hurdle**: construction-matched random-basket bootstrap. `load_null_basket_hurdle(construction, k, hold_horizon, regime, window)` replaces `regime_buy_and_hold_sharpe`. Precomputed table at `pipeline/autoresearch/regime_autoresearch/data/null_basket_hurdles_v2.parquet` (1,200 rows; 5 constructions × 8 k × 3 horizons × 5 regimes × 2 windows). Placeholder ships at `--n-trials 3`; rebuild with `--n-trials 1000` before first live Mode 2 run.
- **Feature library**: 34 features (was 20). 14 additions from existing price/volume/trust data; microstructure (OI/PCR/basis) deferred to v2.1.
- **Proposal logs sharded** per regime: `proposal_log_{risk_off,caution,neutral,risk_on,euphoria}.jsonl`. v1 NEUTRAL rows preserved verbatim in the NEUTRAL shard. New rows carry `schema_version="v2"`.
- **Mode 2 orchestrator**: `AnkaAutoresearchMode2.bat` at 20:00 IST spawns 5 parallel regime workers via `scripts/run_mode2.py`. Supports `--dry-run --cap 0` for test fast-path.
- **BH-FDR**: `AnkaAutoresearchBHFDR.bat` at 05:00 IST fires per-regime batches on v1's whichever-first rule (≥10 accumulated OR ≥30 calendar days) via `scripts/run_bh_fdr_check.py`.
- **Holdout runner**: `AnkaAutoresearchHoldout.bat` at 05:30 IST.
- **Autonomy boundary**: ends at forward-shadow. `scripts/promote_to_live.py` is the only code path that writes `*_strategy.py` files — refuses any rule not in `state=FORWARD_SHADOW_PASS`, commits strategy file + hypothesis-registry entry atomically so the pre-commit gate passes in one commit.
- **Scarcity-fallback deleted**: every proposal now gets a construction-matched null regardless of incumbent count. `hurdle_sharpe_for_regime` in `incumbents.py` reduced to a mean-of-clean-incumbents helper for audit use only.

**v2 status (2026-04-25): infrastructure shipped; 203-test autoresearch suite green across Tasks 1-7.**

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

**Conviction downgrade (B1.5):** Phase B picks exposed in the terminal via `pipeline/terminal/api/candidates.py::_build_regime_picks` apply episode-based label honesty before display. Raw ranker output can carry "HIGH" on a single-episode signal — that label is dishonest. The API layer applies: `episodes < 15 → PROVISIONAL`, `15 ≤ episodes < 30 → MEDIUM` (even if ranker said HIGH), `episodes ≥ 30 → pass through raw label`. Score is recalculated as `hit_rate × 100 × min(episodes, 30) / 30` with a floor of 20 for PROVISIONAL so it is never displayed as zero. Constants `_MIN_EPISODES_FULL=30`, `_MIN_EPISODES_PROVISIONAL=15`, `_PROVISIONAL_SCORE_FLOOR=20` live at the top of `candidates.py`.

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

**Stop hierarchy — trail dominates daily once armed (rewritten 2026-04-22, B9)** — `check_signal_status()` in `pipeline/signal_tracker.py` now enforces a two-phase stop regime. Before the trail arms (peak < trail_budget), the daily stop is the sole floor — it fires on any bad single day and protects fresh entries. Once the trail arms (peak >= trail_budget, where trail_budget = avg_favorable × sqrt(days_since_check)), the daily stop is **inert** — only a retracement past the trail_stop can close the position. This prevents the Sovereign Shield Alpha pattern: a +11.11% peak position killed by a single -1.10% day despite being deeply profitable. The trail arm condition mirrors the existing `trail_stop_triggered()` guard.

**Trail ratchet invariant — monotonic trail_stop within a position's life (B10, 2026-04-22)** — Trail ratchets monotonically upward: once computed, `peak_trail_stop_pct` (persisted on the signal dict) never decreases within a position's life. After a holiday gap, `days_since_check` grows and `trail_budget` widens, which previously caused `trail_stop = peak - budget` to drift lower — allowing a position to retrace further without firing (Fossil Arbitrage: +7.07% peak round-tripped to -4.04% unrestricted). Fix: `check_signal_status()` persists `peak_trail_stop_pct` and only raises it, never lowers it. The `trail_stop_triggered()` function accepts an optional `ratcheted_stop` kwarg and uses `max(ratcheted_stop, peak - budget)` as the effective stop level. Arm guard continues to use the live `trail_budget` so unarmed positions cannot fire via a widened gap budget.

**Per-ticker ATR stops for correlation-break trades (added 2026-04-22)** — Single-ticker directional signals generated by `pipeline/break_signal_generator.py` are no longer routed through the `spread_statistics` fallback (which defaulted to `avg_favorable_move=2.0 → -1.00%` for any name not in the spread catalog). Each signal now carries `_atr_stop = {stop_pct, stop_price, atr_14, stop_source}`, computed at creation time from yfinance 14-day ATR × 2.0. If yfinance fetch fails, `stop_source="fallback"` and the legacy `-1.00%` is used; the Open Positions table renders a muted `◦` next to such stops so the trader can tell real stops from fallbacks. `signal_tracker.check_signal_status()` prefers `_atr_stop.stop_pct` when `source == "CORRELATION_BREAK"` and the stop was ATR-derived. Pair-spread trades continue to use `spread_statistics`. Retrofit: only signals created after 2026-04-22 get ATR stops — three positions open at the time of rollout (YESBANK/IEX/BHEL) kept their `-1.00%` fallback values.

#### Phase C labels (post-2026-04-23 direction audit)

The legacy `OPPORTUNITY` label was split into two geometry-specific variants. Every event now carries four direction-audit fields (`event_geometry`, `direction_intended`, `direction_tested`, `direction_consistent`) populated by `reverse_regime_breaks.py::enrich_break_with_direction`.

- **OPPORTUNITY_LAG** — `sign(expected_return) != sign(residual)` (peers moved, stock lagged). Backtest FADE and live FOLLOW directions agree on this slice by construction. The signal generator routes these to the shadow ledger at `TIER_EXPLORING` (0.5-unit paper row). Governed by pre-registered hypothesis `H-2026-04-23-002`.
- **OPPORTUNITY_OVERSHOOT** — `sign(expected_return) == sign(residual)` (peers moved, stock moved further). Backtest FADE and live FOLLOW directions are opposite. **Alert-only. No shadow row.** Live engine does not trade these until `H-2026-04-23-003` (FADE hypothesis) clears Bonferroni. As of 2026-04-23 both LAG and OVERSHOOT slice compliance runs ended with `decision=FAIL`, so Phase C stays `TIER_EXPLORING`.
- **POSSIBLE_OPPORTUNITY / WARNING / CONFIRMED_WARNING / UNCERTAIN** — unchanged semantics, no direction split.

DIRECTION-SUSPECT verdicts per (ticker, direction) live at `pipeline/autoresearch/results/direction_suspect_verdicts_<date>.json`. See `docs/superpowers/phase_c_direction.md` for the audit mechanics and `docs/superpowers/specs/2026-04-23-phase-c-follow-vs-fade-audit-design.md` for the spec.

#### Phase C compliance audit trail

Every pre-registered hypothesis against the Phase C event panel appears in `docs/superpowers/hypothesis-registry.jsonl` with its terminal_state. Running audit (most recent last):

- `H-2026-04-23-001` — parent event panel (14,907 events, |z|≥2). PASS (2026-04-23). Registry line 1.
- `H-2026-04-23-002` (LAG slice) — OPPORTUNITY_LAG FADE hypothesis. FAIL under Bonferroni (2026-04-23).
- `H-2026-04-23-003` (OVERSHOOT slice) — OPPORTUNITY_OVERSHOOT FADE hypothesis. FAIL under Bonferroni (2026-04-23).
- `H-2026-04-24-001` — TA Coincidence Scorer RELIANCE pilot. FAIL (mean_auc 0.509, 2026-04-23).
- `H-2026-04-24-002` — persistent-break + cross-sectional Lasso (symmetric |z|≥3 on T and T-1). ABANDONED_PRE_EXECUTION (n=116 below 500 floor, 2026-04-24).
- `H-2026-04-24-003` — persistent-break + cross-sectional Lasso v2 (asymmetric |z|≥3 on T AND |z|≥2 on T-1, same-sign). **FAIL** (2026-04-24). Model S1 Sharpe −3.28 vs buy-and-hold +1.70, margin −4.98, permutation p=0.81. Fragility STABLE 26/27 — the negative edge is NOT a parameter artefact. Artifacts at `pipeline/autoresearch/results/compliance_H-2026-04-24-003_20260423T210632Z/`. The 236-feature Lasso cannot extract predictive signal from the persistent-break subset; always-fade and buy-and-hold both dominate in the same holdout.
- `H-2026-04-25-001` — earnings-decoupling pre-publication residual + ΔPCR amplifier (T-3 close → T-1 close MODE A). **FAIL** (2026-04-25). 100k-perm null p=0.336, n=26 (1 regime <30, §9 underpowered). S0 Sharpe 0.63 / hit 0.46 / DD 6.3% — fails §1/3 thresholds. random_direction comparator beats strategy at S0 (mean 0.57% vs 0.09%, §9B.1 fail). β-residual §11B fail. Single-touch holdout consumed per §10.4 — re-run requires v2 pre-registration with fresh holdout. Run executed on Contabo VPS (~12s wall clock, 12-core EPYC). Artifacts at `docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/`.
- `H-2026-04-25-002` — etf-coefficient → per-stock 3-class tail classifier (small MLP vs always-prior/regime-logistic/interactions-logistic baselines, σ=1.5 thresholded labels, 12-month single-touch holdout). **FAIL** (2026-04-26). Held-out CE 0.4838 nats vs strongest baseline B0_always_prior 0.4748 — margin **−0.0090 nats** (need +0.005). 100k-perm p=0.0000 (model captures *some* signal) but always-prior baseline already extracts equivalent predictive value because σ=1.5 labels are ~85% neutral-class dominated. §9A fragility = FRAGILE (0/6 perturbations passed, all retrains converged to ~0.94 CE — extreme architectural fragility). §11B calibration-residualized margin −0.0028 nats. Amendments A1.1–A1.5 in force at terminal (sectoral indices, canonical universe pin, adjustment_mode, synthetic FII/DII waiver, data-driven regime check). Single-touch holdout consumed per §10.4. Run on Contabo VPS, ~99 min wallclock. Artifacts at `docs/superpowers/runs/2026-04-25-etf-stock-tail-h-2026-04-25-002/`.

##### Phase C intraday shape audit (SP1, descriptive forensics, 2026-04-25)

`pipeline/autoresearch/phase_c_shape_audit/` is a one-shot descriptive audit — not a hypothesis. It classifies the intraday shape of every Phase C OPPORTUNITY signal in the trailing 60 calendar days, replays each one across an entry-time grid (09:15/09:20/09:25/09:30/09:45 IST), and reports whether shape × side × regime separates winners from losers. Per spec (`docs/superpowers/specs/2026-04-25-phase-c-intraday-shape-audit-design.md`), the audit is descriptive-only: no kill-switch trigger, no hypothesis-registry append, no edge claim.

- **Entry:** `python -m pipeline.autoresearch.phase_c_shape_audit.runner [--end-date YYYY-MM-DD] [--days N] [--limit N]`
- **Roster source:** join of `pipeline/data/signals/closed_signals.json` (actual Phase C trades) + `pipeline/data/correlation_break_history.json` (full OPPORTUNITY universe — LAG/OVERSHOOT/POSSIBLE) + `pipeline/data/regime_history.csv` (canonical regime tag).
- **Bar source:** Kite `historical_data` minute candles for 09:15–15:35 IST, cached as parquet at `pipeline/data/research/phase_c_shape_audit/bars/<TICKER>_<YYYYMMDD>.parquet`. Re-runs are disk-only.
- **Shape labels:** REVERSE_V_HIGH, V_LOW_RECOVERY, ONE_WAY_UP, ONE_WAY_DOWN, CHOPPY (mutually exclusive, first-match-wins on the order in `features.classify_shape`).
- **Counterfactual replay:** `simulator.simulate_grid` runs each session through the entry grid with STOP=3% / TARGET=4.5% / TRAIL_ARM=2% / TRAIL_DROP=1.5% / HARD_CLOSE=14:30. Conservative tie-break — STOP fires before TARGET on the same bar.
- **Verdicts:** CONFIRMED, REGIME_CONDITIONAL_CONFIRMED, WEAK_SIGNAL, DISCIPLINE_ONLY, NULL, INSUFFICIENT_N (chosen by `report._pick_verdict` against MIN_CELL_N=10 and the baseline 56.4% closed-trade win rate).
- **Outputs:** `pipeline/data/research/phase_c_shape_audit/trades_with_shape.csv` (per-row roster with shape features + cf grid pnl), `missed_signals.csv` (subset with `source=missed`), and `docs/research/phase_c_shape_audit/<date>-shape-audit.md` (Tables A/B/F + verdict).
- **First run (2026-04-25, window 2026-02-24 → 2026-04-25):** roster 87 rows (5 actual, 82 missed), n_valid 71. Verdict **INSUFFICIENT_N** — no shape × side cell reaches MIN_CELL_N=10. Most missed-signal rows carry `trade_rec=nan` because POSSIBLE_OPPORTUNITY entries in `correlation_break_history.json` don't populate a directional rec. Re-run after the LAG slice forward sample grows.
- **Tests:** 26 SP1-specific tests across `tests/test_roster.py`, `test_fetcher.py`, `test_features.py`, `test_simulator.py`, `test_report.py`.

##### Mechanical 60-Day Replay (MR v1, descriptive forensics, 2026-04-25)

`pipeline/autoresearch/mechanical_replay/` re-runs the live execution rules over a 60-day historical window and produces a per-engine P&L attribution. Mandate: enter every signal at **09:30 IST**, hard-close at **14:30 IST**, apply our own ATR stop + ratchet trail + 20bps slippage. Per spec (`docs/superpowers/specs/2026-04-25-mechanical-60day-replay-design.md`), this is **forensics, not an edge test** — no hypothesis-registry append, no kill-switch trigger, no PASS/FAIL gating.

> **v1 scope reality:** v1 reads the live engine's stored Phase C roster (`correlation_break_history.json`) and regime tag (`regime_history.csv`) instead of regenerating them from canonical bars. Phase B + spread engines are not replayed. Z_CROSS exit channel is wired but not populated. Only the intraday 09:30→14:30 minute-bar walk is fully deterministic. v2 spec (`docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md`) closes the gap.

- **Entry:** `python -m pipeline.autoresearch.mechanical_replay.runner [--window-start YYYY-MM-DD] [--window-end YYYY-MM-DD] [--limit N] [--no-fetch] [--out-dir PATH]`
- **Universe:** `canonical_fno_research_v1` (154 tickers, dividend-adjusted) — anything outside is dropped, count logged.
- **Roster:** Phase C only in v1, sourced from `pipeline/data/correlation_break_history.json` joined with `pipeline/data/signals/closed_signals.json`. Phase B + spread engines are out-of-scope until roster.py is extended.
- **Bar source:** SP1's parquet cache at `pipeline/data/research/phase_c_shape_audit/bars/`. The replay reuses the SP1 fetcher as a passthrough — no fork.
- **Exit hierarchy** (most-conservative-first, mirrors live `signal_tracker.check_signal_status`):
  1. **ATR_STOP** — 14-day ATR × 1.0 with 3.5% absolute cap (intraday profile)
  2. **Z_CROSS** — caller-supplied timestamp (Phase C peer-relative neutralisation; deferred to v2)
  3. **TRAIL** — peak ratchet, arms at +2.0% (TRAIL_ARM_PCT), gives back 1.0% (TRAIL_GIVEBACK_PCT — 50% of arm, B9+B10 fix intent)
  4. **TIME_STOP** — last bar at/before 14:30 IST
- **Outputs:**
  - `pipeline/data/research/mechanical_replay/trades_with_exit.csv` — per-row ledger (signal_id, ticker, date, regime, side, exit_reason, pnl_pct, mfe_pct, entry/exit_time/price, stop_pct, atr_14, actual_pnl_pct).
  - `pipeline/data/research/mechanical_replay/engine_summary.json` — per-engine n / hit_rate / mean+total P&L / exit mix.
  - `docs/research/mechanical_replay/2026-04-25-replay-60day.md` — trader's one-pager: per-engine table + regime cube + exit breakdown + §10 sanity rollup + trader's read paragraph.
- **Sanity checks (descriptive, not gating):** coverage ≥95%, live cross-check ±2pp on ≥80% of overlap, ≥1 regime present. Coverage and live cross-check FAIL on the first run by design (most roster rows are POSSIBLE_OPPORTUNITY without a side; live entered at signal time, replay at 09:30).
- **First run (2026-04-25, window 2026-02-24 → 2026-04-24):** roster 24 rows (5 actual + 19 missed); 5 simulated; hit_rate 80%; total +4.34%. Exit mix TRAIL=4 / TIME_STOP=1. Regime split NEUTRAL 4/4 (+4.81%) / CAUTION 0/1 (-0.47%).
- **Tests:** 33 MR-specific tests across `tests/test_canonical_loader.py`, `test_atr.py`, `test_roster.py`, `test_simulator.py`, `test_report.py`.

##### Mechanical 60-Day Replay (MR v2, deterministic regen, 2026-04-25)

`pipeline/autoresearch/mechanical_replay/runner_v2.py` closes v1's reconstruction gaps. Every engine roster (regime, Phase C, Phase B, spread) is **deterministically regenerated** from canonical inputs — if `regime_history.csv` and `correlation_break_history.json` are deleted, v2 outputs are unchanged. Spec: `docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md`.

- **Entry:** `python -m pipeline.autoresearch.mechanical_replay.runner_v2 [--window-start YYYY-MM-DD] [--window-end YYYY-MM-DD] [--no-fetch] [--out-dir PATH]`
- **Modules** (all under `pipeline/autoresearch/mechanical_replay/reconstruct/`):
  - `regime.py` — sums weighted ETF returns through `phase_c_backtest.regime._compute_signal`, then quintile-buckets via frozen `regime_cutpoints.json`. Lookback extended to `window_start - 2y - 30d` so Phase C profile training sees full history.
  - `phase_c.py` — walk-forward profile (per-(symbol,regime) next-day return stats, 2y lookback) + shared `classify_break` decision matrix. POSSIBLE_OPPORTUNITY synthesizes `trade_rec` (LONG if expected_return>0, SHORT otherwise — FOLLOW-the-peer geometry).
  - `phase_b.py` — fires only on regime-transition days; ranks by `avg_drift_5d`, top-N longs + shorts.
  - `spread.py` — log(long/short) z-score over rolling 60-day lookback, regime-gated, |z| ≥ entry_threshold (default 2.0).
  - `zcross.py` — per-minute peer-relative residual recompute against sectoral indices, returns first sign-flip timestamp.
- **Cross-checks** (informational, not gating):
  - regime_vs_history_csv: ≥98% zone agreement
  - phase_c_roster_vs_history_json: ≥95% (ticker,date) overlap — **FAIL by design under §14 PCR contamination** (live archives stricter LAG-only set; v2 captures broader POSSIBLE_OPPORTUNITY because PCR archive missing → `classify_break` defaults to NEUTRAL → never reaches LAG)
- **Outputs:**
  - `pipeline/data/research/mechanical_replay/v2/regime_reconstructed.csv`
  - `pipeline/data/research/mechanical_replay/v2/phase_c_roster.csv`
  - `pipeline/data/research/mechanical_replay/v2/phase_b_roster.csv`
  - `pipeline/data/research/mechanical_replay/v2/spread_roster.csv`
  - `pipeline/data/research/mechanical_replay/v2/trades_with_exit.csv`
  - `pipeline/data/research/mechanical_replay/v2/engine_summary.json`
  - `docs/research/mechanical_replay/2026-04-25-replay-60day-v2.md`
- **First v2 run (2026-04-25, window 2026-02-24 → 2026-04-24):** regime cross-check 100% on 47 overlap rows (PASS). Phase C roster 2,076 rows of 6,006 events scored (LAG=0, POSSIBLE=2,076 under NEUTRAL-PCR). Phase B 340 basket rows. Spread 516 evaluations / 134 gate-OPEN. 2,416 trades simulated; only 9 had cached minute bars to fill (Phase B: 2 / Phase C: 7) — others retained as roster rows. Combined fillable sample: hit-rate 78%, total +5.14pp.
- **§14 binding contamination:** ETF weights (current snapshot, not as-of-D), trust scores not archived, **PCR archive missing** (the binding constraint that keeps Phase C at LAG=0), pair definitions not versioned. PCR backfill is the priority v3 work.
- **Tests:** 26 v2-specific tests added — `test_reconstruct_regime.py` (7), `test_reconstruct_phase_c.py` (5), `test_reconstruct_phase_b.py` (5), `test_reconstruct_spread.py` (5), `test_reconstruct_zcross.py` (4). All green alongside the 33 v1 tests.

##### Compliance runner: H-2026-04-24-003 (persistent-break v2 + cross-sectional)

- **Entry:** `python -m pipeline.autoresearch.phase_c_cross_sectional.runner`
- **Source:** `pipeline/autoresearch/phase_c_cross_sectional/`
- **Hypothesis:** v2 of H-2026-04-24-002. Lasso regression on 236-feature cross-sectional vector over asymmetric persistent-break events (`|z|≥3 on T AND |z|≥2 on T-1, same-sign`). Single-model family (Bonferroni α = 0.05).
- **Scheduling:** ad-hoc research, NOT a scheduled task.
- **Output:** `pipeline/autoresearch/results/compliance_H-2026-04-24-003_<stamp>/` with manifest, feature matrices, model, predictions, slippage grid, naive comparators, permutation null, fragility sweep (α × z_current × z_prior grid), §11B/§11C/§12 sections, §15.1 gate checklist.
- **Runtime:** ~10 min for 100k permutations on 8 cores.
- **H-2026-04-24-002 (abandoned) and the superseded v1 plan are historical context only:** see registry line 5 (`b50773f`) and `docs/superpowers/plans/2026-04-24-persistent-break-cross-sectional.md`.

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
| 08:00 | AnkaEarningsCalendarFetch | IndianAPI corporate_actions sweep, classify quarterly results, append parquet history. Feeds H-2026-04-25-001. | warn |
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
| 16:00 | AnkaTAScorerScore | TA Coincidence Scorer daily apply — writes `ta_attractiveness_scores.json` (RELIANCE pilot) | warn |
| 16:15 | AnkaEODTrackRecord | Write official track record, push website JSONs | warn |
| 16:20 | AnkaEODNews | Backtest news predictions | warn |
| 16:30 | AnkaBulkDeals | NSE rolling bulk + block deals CSV → daily parquet | info |
| 16:35 | AnkaTrustEOD | OPUS ANKA EOD review + next-day outlook | warn |
| 16:45 | AnkaWatchdogGate | Watchdog gate run — check everything | warn |
| 18:30 | AnkaInsiderTrades | NSE PIT (insider trading) disclosures, 7-day rolling pull | info |

Note: `website_exporter.py` is folded into morning_scan, every intraday cycle, eod_review, eod_track_record, and daily_dump — it is not a standalone scheduled task. Auto-pushes data/*.json to the GitHub Pages branch.

### Weekly

| Day/Time | Task Name | What It Does |
|----------|-----------|-------------|
| Saturday 22:00 | AnkaETFReoptimize | Reoptimize ETF weights with Indian data (Karpathy) | CRITICAL |
| Sunday 01:30 | AnkaTAScorerFit | RELIANCE TA model walk-forward fit — writes `ta_feature_models.json` |
| Sunday 22:00 | AnkaWeeklyAgg | Aggregate weekly spread statistics |
| Sunday 22:00 | AnkaWeeklyStats | Compute per-regime spread distributions via spread_statistics.py → pipeline/data/spread_stats.json |
| Friday 16:00 | AnkaWeeklyReport | Weekly performance report → Telegram |

**Path fix note (2026-04-22):** `spread_statistics.py` previously resolved `_DATA_DIR` to `askanka.com/data/` (wrong). Canonicalised to `pipeline/data/` to match `macro_stress.py` (writes `msi_history.json`) and `spread_intelligence.py` (reads `spread_stats.json`). Root `data/msi_history.json` was removed in commit `bb91a27`, so AnkaWeeklyStats had been silently running with an empty regime_map since that commit. Fix unblocks A2 bootstrap in the Anka Terminal Coherence plan.

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
