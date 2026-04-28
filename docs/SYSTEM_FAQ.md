# Anka System — FAQ

A living reference of Q&A about how the Anka research system actually works. Synthesized from session transcripts, design specs, and memory files. Updated on `/autowrap` each session.

> **Purpose:** stop re-asking the same questions across sessions. When something is asked and answered well in chat, it lands here.

**Last updated:** 2026-04-29

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
11. [Glossary of acronyms](#11-glossary)

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

## 11. Glossary

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

## How this document evolves

- **Updated on `/autowrap`** each session: new Q&A from chat → relevant section.
- **Cross-referenced with memory:** when a Q&A here is detailed enough to deserve its own memory file, link from here to memory and keep the FAQ entry as a 1–2 sentence summary.
- **Versioned via git history:** `git log docs/SYSTEM_FAQ.md` shows the trail of when each topic landed.
- **Source of truth for newcomers:** any new collaborator reads this before asking the same questions.
