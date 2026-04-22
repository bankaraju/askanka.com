# Anka Research — Investor Deck v1

*Indian F&O trading intelligence, built clockwork-first.*
*Author: Bharat Ankaraju. Draft date: 2026-04-16.*

---

## Slide 1: Problem

SEBI's own published data shows 93% of Indian retail F&O traders lose money. The reasons are structural, not behavioural:

- **Fragmented data.** Price from Kite, fundamentals from Screener, filings from BSE, news from ten feeds, options OI from NSE. No one stitches them in a single decision loop.
- **No systematic edge.** Tips from Telegram channels, borrowed strategies from YouTube, scorecards without regime context. Retail participants don't know which signal works in which regime — so they trade all of them, all the time.
- **No risk discipline.** Stops are arbitrary percentages (3%, 5%, 10%). Position sizing is vibes-based. Exits are emotional. There is no track record because nobody is keeping one honestly.
- **Quality is not alpha by itself.** Our own scorecard-alpha test on 57 graded F&O names showed WEAK (D/F) stocks outperformed QUALITY (A/B) by 0.19%/10d overall in the last year. Good management is not a buy signal. Retail assumes it is.

The survivors of F&O are institutional desks with unified data pipes and hedged books. Retail is trading the same product with 10% of the infrastructure and none of the regime awareness.

*Speaker note: this isn't a marketing problem — it's a plumbing problem, and we're building the plumbing.*

---

## Slide 2: Solution / Product

**Anka Research is an end-to-end clockwork** that turns global regime signals into daily Indian-market trade baskets with honest, verifiable track records.

The system runs unattended on a published IST schedule:

- **04:30** — overnight global data dump + 31-ETF regime computation
- **09:15** — pre-market Telegram briefing
- **09:25** — morning scan: regime × spread statistics × technicals × OI × news × scorecard × Phase B ranker
- **09:30–15:30** — intraday scan every 15 minutes, signal generation, Phase C correlation-break detection
- **16:00** — EOD P&L capture, track-record update
- **16:30** — website data export, news refresh
- **Sunday 22:00** — weekly 5-year spread-statistics recompute

What the user sees: daily trade baskets on askanka.com with entry, stop, target, holding period, and a prose investment memo explaining *why* — anchored to the same 31-ETF ground truth that drove the trade. Telegram mirrors the same thesis; the terminal (localhost) is the operator cockpit.

**One story. Four surfaces. Same numbers. No contradictions.**

*Speaker note: the differentiator is the clockwork, not any single signal. Every signal is pre-committed to a schedule and a data file.*

---

## Slide 3: How It Works — 8-Layer Architecture

```
LAYER 1  Trust Scorecard        ── opus/run_trust_score.py           BUILT
LAYER 2  Pre-Announcement        ── bulk_deal_forensics.py (NSE)      BUILT
                                    options_monitor.py + pinning      BUILT
LAYER 3  Technical Filter        ── technical_indicators.py           BUILT
                                    (RSI, 20/50/200 DMA, MACD, ATR)
LAYER 4  News + Timing           ── news_intelligence.py              BUILT
                                    news_alerter.py (Telegram)        BUILT
                                    news_backtest.py (overnight)      BUILT
LAYER 5  Recommendation Engine   ── daily_recommendation.py           BUILT
                                    spread_intelligence.py (6 modules)BUILT
                                    reverse_regime (Phase A/B/C)      BUILT
LAYER 6  Trading Terminal        ── localhost:8888 FastAPI            BUILT
LAYER 7  Kite Execution          ── Kite place_order + GTT stops      TO BUILD
LAYER 8  Risk Monitoring         ── automated stop-loss + P&L track   PARTIAL
```

Sitting on top of all eight: the **31-ETF Global Regime Engine** (`autoresearch/`), computed overnight, that assigns today's zone (RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA) and gates which spreads are active.

**Core principle:** "Scorecard is the judge, news is the witness, technicals are the timing, bulk deals are the smoking gun."

*Speaker note: layers 1–6 are live. Layers 7–8 are the last-mile execution work.*

---

## Slide 4: Core Insights / Moat

Three findings the system is built on — each produced by running the experiment, not by assumption:

1. **Regime-conditional alpha.** Management grade alone is not alpha. Our scorecard-alpha test on 57 graded stocks across 1 year showed WEAK outperforms QUALITY by 0.19%/10d overall (p=0.21). Quality only wins in **NEUTRAL** regimes (+0.69%/10d). In **RISK-ON**, momentum eats quality. The moat is the regime filter, not the grade — and we've measured it.

2. **"All bad = good trade" (PSU sector spreads).** In PSU-heavy sectors (oil, banks, defence) management credibility is uniformly poor. Scorecard differences cancel out. Edge comes from sub-sector dynamics (upstream vs OMC, corporate bank vs PSU bank) plus technical timing plus OI positioning. A D-vs-D spread driven by sector mechanics can be high-conviction — and the system knows not to reject it.

3. **Credit markets lead India, not equities.** The 31-ETF engine (716 days, 2,000 weight combinations tested, 62.3% directional accuracy) shows HY corporate-bond ETFs are the strongest single predictor of next-day Indian markets. Equity-only MSI formulas are structurally lagging. We use credit as the lead trigger.

