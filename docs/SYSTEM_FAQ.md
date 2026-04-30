# Anka System — FAQ

A living reference of Q&A about how the Anka research system actually works. Synthesized from session transcripts, design specs, and memory files. Updated on `/autowrap` each session.

> **Purpose:** stop re-asking the same questions across sessions. When something is asked and answered well in chat, it lands here.

**Last updated:** 2026-04-30 (late evening — backtest verdicts §17 appended)

---

## Table of contents

1. [Spread framework — old (news-driven) vs new (data-driven)](#1-spread-framework)
2. [ETF regime engine](#2-etf-regime-engine)
3. [Correlation breaks (Phase C)](#3-correlation-breaks-phase-c)
4. [TA scorer (Karpathy v1)](#4-ta-scorer)
5. [News pipeline](#5-news-pipeline)
6. [Holdout discipline (§10.4)](#6-holdout-discipline)
7. [Validation gates (§9 / §9A / §9B)](#7-validation-gates)
8. [Long-short pairing](#8-long-short-pairing)
9. [Live trade execution](#9-live-trade-execution)
10. [Universe definitions](#10-universe-definitions)
11. [Z-score — the trigger](#11-z-score)
12. [Technical indicators layer (the 10)](#12-technical-indicators)
13. [Stock selection pipeline (273 F&O → today's list)](#13-stock-selection)
14. [Why each test exists (pedagogical)](#14-why-each-test)
15. [Glossary of acronyms](#15-glossary)
16. [Skeletons audit Q&As (2026-04-30 evening)](#16-skeletons-audit-qa)
17. [Backtest verdicts (2026-04-30)](#17-backtest-verdicts-2026-04-30)

---

## 1. Spread framework

### Q: How do (legacy news-driven) spread trades get initiated? What's the trigger?

**A:** As of 2026-04-28 audit, the legacy spread framework triggers on news events classified by `pipeline/political_signals.py:generate_signal_card()`. Headlines flow through `news_verdicts.json`; if the verdict has `recommendation IN ('ADD', 'CUT')` and `impact IN ('HIGH_IMPACT', 'MODERATE')`, a spread fires from `pipeline/config.py:120-202` `INDIA_SPREAD_PAIRS`. **The audit found this pipeline is structurally broken** — all 314 verdicts in `news_verdicts.json` are `NO_ACTION`; 0 ADD, 0 CUT. The 04-27 spread trades that opened on "Lebanon drone" / "Hengli sanctions" headlines came from elsewhere (likely cached fixtures or older paths), not a fresh news-classifier output.

### Q: Did PCR/OI move post-news (reactive) or were they already loaded (predictive)?

**A:** Mixed. On the 04-27 cohort: ICICIBANK was already PCR>1 pre-news; TMPV was already put-heavy on next-month; ONGC turned bearish post-news; M&M had the cleanest reactive build. The post-hoc narrative "PCR was loaded, news activated it" is overstated — the live system never reads PCR at signal-generation time, so no causal chain was actually being followed.

**Key learning:** caught the trade by luck, not by framework. The right capture is delta-PCR (next-month, 2-day cumulative) BEFORE the news, not after.

### Q: Why next-month PCR instead of near-month?

**A:** Near-month PCR gets distorted by expiry rollover in the last 1–2 weeks of any expiry cycle. Next-month is unaffected by rollover and reflects the durable positioning bet. Always read next-month for delta-PCR signals.

### Q: What is replacing the news-driven framework?

**A:** `H-2026-04-29-intraday-data-driven-v1` (twin: stocks pool + indices pool). 6-feature Karpathy-fit pooled-weight model on NIFTY-50 stocks + options-liquid index futures. Single-leg directional V1; long-short pairing in V2 after V1 passes. See `docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md`.

### Q: When does the news-driven framework get killed?

**A:** On V1 holdout pass (verdict by 2026-07-04). Specifically, the kill switch flips in `pipeline/political_signals.generate_signal_card()` and `pipeline/run_signals._run_once_inner()`. `INDIA_SPREAD_PAIRS` renames to `INDIA_SPREAD_PAIRS_DEPRECATED`. All open positions close at the next 14:30 mechanical exit. Ledgers archive to `pipeline/data/research/news_driven_archive_2026_07/`. If V1 fails, the news-driven incumbent stays running — V1 returns to drawing board.

---

## 2. ETF regime engine

### Q: What does the ETF regime engine actually do?

**A:** Reads daily returns / RSI / 5-day momentum on a curated set of ~30 global ETFs (ETF v3 `curated_30` feature set), feeds 37 features into a logistic-regression-style classifier, outputs one of {RISK_ON, RISK_OFF, NEUTRAL} regime zones for the trading day. Production model: `pipeline/autoresearch/etf_v3_curated_optimal_weights.json`. Best in-sample accuracy 56.9%, Sharpe 1.91. Two features dominate the weight vector: `mchi_ret_5d` (-58.1) and `iwm_ret_5d` (+45.1). Together they account for >99% of total weight magnitude.

### Q: NIFTY was excluded from the ETF basket — confirm?

**A:** Partially correct. NIFTY-related features (`nifty_ret_1d`, `nifty_ret_5d`, `nifty_rsi_14`) are physically present in the v3 curated_30 feature set but the optimizer assigned them effectively zero weight (-0.0003 to -0.00003). So the optimizer "excluded" NIFTY as a predictor by assigning ~0 weight, while the curation list still includes NIFTY. The intent ("NIFTY is being predicted, can't also be a predictor") is reflected in zero-weight, not in absence from the feature list.

### Q: Was the old ETF v2 engine claim of 62.3% accuracy real?

**A:** Dead. ETF v2 retested at any feature count yields 47–49% accuracy. The 62.3% number is a hindsight artefact (training data leakage in the way `regime_history.csv` was built). Per `reference_regime_history_csv_contamination.md`: "regime_history.csv is built with HINDSIGHT v2 weights, NOT a production audit trail." Do not use it for OOS comparisons. ETF v3 + curated_30 is the current production model.

### Q: How often does the ETF basket get re-optimized?

**A:** Saturday 22:00 IST weekly via `AnkaETFReoptimize`. The weight vector is allowed to drift; the curation list (which 30 ETFs to consider) is changed manually with deliberation, not auto.

---

## 3. Correlation breaks (Phase C)

### Q: What does Phase C actually do?

**A:** Reads ~60-day rolling correlation of each F&O stock against its sector regime; when |z-score| ≥ 4σ, registers a "correlation break event." The event slice is split into `OPPORTUNITY_LAG` (continuation direction) vs `OPPORTUNITY_OVERSHOOT` (fade direction). Per `project_phase_c_follow_vs_fade_audit.md` (#107 audit, 2026-04-23): both slices fail Bonferroni at the strict gate; live routes only LAG. Per the mechanical 60-day replay (`project_mechanical_60day_replay.md`, 2026-04-25): `POSSIBLE_OPPORTUNITY` slice +41.67pp/n=328 BEATS `OPPORTUNITY_LAG` -3.30pp/n=60. The 04-23 audit kept the wrong slice live-tradeable; the replay engine is the more honest read.

### Q: What's the kill criterion for Phase C?

**A:** Per `project_phase_c_kill_criteria.md`, kill-line set 2026-04-27: edge < 100 bps OR win < 55% on 100+ forward trades → archive Phase C, pivot to gap-fade / pair-trade overlays. Currently Phase C is in the validation window; verdict TBD as forward trades accumulate.

### Q: Does Phase C overlap with the spread trades?

**A:** No. Phase C trades single-leg directional positions on ATR(14)×2 stops. Spreads are pair trades. Different signal generators (`pipeline/break_signal_generator.py` vs `pipeline/political_signals.py`). The 14:30 IST cutoff applies to both for new opens; existing positions are monitored regardless.

---

## 4. TA scorer

### Q: Why per-stock Lasso instead of pooled?

**A:** `H-2026-04-29-ta-karpathy-v1` is a per-stock Lasso L1 logistic regression with 4-fold walk-forward + BH-FDR permutation null + qualifier gate. Honest expectation written into the spec: 0–3 of 10 NIFTY stocks qualify. Per-stock structure was chosen because TA features (RSI, MACD, BB position) are believed to behave differently per stock. Predecessor `H-2026-04-24-001` already failed on RELIANCE — distinct family widening was the deliberate response.

### Q: Why is `H-2026-04-29-intraday-data-driven-v1` choosing pooled instead of per-stock when TA Karpathy chose per-stock?

**A:** Different feature set, different intent. TA Karpathy is exploring per-stock structural differences in technical indicators. The new intraday framework is testing whether a small set of intraday features (delta-PCR, ORB, volume, VWAP, RS, trend-slope) admit a *steady* universe-wide weight vector. The user's stated mandate ("keep weights relatively steady, recalibrate monthly") explicitly favors pooled. Both architectural choices are pre-registered, both will be evaluated on their own holdouts.

---

## 5. News pipeline

### Q: Is the news pipeline working?

**A:** **No, structurally broken as of 2026-04-28.** Three findings:

1. `data/fno_news.json` (public website) is **2 bytes (`[]`)** — empty.
2. `pipeline/data/fno_news.json` is **76KB but stale 6 days** (last write 2026-04-22). Deprecated path per code comment.
3. `pipeline/data/news_verdicts.json` is **152KB and fresh today** but has **314/314 NO_ACTION verdicts** — 100% of events graded as no-impact, 0 ADD, 0 CUT.

`website_exporter.export_fno_news()` filters verdicts to `recommendation IN ('ADD', 'CUT')` — zero rows pass → empty file exported. The classifier itself is dead. Pre-existing issue tracked in commit `8f6333e docs(news): audit why news_verdicts.json grades every event NO_IMPACT (#37)`.

### Q: Where did the 04-27 "Lebanon drone" / "Hengli sanctions" headlines come from?

**A:** Not from the live news classifier (which would have graded them NO_ACTION too). Likely from cached headlines in `political_signals.py` test fixtures or an older snapshot. Traced as part of the deprecation work — the news-driven framework was always running on partly-stale or partly-fixture data. **This is the smoking gun that justifies the framework deprecation.**

### Q: When will news pipeline be fixed?

**A:** Not in the V1 framework's scope. The `news_classification` task in the Gemma 4 pilot routing config (`pipeline/config/llm_routing.json`) was set to shadow Gemini's classifier output for 20 days starting 2026-04-29 — but since the underlying classifier is dead, the pilot's pairwise scoring on this task will be meaningless. Recommendation: drop `news_classification` from Gemma pilot scope until the upstream classifier is fixed; other 3 tasks (concall, EOD narrative, article draft) proceed unchanged.

---

## 6. Holdout discipline

### Q: What does "single-touch holdout" mean?

**A:** Per `backtesting-specs.txt §10.4` strict: once a hypothesis spec is registered and its holdout window starts, **no parameter changes** may be applied during the window. Adjusting features, thresholds, or model after seeing intermediate holdout performance corrupts the OOS test. The window can be extended for infrastructure-failure days (e.g., Kite session expired), but never shortened or re-fitted mid-flight. Single-touch = one shot; if it fails, the hypothesis is consumed and a new spec must register a different (named, non-trivial) variation.

### Q: What counts as a "trivial" variation that doesn't earn a fresh holdout?

**A:** Re-running with adjusted threshold values (e.g., 70th percentile → 65th percentile) on the same feature set is trivial — the holdout has already been seen, the adjustment is over-fitting to it. A non-trivial variation is a different *family* (different features, different model class, different objective). Predecessor `H-2026-04-24-001` failed; `H-2026-04-29-ta-karpathy-v1` is a "distinct family widening" — same broad TA-features intent but different model class (Lasso vs Karpathy random search) and different univ universe (1 stock pilot vs 10 stocks).

### Q: What's the "bug-fix touch" exception?

**A:** If a code-level bug is discovered that contaminates the holdout (e.g., off-by-one in feature compute), the fix may be applied with a public log entry documenting before/after. This consumes the bug-fix touch — any further fixes invalidate the holdout. Precedent: `project_h_001_regime_bug_2026_04_27.md` (Day-1 holdout bug, 26 rows backfilled, documented).

---

## 7. Validation gates

### Q: What is §9A Fragility?

**A:** Robustness gate: perturb the model's parameters (e.g., weight vector components) by ±10%, recompute holdout performance under each perturbation. Required: ≥4 of 6 (or 4/12 in the v1 spec) perturbations remain Sharpe-positive AND hit-rate > 50%. Below this = FRAGILE = FAIL regardless of other gates passing. Catches over-optimization that crumbles on small parameter changes.

### Q: What is §9B Margin?

**A:** Hit-rate margin gate: the framework must beat the better of "always go long" / "always go short" baselines by ≥ 0.5pp. This prevents passing the §9 hit-rate gate trivially via market drift (e.g., NIFTY went up so always-long would also clear 53%). H-2026-04-25-002 failed on §9B with margin -0.0090 vs always-prior — the model couldn't beat a trivial baseline.

### Q: How does BH-FDR work for multi-stock tests?

**A:** Benjamini-Hochberg controls the false-discovery rate at q=0.05 across N simultaneous tests. Sort p-values ascending; reject p_(i) iff p_(i) ≤ (i/N) × q. Useful when testing 50 stocks each with their own per-stock null — without correction, you'd expect ~2.5 false positives at α=0.05 just by chance. BH-FDR keeps the expected proportion of false positives among rejected hypotheses ≤ q.

---

## 8. Long-short pairing

### Q: Why single-leg first, pairing later?

**A:** User's framing 2026-04-28: "before we put them as spread trades, lets us first find out if our framwork is good and then think of long short -- the reason for long short is to keep risk less and generate higher alpha for the same risk -- usually end up with higher sharpe ratios." Validating each leg independently catches a broken framework cheaply; pairing on top of a broken framework just hides the brokenness in basket-level Sharpe. Once V1 single-leg passes, V2 layers pairing rules — the single-leg signal becomes the *score* used to construct top-quartile-long / bottom-quartile-short baskets.

### Q: How does cross-class pairing work in V2?

**A:** Stocks-pool and indices-pool each have their own Karpathy weight vector and per-instrument scoring. At basket construction, scores are z-normalized within each pool, then merged into a single ranked list of 60 instruments. Top-quartile (best 15) goes long; bottom-quartile (worst 15) goes short; middle 30 are skipped. Cross-class pairs (e.g., long RELIANCE / short NIFTY) emerge naturally when stock-and-index scores diverge across the same direction. V2 spec written after V1 verdict.

### Q: Why not test pairing in V1?

**A:** Two reasons. (1) §10.4 single-touch — V1 has one shot, can't burn it on a multi-component test where pairing math is entangled with single-leg signal quality. (2) Pairing introduces variance-reduction that could mask single-leg failure: a basket can have positive Sharpe even if individual legs are 50/50, just from variance dampening. Need to know the single-leg signal is real before celebrating pair Sharpe.

---

## 9. Live trade execution

### Q: Are V1 trades real money or paper?

**A:** **Paper-only.** Both V1 stocks and V1 indices write to `recommendations.csv` at Kite LTP at entry and exit. No real capital. The user has paused all real-money trading per `feedback_website_trade_publish_blocked.md` (re-validation in progress since 2026-04-26). Public website does NOT show trades / positions / track record — these stay locally until V1 + Tier 1 null both clear.

### Q: Why mechanical 14:30 IST exit?

**A:** Eliminates overnight risk. Per `feedback_1430_ist_signal_cutoff.md`, no live engine opens new positions after 14:30 IST because mechanical TIME_STOPs run at 14:30 — anything later has under 60 min of execution window. New-signal cutoff is enforced at source in `run_signals.py`, `break_signal_generator.py`, `arcbe_signal_generator.py`. V1 inherits the same discipline.

### Q: What's the protective stop?

**A:** ATR(14) × 2.0 per-instrument. Computed at entry time using the prior 14 trading days' ATR from `pipeline/data/fno_historical/`. Monitored on Kite LTP every 5 min. If breached, position closes at trigger price (paper); 14:30 mechanical exit ignored for that position. Same standard as H-001, SECRSI, Phase C.

### Q: What's the position sizing rule in V1?

**A:** Equal-weight across all firing signals. If 12 instruments fire on a given day, each gets 1/12 of basket capital. Karpathy weight vector decides *which* instruments fire (via score threshold), not *how much* to size each. Sizing-as-second-optimization is a V2 question.

---

## 10. Universe definitions

### Q: How many stocks are in the F&O universe?

**A:** Depends on which definition. As of 2026-04-29:
- **Internal `opus/config/fno_stocks.json`:** 213 (likely stale)
- **NSE-published F&O membership (latest snapshot 2026-03-30):** 206
- **PIT ticker pool with name-changed historical aliases (`docs/superpowers/specs/tickers list .xlsx`):** 239

History trend: 2024-01: 183 → 2024-11 jump to 223 (NSE expansion) → 2025-01 peak 227 → drift down to 206 by 2026-03. NSE has been expanding F&O steadily; "250+" claims are forward-looking, not current state.

### Q: What's the V1 universe?

**A:** NIFTY-50 stocks + ~8–12 index futures clearing the options-liquidity gate. Frozen at 2026-04-29 09:30 IST. Universe expansion to full F&O is V1.1 (V2 component) after V1 passes. See spec §2.

### Q: What's the options-liquidity gate?

**A:** A stock or index qualifies for V1 (and later V1.1) if its options market satisfies: median ATM call+put daily volume ≥ 5,000 contracts; near-month total OI ≥ 50,000 contracts; median ATM bid-ask spread ≤ 1.5% of premium; ≥5 strikes with non-zero volume on each side. Computed once at kickoff from prior 20 trading days of `pipeline/data/oi/` snapshots.

---

## 11. Z-score

### Q: What is the Z-score in plain English?

**A:** Z = how many standard deviations a number is away from its rolling mean. If a stock's correlation with its sector usually sits between 0.4 and 0.6, and today it dropped to 0.1, that's *unusually* far from normal. The Z-score quantifies "unusual" — Z=2 means "two standard deviations below the rolling mean," i.e. an event that happens roughly 2.5% of the time under a normal distribution.

In Anka, Z-score is computed on **a 60-day rolling window** of the daily correlation between each F&O stock and its sectoral regime. The break engine fires when |Z| ≥ 2.0.

### Q: Why ±2σ specifically — not ±1σ or ±3σ?

**A:** Empirical, not theoretical. Tested at multiple thresholds in the mechanical 60-day replay:
- **±1σ** fires too often (~32% of stock-days), no edge — the signal becomes noise.
- **±2σ** fires ~5% of stock-days, gives the H-001 forward sample of 105 trades in 3 days. Edge is positive (+0.225% mean, 59% wins on NEUTRAL).
- **±3σ** fires <1% of stock-days; sample too thin to validate within a holdout window.

±2σ is the sweet spot of "rare enough to be meaningful, common enough to validate." Any future change to the threshold consumes a fresh single-touch holdout per §10.4.

### Q: Where in the pipeline does Z-score fire?

**A:** Three places:
1. **`pipeline/break_signal_generator.py`** — live intraday break detection, every 15 min during market hours. Reads current correlation, computes Z, fires `BRK-<date>-<ticker>` row if |Z|≥2 and 14:30 cutoff hasn't passed.
2. **`pipeline/h_2026_04_26_001_paper.py`** — at 09:30 IST, sweeps yesterday's overnight Z values, opens paper positions on |Z|≥2 NEUTRAL-regime breaks. Closes 14:30 mechanical.
3. **`pipeline/autoresearch/mechanical_replay/runner_v2.py`** — historical replay over 60 days, same Z computation rule applied to every (ticker, day) pair to reconstruct what live would have seen.

### Q: What window is the Z-score rolling on?

**A:** **60 trading days** for the correlation Z. Matches the Kite 1-min historical API's 60-day rolling cap, so live and replay see the same window length. Why 60 days specifically: long enough that a single regime shift doesn't dominate, short enough that the rolling mean tracks the recent market state. Tested vs 30/90/120 in the 04-25 replay sweep — 60 had the cleanest separation between signal and noise.

### Q: What's the "regime gate" on top of Z-score?

**A:** A second filter: `regime_gate_pass = True` requires the day's ETF regime ≠ NEUTRAL. H-002 reads only those rows. The hypothesis is that breaks fire more cleanly when the broad regime is risk-on or risk-off than when the regime is undirected (NEUTRAL). Currently can't be evaluated — every day since 2026-04-22 has been NEUTRAL, so the H-002 gate is closed and all 105 trades have routed through H-001 (unconditional).

---

## 12. Technical indicators

### Q: What are the "10 technical indicators" the system uses?

**A:** The current production set of intraday confirmation features, layered on top of the Z-score signal:

| # | Indicator | Window | What it captures |
|---|---|---|---|
| 1 | **VWAP deviation (signed)** | 09:15→09:30 | how far open price has drifted from cumulative VWAP, signed by trade direction |
| 2 | **ORB-15min %** | 09:15→09:30 | high-low range as % of open — wide = volatile, tight = compression |
| 3 | **Volume Z** | 09:15→09:30 vs 20-day | first-15-min volume vs trailing 20-day mean of same window |
| 4 | **Intraday slope %** | 09:15→09:30 30 closes | linear regression slope of 30 1-min closes, normalized to open price |
| 5 | **Bollinger position** | daily BB(20,2) | z-position of today's open within yesterday's Bollinger envelope (PENDING — being added) |
| 6 | **ATR(14)** | daily, 14-day | average true range — protective stop multiplier (×2.0 in production) |
| 7 | **RSI-14** | daily | momentum oscillator; ≥70 overbought, ≤30 oversold |
| 8 | **MACD signal cross** | daily 12/26/9 | trend-direction confirmation |
| 9 | **delta-PCR (next month)** | 2-day cumulative | options positioning shift on next-month chain — early conviction signal |
| 10 | **Sectoral RS** | 09:15→09:30 vs sector index | relative strength of stock vs its NSE sectoral index over the morning |

### Q: How do they enhance the Z-score signal?

**A:** Z-score alone says "something rare happened." The technical layer asks "in which direction is the rarity confirmed by other evidence?" Empirically, on the H-001 forward sample of 105 NEUTRAL trades:

- **Z-only (no filter):** 59.05% wins, +0.225% mean
- **Z + VWAP cooperative direction (KEEP cell):** 64.71% wins, +0.397% mean — this single filter alone adds **~6pp** on n=85
- **Z + VWAP rejected (DROP cell):** 35.00% wins, -0.502% mean — confirms the filter is doing real work
- **Z + ORB_HI + VWAP cooperative:** 92% wins on n=13 (MONITOR — too small to claim PUBLISH)

The technical layer is not a separate signal; it is a *filter* on the Z-trigger. Interpretation: Z-score is necessary but not sufficient — the technical layer separates good Z from noise Z.

### Q: Why is the VWAP filter the strongest cell?

**A:** Two structural reasons:
1. **VWAP is the institutional reference price.** When price is already extended past VWAP at 09:30 in the trade direction, it usually means the institutional flow has *already moved* — there's no fresh imbalance for the fade to capture. Skipping these saves you from buying the top / selling the bottom of the institutional impulse.
2. **VWAP captures the morning auction discovery.** First 15 minutes of trading is the price-discovery window where overnight news + Asia + futures gap are absorbed. By 09:30, VWAP shows where the "agreed price" settled. Trades that fade *into* this agreement (price already at VWAP) tend to win; trades that fade *across* it (price extended away) tend to lose.

### Q: Why is Bollinger position still PENDING?

**A:** Per `memory/project_neutral_overlay_family_2026_04_28.md` and ANALYSIS_CATALOG §A.3: backfill in flight 2026-04-29. Hypothesis: "long fade when price is below the lower BB band creates an additional PUBLISH cell on top of VWAPSIGN_LO." Pending feature engineering + 30+ forward closed trades to validate. Currently 0 closed BB-tagged trades.

### Q: How does Volume-Z catch real signals vs noise?

**A:** Volume-Z compares today's 09:15-09:45 volume to the trailing 20-day mean of the same window. A Z-score of +2 means "today's morning volume is 2σ above its 20-day norm" — usually news-driven or institutional accumulation. The intraday panel v1 backtest found ALL/fade with high volume-Z does **not** outperform — pure volume isn't directional. But volume-Z paired with VWAP direction sometimes is. Treated as a context indicator, not a standalone signal.

### Q: Why ATR×2 for stops, not a fixed %?

**A:** A fixed 1% stop on a low-vol stock (ATR=0.4%) is a noise-stop — gets hit by routine wiggle. The same 1% on a high-vol stock (ATR=1.5%) doesn't give the trade room to breathe. ATR×2 sizes the stop to the *stock's own historical volatility* — same statistical "noise tolerance" applied to every name. ×2 was tested vs ×1.5 and ×3 on Phase C: ×2 gave the best ratio of (winners protected / losers cut early).

---

## 13. Stock selection

### Q: From 273 F&O stocks down to today's 5-10 trade candidates — what's the funnel?

**A:** Step by step:

1. **Universe input: 273 F&O canonical** — `pipeline/config/canonical_fno_research_v3.json`. This is the Anka-curated PIT-correct list (handles 5 active aliases like GMRINFRA→GMRAIRPORT). NSE's official F&O list is 206; Anka's 273 includes the historical names that traded F&O during the 5-year backtest window.

2. **Daily data freshness cut:** drop names where the 1-min cache is stale > 1 trading day. Currently 269/273 stocks survive (4 dropouts on 2026-04-29: LTIM has no Kite alias; PEL+SAMMAAN are Kite-only with EODHD gaps; one rotational dropout per day).

3. **Sectoral mapping:** each surviving ticker is mapped to one of ~25 NSE sectoral indices via `pipeline/sector_mapper.py`. Stocks with `sectoral_index=UNKNOWN` are excluded from break detection (currently a known issue affecting 100% of H-001 holdout rows — task #42 pending diagnosis).

4. **Z-score sweep:** for each (ticker, day), compute the 60-day correlation Z of stock-vs-sector. Names with |Z| ≥ 2.0 fire as break candidates. Typical day: 5-15 names fire.

5. **Regime gate:** the day's ETF regime is read from `pipeline/data/today_regime.json`. H-001 ignores regime; H-002 only opens trades when regime ≠ NEUTRAL (currently 0 opens — regime has been NEUTRAL 8+ days).

6. **Direction tag:** each candidate is tagged LONG or SHORT based on the sign of the correlation deviation. This becomes the trade side.

7. **Technical filter (display-only during holdout):** the VWAP-deviation tag adds KEEP / DROP / WATCH cell membership. Currently DISPLAY-ONLY on the terminal, NOT live-gated — promotion to gating requires fresh hypothesis post-2026-05-26 holdout.

8. **14:30 cutoff:** any candidate that fires after 14:30 IST is silently dropped — see `feedback_1430_ist_signal_cutoff.md`.

9. **Output:** the surviving names land in `pipeline/data/research/h_2026_04_26_001/recommendations.csv` as `BRK-<date>-<ticker>` rows. Paper open at Kite LTP. 14:30 mechanical close. Yesterday's run produced ~25-35 such trades per day.

### Q: How many of the 273 actually trade in a typical day?

**A:** On the H-001 NEUTRAL forward sample (3 days, 105 trades): ~35 distinct tickers per day fire on |Z|≥2. Of those ~35:
- ~21 are tagged LONG, ~84 are tagged SHORT — a real asymmetry; the framework is currently more sensitive to short-side breaks
- ~85 (KEEP cell) survive the VWAP cooperative-direction filter
- ~20 (DROP cell) get filtered out

So the *full pipeline* output is ~35 trades/day open at 09:30, ~85% of which would survive the (display-only) VWAP filter to become "high-conviction."

### Q: Why is H-001's `sectoral_index` UNKNOWN on 100% of holdout rows?

**A:** Live bug in the H-001 paper engine — the sectoral mapping step is not being applied at signal-write time. Tracked as task #42. Doesn't break trades (the Z-score itself fires correctly via the live correlation engine), but it prevents per-sector cell aggregation in the cohort tracker. Fix is mechanical — call `sector_mapper.map_one(ticker)` at row-write time.

---

## 14. Why each test

### Q: What is each validation gate actually catching?

| Gate | Section | What it catches | Real-world example |
|---|---|---|---|
| **§9 baseline (hit-rate p<0.05)** | core | Random-chance results that look like edge | If you flip a coin 100 times you'll see one 10-streak. p<0.05 against a binomial null says your win rate is unlikely under chance |
| **§9A Fragility (perturb)** | robustness | Over-fit weights that crumble on tiny parameter changes | A model that reaches 65% at weight=0.50 but 51% at weight=0.55 is fitting noise. ≥4/6 perturbations must stay Sharpe-positive |
| **§9B Margin (vs always-long/short baseline)** | trivial-baseline | Hit rates that look good only because the market drifted | NIFTY went up 4% during your test → "always go long" hits 56% on its own. Must beat that by ≥0.5pp to count |
| **§9.5 Sharpe ≥ 0.5** | risk-adj | Strategies with lottery-ticket P&L profile (one big win hides 9 losses) | Sharpe forces consistency — a 65% win rate with -5% one-day drawdown might still fail |
| **§10.1 MaxDD ≤ 5%** | tail-risk | Strategies that work on average but blow up periodically | A model that produces 70% wins with one -8% week fails — the drawdown disqualifies |
| **§10.4 Single-touch holdout** | overfitting | Researcher iterating on the holdout set itself | If you test 20 versions of a model on the same OOS window, you're fitting OOS. One shot per spec, no re-fits |
| **BH-FDR (multi-stock)** | multiple-testing | False positives from testing many stocks | Test 50 stocks at α=0.05 → 2.5 false rejects expected. BH-FDR keeps expected false-discovery rate bounded |
| **Decade splits** | regime-stability | Strategies that work in one decade and fail in the next | If 2014-2018 prefers fade-low-vol and 2019-2024 prefers fade-high-vol, the strategy is a regime artefact |

### Q: Why so many gates — isn't one or two enough?

**A:** Each gate catches a different failure mode. Hit-rate alone passes lottery-ticket strategies (§9.5 Sharpe catches them). Sharpe alone passes hindsight-fitted models (§9A Fragility catches them). All gates passed but on a single-decade sample passes regime-artefact (decade-split catches it). The "so many gates" is intentional defense-in-depth — H-2026-04-25-002 passed §9 hit-rate but failed §9A (0/6 fragility) AND §9B (margin -0.0090); without those two gates we'd have wasted a holdout slot on a fragile / no-margin model.

### Q: What's the cost of being this strict?

**A:** Most pre-registered hypotheses fail. Of 6 hypotheses pre-registered since 2026-04-23: 4 DEAD (TA-Karpathy v1 RELIANCE, persistent-break v2, earnings-decoupling, etf-stock-tail), 1 POSTPONED (intraday data-driven V1), 1 ACTIVE (sigma-break mechanical, current 105-trade NEUTRAL sample). That's a ~17% pass rate. The user's stance: "winning shadow trade ≠ edge; validate fade direction against 5-yr per-ticker bootstrap null before claiming alpha" (`feedback_alpha_vs_timing_luck.md`). Strictness is the price of not deploying false-edges with real money.

### Q: Why decade-split / OOS holdout — isn't 60-day backtest enough?

**A:** No. 60-day backtest = one regime, one news cycle, one global macro state. A strategy that works on the 60-day replay might be capturing the specific regime of those 60 days (e.g. NEUTRAL stable). Decade-split tests force the strategy to survive multiple regime classes. OOS holdout tests force it to survive *unseen future data* (the harder test). Both are necessary — neither alone is sufficient.

### Q: Why are some tests "report-only" before "gate-blocking" (e.g. Deflated Sharpe)?

**A:** When a metric is new or its threshold is uncertain, ship it report-only first. Collect 30+ holdout-cycles of data on what passes vs fails. Only then promote to gate-blocking with an empirically-calibrated threshold. Per `H-2026-04-29-ta-karpathy-v1` spec v1.1: "Deflated Sharpe metric report-only at v1, gate-blocking at v2 when N≥100 days." Report-only avoids prematurely killing hypotheses on a metric whose pass/fail line we don't yet trust.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **ATR(14)** | Average True Range over 14 trading days; volatility measure |
| **BH-FDR** | Benjamini-Hochberg False Discovery Rate correction for multiple testing |
| **delta-PCR** | 2-day cumulative change in put/call OI ratio on next-month options |
| **F&O** | Futures and Options (NSE's derivatives universe) |
| **Holdout-of-record** | The single ledger that decides hypothesis pass/fail per §10.4 |
| **IST** | Indian Standard Time (UTC+5:30) |
| **Karpathy random search** | Random sampling over weight space, retain best per objective |
| **LTP** | Last Traded Price (Kite live feed) |
| **MaxDD** | Maximum drawdown — peak-to-trough cumulative P&L decline |
| **MSI** | Market Sentiment Index (legacy heuristic, replaced by ETF regime) |
| **OI** | Open Interest on options/futures contracts |
| **OOS** | Out-of-sample (holdout) |
| **ORB** | Opening Range Breakout — first-15-min %move from open |
| **PCR** | Put-Call Ratio (put OI / call OI on options chain) |
| **PIT** | Point-in-time (no future data leakage) |
| **RS** | Relative Strength (instrument vs sector / vs benchmark) |
| **Sharpe** | Annualized risk-adjusted return: mean(r) / std(r) × √252 |
| **VWAP** | Volume-Weighted Average Price (intraday) |
| **§9A** | Fragility gate (perturb-and-retest) |
| **§9B** | Margin-vs-baseline gate |
| **§10.4** | Single-touch holdout discipline |

---

## 16. Skeletons audit Q&A

These Q&As emerged from the 2026-04-30 evening session "let's open every cupboard". Companion document: `docs/SYSTEM_SKELETONS_AUDIT.md`.

### Q: Why was `AnkaUnifiedBacktest` showing ~777 trading days when we'd standardized everything else on 5 years?

**A:** The change to 5y was applied across F&O CSVs, Pattern Scanner, TA Fingerprint, correlation forensics, sector_panel, sector_correlation studies — but NOT to `pipeline/autoresearch/unified_backtest.py`. That file was last edited at its original commit (`01d08f3`) and stayed on `days=1095` (3y default in `_fetch_etf_returns`). 776 trading days = ~3 calendar years of yfinance data. **Patched 2026-04-30 evening:** line 97 changed to `days=1825` (5y). One-line fix; more importantly the script also tests only 6 of 13 baskets and reports a Sharpe of 13.72 because no costs are deducted — this script will be replaced by Task #24 outputs (full 5y, all 13 baskets, cost-deducted) over the next weekend.

### Q: What is "Commodity-Credit Divergence" (the trade row that's been most consistently in profit)?

**A:** Dashboard label for the basket internally named "PSU Commodity vs Banks" at `pipeline/config.py:153-157`:

```
long: ONGC + COALINDIA
short: HDFCBANK + ICICIBANK
news triggers: escalation, sanctions, hormuz
```

**Macro thesis:** when geopolitical stress rises, oil and coal benefit from supply premium and government PSU support, while private banks face credit risk and slower loan growth. The 4-leg dollar-neutral structure nets out NIFTY beta and isolates the macro signal. **Why it pays:** stress events are persistent (3-5 days, not spike-and-snap), so multi-day hold captures the full move; high signal-to-noise mapping; 4-leg averaging dampens single-name noise; trail-stop locks the gain.

**Why it's an audit gap:** like the other 12 baskets in `INDIA_SPREAD_PAIRS_DEPRECATED`, it has no formal backtest, no hypothesis-registry entry, no single-touch holdout. Real paper P&L, but not registered evidence of edge. **Action:** Task #24 backtests it first; on pass it becomes `H-2026-04-30-spread-basket-006` with a 60-day single-touch holdout going forward.

### Q: What does INERT mean on a position row?

**A:** Stop-status label, **not a regime label**. Defined in `pipeline/signal_tracker.py:712`. Once the trade's peak P&L exceeds the magnitude of the daily-stop, the trail-stop arms and dominates; the daily stop becomes inactive ("INERT") because we're in profit and the trail is doing the work. Visible in the dashboard at `pipeline/terminal/static/js/components/positions-table.js:265` — the Stop cell renders "INERT" with a tooltip explaining the trail is now active.

### Q: Why does the options paired ledger have only 9 unique tickers (and not the usual RELIANCE/HDFCBANK)?

**A:** The options sidecar is wired into ONLY three engines today: Phase C correlation breaks, Pattern Scanner Top-10, and Intraday V1 framework. **Phase C by construction flags stocks that *diverge* from their sector** — those tend to be mid-caps with idiosyncratic stories, not index-heavy names that track their sector closely. Of the 12 attempted opens, 7 ended SKIPPED_LIQUIDITY because the four-pronged options liquidity gate (5,000 ATM contracts/day OR 50K OI OR 1.5% spread max OR 5+ active strikes) filters thin mid-cap options markets. **The bigger gap:** SECRSI's 8-leg basket, the H-001/H-002 sigma-break engines, and the 13 spread baskets all have NO options sidecar — that's why heavyweight names don't show up. Task #30 wires them, currently paused per user direction until post-backtest review.

### Q: Should we add Indian sectoral indices (Bank NIFTY, NIFTY IT, etc.) to the regime classifier inputs?

**A:** **No — confirmed 2026-04-30.** The regime engine uses 28 global ETFs + 4 macro features as INPUTS to produce a regime label, then uses that label to PREDICT Indian sector behavior (Phase A/B/C). If we add Indian sector indices to the inputs, we contaminate: sectors would partly *define* the regime that's used to *predict* their own behavior — circular. Loses out-of-sample meaning, leaks information in backtests. The clean architecture: regime is exogenous (global ETFs), sector behavior is the dependent variable measured downstream. **What's missing:** a "sector × regime × time-of-day behavior" table that conditions the existing sector_panel returns on the regime label without adding sectors to the regime classifier. That's Task #25.

### Q: What is Banks × NBFC PDR and what did the discovery study find today?

**A:** PDR = Pair-Divergence-Reversion. The user's intuition: stably-correlated sector pairs (Banks × NBFC have +0.825 correlation over 5y, 100% bootstrap stable) should mean-revert when they diverge during a session. Today's intraday study (60-day Kite 1-min cache, Banks × NBFC pair, 11:00 IST signal time, 14:25 IST exit) found the user's intuition is **directionally validated at intraday frequency where the daily test had failed**. At T=11:00 with 1.0σ divergence threshold: n=9 events in 38 trading days, mean +11 bps post 20bp cost, 78% hit rate (7/9), t=1.32. Same pair at T=12:00, 1.5σ: n=6, mean +9 bps, 67% hit. Four cells positive after costs. None passes the formal verdict bar yet (need t>1.7) due to sample size, but the cross-cell consistency (multiple T-points and thresholds, all positive) is the real signal. **Next step:** registered as `H-2026-04-30-pdr-banks-nbfc` (Task #26), riding SECRSI's existing 09:16 capture-opens / 11:00 snapshot / 14:25 close plumbing. No new infrastructure.

### Q: How does today's "EARLY / LATE" filter work on signals?

**A:** Each signal at entry gets classified by its VWAP-deviation tertile:
- `EARLY` if VWAP-deviation is in the lowest tertile (`< -0.08%`) — i.e., the stock is below its volume-weighted average, which we treat as the early phase of an intraday move
- `LATE` if in the highest tertile (`> +0.36%`) — the stock has already moved
- `N/A` for the middle tertile

Live-monitor breakdown rows show separate P&L for EARLY vs LATE so we can see whether the system's edge concentrates in one timing bucket. Implementation: `pipeline/terminal/api/live_monitor.py:_aggregate_pnl` (commit `2654cd5`).

### Q: Why is news so suspect that we're moving to "data-primary, news-as-confirmation only"?

**A:** Two incidents hit 2026-04-30:

1. **Stale news bug** — `website_exporter.export_fno_news` overwrote morning headlines with `[]` at 16:00 EOD because the verdicts filter yielded zero rows. The terminal then displayed yesterday's news as today's. Fixed in commit `64a5f99`.
2. **Trade trigger fragility** — the 13 spread baskets fire on news-keyword triggers. We have no record of WHICH headline fired the trigger, whether the URL is still resolvable, whether the body has changed since fetch. We could be hallucinating evidence and not know.

**The fix (Task #23 spec):** every news headline cited in any trade row must persist URL + sha256 hash + published_at + fetched_at + classifier_score + verified_today flag. Anti-stale guard (>24h published = no confirmation). Anti-contradiction guard (data says LONG, news says contradicting keyword → BLOCK). Retroactive auditability — at any post-mortem the URL must still resolve and hash must match, else flagged "EVIDENCE_VANISHED".

Going-forward rule: **trade triggers must be data-primary; news is reassurance, never the trigger.**

### Q: What does the new "skeletons audit" document do?

**A:** `docs/SYSTEM_SKELETONS_AUDIT.md` — comprehensive inventory of every system component, registration/audit state, doc-coverage status, and gaps. Tagged with severity (CRITICAL / HIGH / MEDIUM / LOW). Re-run weekly until the doc-coverage column has zero "gap" or "skeleton" rows. Going-forward rule: every system component must have (1) entry in `anka_inventory.json` if scheduled, (2) a spec or design doc, (3) an FAQ entry, (4) a declared `data_primary_trigger` and provenance fields if it generates trades or consumes news.

---

## 17. Backtest verdicts (2026-04-30)

### Q: We ran the 5y backtest of all 13 INDIA_SPREAD_PAIRS baskets — what did it find?

A: **Brutal.** Only **1 PASS cell across 234** regime-conditional cells: Reliance vs OMCs in EUPHORIA, 5d hold (n=28, post-20bp +275 bps, t=4.38, hit 75%, BH-FDR survive). Mode A (news-conditional 2y) had 0 PASS — news conditioning adds nothing the data can prove. Full readout: `docs/research/india_spread_pairs_backtest/findings_2026-04-30.md`.

### Q: So what about "PSU Commodity vs Banks", the most consistent paper earner?

A: **No statistical edge in the 5y data.** Best Mode B cell: t=1.41 (RISK-ON 5d). The live paper P&L is consistent with sample-period luck. Specifically: in the 24 months of news data (Mode A), the basket fired ~23 times — n too small to prove or disprove news conditioning. Recommend: keep paper-trading until the next 12 months adds n, but tag with "no edge proven" in the UI.

### Q: Which baskets are kill candidates?

A: 4 confirmed structural net-losers (negative post-cost mean across every regime over 5y):
- Reliance vs OMCs (#3) — outside EUPHORIA, where it earns. Inside EUPHORIA, see promotion below.
- Pharma vs Cyclicals (#5)
- EV Plays vs ICE Auto (#12)
- Infra Capex Beneficiaries (#13)

Plan: leave the news-trigger live for now (no behavioral change); when the V1 kill-switch fires per the news-driven framework deprecation, these 4 don't get individual hypothesis registrations. They die as the framework dies.

### Q: Which baskets actually have structural alpha?

A: 4 candidates emerged in the Mode B 5y test:
- **Defence vs IT (#2) NEUTRAL 5d**: t=3.76, n=882, post +63 bps — fails ONLY hit-rate by 1.0pt
- **Defence vs IT (#2) RISK-ON 5d**: t=4.80, n=161, post +172 bps — fails MaxDD (path is bumpy)
- **Defence vs Auto (#7) RISK-ON 5d**: t=4.73, n=161, post +185 bps — same MaxDD issue
- **Reliance vs OMCs (#3) EUPHORIA 5d**: PASS (the one PASS cell). Promoted to `H-2026-04-30-RELOMC-EUPHORIA`.

The Defence cases need a sizing rework (ATR-scaled notional, not equal-notional) before re-registration. The Defence story is: HAL, BEL beating IT/Auto over 5y — likely a structural sector trend (defence push post-Russia-Ukraine + India's military modernization), not news.

### Q: What does this mean for the news-driven framework?

A: It means **news is reassurance, not alpha**. Per memory `feedback_news_is_reassurance_not_trigger.md`. The 4 surviving baskets earn money STRUCTURALLY — news triggers correlate weakly or not at all with the actual return. Once provenance recording is wired (Task #23 phase 1 in `pipeline.news_provenance` shipped 2026-04-30), news becomes a *contradicts-block* (anti-correlation guard), not a primary trigger. When V1 holdout completes 2026-06-27 and passes, the kill-switch deprecates news triggers entirely.

### Q: What's `H-2026-04-30-RELOMC-EUPHORIA`?

A: The first hypothesis born from this backtest. LONG RELIANCE / SHORT BPCL+IOC, opens at 09:15 IST whenever V3 CURATED-30 regime label = EUPHORIA at T-1 close, hold 5 trading days, exit at T+5 close. Holdout 2026-05-01 → 2027-04-30. EUPHORIA is rare (~5-8 days/year), so verdict is slow by design — single-touch is binding. Spec: `docs/superpowers/specs/2026-04-30-relomc-euphoria-design.md`.

### Q: Did the sector × regime matrix find anything?

A: Yes — 16 sectors qualify in RISK-ON regime over 5y (broad-based bullish). Also 4 in NEUTRAL. None in RISK-OFF / EUPHORIA (small n). This is descriptive evidence that the regime conditioning architecture works: when V3 calls RISK-ON, broad sector longs have positive expectancy. Promotable cells become candidates for autoresearch v2's hypothesis proposal queue. NOT trade signals on their own — they need single-touch holdouts. Findings: `docs/research/sector_regime/sector_regime_matrix_2026-04-30.md`.

---

## How this document evolves

- **Updated on `/autowrap`** each session: new Q&A from chat → relevant section.
- **Cross-referenced with memory:** when a Q&A here is detailed enough to deserve its own memory file, link from here to memory and keep the FAQ entry as a 1–2 sentence summary.
- **Versioned via git history:** `git log docs/SYSTEM_FAQ.md` shows the trail of when each topic landed.
- **Source of truth for newcomers:** any new collaborator reads this before asking the same questions.

## Daily-update commitment (added 2026-04-30)

Per Bharat 2026-04-30: "FAQ needs daily update so I don't forget what is happening." Mechanism:

1. **End of every session** that touched a system, hypothesis, or design decision: add a Q&A here. The Q is "what did Bharat ask / what was decided"; the A is the answer with a code/memory link.
2. **The "Last updated" date at the top** must be bumped on any commit that touches this file. If the date is more than 3 days stale, that's a signal that the FAQ has fallen behind — `/autowrap` should explicitly check and prompt.
3. **No silent additions.** Each new Q&A must come from an actual chat exchange or design memo. Synthesizing topics from imagination is forbidden — the FAQ should reflect what's *actually* been discussed, not a theoretical curriculum.
4. **One commit, one section.** When updating, prefer a focused commit per section being touched. Easier to skim git log to find when a topic was last clarified.