**Unified ETF-anchored content:** every surface (website, articles, terminal, Telegram) validates its market numbers against the ETF ground truth. A 10% miss disqualifies the content, not just the number.

*Speaker note: the moat is a library of honest negative results, not just positive ones. We know what doesn't work.*

---

## Slide 5: Data Stack

| Layer | Source | Role |
|---|---|---|
| **Prices (primary)** | Kite Connect | Real-time NSE, order routing |
| **Prices (historical)** | EODHD | 213-bar OHLCV, 100K calls/day cap |
| **Prices (fallback)** | yfinance | $0, full F&O universe downloaded |
| **Fundamentals** | indianapi.in | 280–380KB/stock: profile, 14-period financials, announcements, corporate actions |
| **Filings** | BSE + NSE scrapers | Bulk/block deals, insider transactions, pledge changes |
| **Macro / Regime** | 31 global ETFs (EODHD) | Overnight regime computation |
| **News** | IndianAPI + Google News RSS + 40+ YouTube channels | 632 events on first scan |
| **FII/DII flow** | NSE API | Daily institutional positioning |

**LLM routing (locked 2026-04-11):**

- **Gemini 2.5 Flash** — primary. Free tier + GCP cap. Used for PDF extraction, guidance scoring, news classification, article generation.
- **Haiku 4.5** — locked fallback. Proven on a 17-stock bake-off (16/17 flipped at ~$0.22/stock, ~$3.75 total).
- **OpenAI gpt-5.4-mini / OpenRouter** — emergency hatches only.

Per-batch cost: Gemini free ≈ $0, Gemini paid ≈ $6, Haiku ≈ $70, Claude Sonnet ≈ $230. We learned the hard way why this ordering matters.

*Speaker note: the stack is designed to run on a laptop — not a GPU cluster. Costs are measured per batch, not per month.*

---

## Slide 6: Traction — Shipped vs In-Flight

**Shipped (verifiable in the repo and session logs 2026-04-11 through 2026-04-15):**

- **213 F&O universe** fully onboarded. ~207/210 trust-scored (98.6%); remaining 3 are data-constrained, not model-constrained.
- **6-module Spread Intelligence Engine** (`spread_statistics`, `regime_scanner`, `technical_scanner`, `oi_scanner`, `news_scanner`, `spread_intelligence`) — 55 tests, 13 spreads, 26 scheduled Windows tasks.
- **Reverse Regime Engine (Phase A/B/C)** — 205 tradeable signals identified, daily ranker, correlation-break detector with OI confirmation. 68 tests.
- **News Intelligence Layer** — 632 events classified on first scan (47 HIGH, 585 MEDIUM), two-phase intraday alert + overnight verdict backtest.
- **31-ETF Regime Engine** wired as the primary regime classifier (demoted the old 5-input MSI to secondary).
- **Bloomberg-style terminal** at `localhost:8888` — narrative, spreads, basket, news, positions, heatmap.
- **Narrative generator** — LLM-produced daily investment memos (first real memo shipped 2026-04-12).
- **97 Windows scheduled tasks** registered and firing on the IST clockwork.
- **askanka.com** live with Global Regime Score hero, Live Positions table, research articles.

**In-flight:**

- Layer 7 Kite execution (limit orders from the terminal, GTT stop automation)
- Website Wave 2: ETF-anchored article workflow
- Stage 1 Closeout Gate (spec frozen 2026-04-10, implementation not started)
- Track-record accumulation (P&L tracker wired 2026-04-13, needs days/weeks to be meaningful)

*Speaker note: 30+ commits on 2026-04-12 alone. The repo is the proof.*

---

## Slide 7: Business Model / Distribution

**askanka.com** is the consumer-facing research product. Distribution is built around a single non-negotiable: the **no-hallucination mandate**.

**Published surfaces:**

1. **askanka.com homepage** — Global Regime Score hero, Live Positions table with real signal-file timestamps, daily research articles (war + markets + Epstein tracks). Hosted free on GitHub Pages.
2. **@ANKASIGNALS Telegram channel** — signal cards, pre-market briefings, EOD P&L, intraday alerts on state changes only (not noise).
3. **Weekly research** — backtested spread results, regime reviews, honest track-record leaderboard.
4. **Per-stock research pages** (`gen_stock_report.py`) — any of 213 F&O names on demand, powered by OPUS ANKA Trust Score + pipeline signals.

**Honest-metrics principle:** when a predecessor metric was wrong, we changed it publicly. The hero used to display "89.8% ML Accuracy"; when we realised the underlying model had 2.2% precision, we removed the claim. The current hero shows 4 honest track-record stats: 90+ Events / 35 Setups / 4 Yrs Backtested / 25 Pairs.

**Monetisation (direction, not yet priced):** Telegram subscription tier for live signals; institutional data-licence for the regime/scorecard feed; white-label advisory. Exact pricing <TBD: find exact figure>.

*Speaker note: we have a live, free, verifiable product. Monetisation is a second-order decision once track record compounds.*

---

## Slide 8: Roadmap — Next 90 Days

Committed in memory / specs, in priority order:

1. **2026-04-16 → 2026-04-20 — Wave 1 website push to master.** 11 commits on `feat/website-regime-score` branch. Global Regime Score hero live, stale articles stripped. Staleness of `fno_news.json`, `open_signals.json` triaged and fixed at source.
2. **2026-04-20 → 2026-04-24 — Wave 2 ETF-anchored article workflow.** Daily articles derive thesis *from* ETF ground truth, not *from* news. Automated numeric-validation pass; any failure rejects the whole article.
3. **2026-04-24 — ML MSI revisit (calendar-scheduled).** Pre-flight: verify `data/ml_performance.json` has ≥15 trading days. If clean, train XGBoost classifier to replace heuristic MSI. If sparse, push one week.
4. **Q2 — Stage 1 Closeout Gate implementation.** Frozen spec (1,627 lines, 9 blocking + 6 warning criteria) exists at `opus-anka/docs/superpowers/specs/2026-04-10-stage1-closeout-gate-design.md`. Read-only validation barrier between batch scoring and portfolio construction. Manifest with content-hash. 3-cycle manual rollout before `STAGE1_GATE_ENABLED` defaults on.
5. **Q2 — Layer 7 Kite execution + Layer 8 GTT stop automation.** Terminal → one-click limit order to Kite → GTT stop persisted → risk-monitor loop.
6. **Q2 — Index-vs-stock spreads.** Long best-scorecard stock, short BANKNIFTY / FINNIFTY future. Prerequisite is full 211 F&O scorecard batch complete. This is the "pure alpha extraction" structure.
7. **Q2 — Layer 3 Pre-News Anomaly Detection.** The real alpha — volume/OI/delivery/block-deal anomalies *before* news breaks. Builds on existing pre-announcement forensics.

*Speaker note: each item has a memory file, a spec, or a named script behind it. This isn't a wishlist.*

---

## Slide 9: Risks & Honest Gaps

Credibility comes from naming weaknesses, not hiding them.

**Data quality risks:**

- **Stale-data disqualification rule.** If a single market number is wrong by ~10% (e.g., "$103 oil" when spot is $93), the whole article is pulled — not just the number. We enforce this retroactively; multiple Apr 11–15 articles were pulled.
- **BSE RSS returning 404** as of 2026-04-14 — alternate corporate-announcement feed needs sourcing.
- **indianapi.in `/news` endpoint does NOT filter by stock** — returns same 20 articles for every symbol. Workaround: use `/recent_announcements` + EODHD news.
- **~153/210 stocks are INSUFFICIENT_DATA** on Trust Score — data pipeline gap (missing concall transcripts), not model gap. TRENT/LUPIN/HAVELLS explicitly flagged.

**Cost & operational risks:**

- **$90 Anthropic burn (2026-04-10)** on a single batch run — half wasted on a prompt bug returning 0 items. Triggered the Gemini-primary + Haiku-fallback lock. Never again.
- **$40 Gemini surprise charge** — hard billing cap now enforced at the provider level, not just in code.
- **HeyGen video pipeline:** ~$47 spent, 1 of ~15 attempts delivered (73-second clip). Credits drain on failures. Written-article fallback is the current production path. Alternative tools under evaluation.
- **Scorecard grade is NOT standalone alpha** (p=0.21 in our own test). Advertising it as such would be dishonest. We use it as a regime-conditional modifier only.

**Execution risks:**

- Layers 7–8 (live Kite execution, automated GTT stops) are not built yet. Signals are delivered; execution is manual.
- Track record accumulates slowly (one trading day at a time). Honest numbers require patience.
- Single-operator project today. No team redundancy.

*Speaker note: every failure above is documented in a memory file and linked from the MEMORY.md index. We don't forget the lessons.*

---

## Slide 10: The Ask

Anka Research is a working, shipping, clockwork-automated trading-intelligence platform for Indian F&O markets — built solo, with an aggressive bias towards verifiable numbers and honest track records.

**What we are looking for:**

- <TBD: capital amount> over <TBD: tranche horizon> to fund:
  - Layer 7/8 execution build-out (Kite live trade routing, GTT automation)
  - Data-quality hardening (concall transcripts, BSE filings backlog, news-source redundancy)
  - Operator redundancy (second engineer, on-call rotation for the clockwork)
  - Subscriber acquisition for the Telegram signal tier

**Ideal partners:**

- Family offices or prop desks that want a transparent, auditable Indian F&O overlay
- Data partners with institutional-grade NSE/BSE feeds
- Distribution partners with Indian retail reach (Telegram, YouTube, newsletter)

**What we are not asking for:**

- Marketing-led growth before track record compounds. Subscribers see honest metrics or none.
- Capital deployment into trades we haven't backtested. Every new signal is a hypothesis until the overnight loop validates it.

**Contact:** Bharat Ankaraju — bharatankaraju@gmail.com — askanka.com.

*Speaker note: this is the last slide. The pitch is the product. Open the terminal, open the website, open the Telegram channel — it all runs tomorrow at 04:30 IST whether we're in the room or not.*
