# Phase C Validation Research — Design Spec

**Date:** 2026-04-20
**Author:** Anka Research (Bharat + Claude)
**Status:** Spec — pending implementation plan
**Related:** `pipeline/autoresearch/reverse_regime_breaks.py`, `pipeline/break_signal_generator.py`, `correlation_break_history.json`

---

## 1. Goal

Produce a peer-review-grade research document and a reusable backtest engine that establishes — defensibly — whether the Phase C correlation-break engine has tradeable edge as an **intraday-only** strategy with mechanical exit at 14:30 IST.

The output must satisfy two reviewer audiences:

1. **Internal trading desk** — practitioners who understand market microstructure, regime engines, correlation breaks. Bar: clear narrative, walk-forward, regime-stratified, hit rate + Sharpe + drawdown, transparent cost model.
2. **Quant fund / institutional investor** — bar: A + multiple-hypothesis correction, cost stress-tests, parameter robustness, survivorship-bias controls, point-in-time universe, true out-of-sample forward test.

Explicitly **not** academic-publication grade (no formal literature comparison, no journal-style framing).

---

## 2. Context

Phase C currently:

- Runs every 15 min during market hours via `AnkaCorrelationBreaks` scheduled task
- Reads `pipeline/data/correlation_breaks.json`
- For each break with `trade_rec.direction ∈ {LONG, SHORT}` (i.e. `classification = OPPORTUNITY`), `pipeline/break_signal_generator.py` emits a single-leg shadow signal
- `pipeline/run_signals.py:401-419` calls `signal_tracker.save_signal()` immediately, auto-opening the trade as a paper position with 3-day hold
- Result: positions land in `open_signals.json` and the Dashboard renders them as Open Positions

**Two problems with the current state:**

1. **No backtest exists.** The engine has been live ~6 days. Success criteria are defined in `docs/superpowers/specs/2026-04-14-correlation-break-detector-design.md` (line 156-160) but never measured. Anecdotal "it makes money" claims are unverified.
2. **3-day hold is the wrong horizon.** Phase A profile quality is moderate (28-58% historical hit rates, 38-50% regime persistence) — these are weak anchors over 3-5 days. The hypothesis is they're stronger over hours.

**This research project tests the intraday-only reformulation** (entry at signal time, exit at 14:30 IST mechanical, no overnight risk).

---

## 3. Hypotheses tested

We test **all five Phase C classifications**, not just OPPORTUNITY. Each becomes a separate hypothesis with its own pass/fail bar:

| ID | Classification | Claim |
|---|---|---|
| H1 | OPPORTUNITY | Generates positive risk-adjusted net return when traded intraday with 14:30 IST exit |
| H2 | POSSIBLE_OPPORTUNITY | Has informational value (next-day directional accuracy > chance) |
| H3 | WARNING | Predicts subsequent weakness in the labeled stock over next 1 day |
| H4 | CONFIRMED_WARNING | Predicts large-magnitude adverse move (> 1σ) over next 1 day |
| H5 | UNCERTAIN | Has no predictive value (null result expected; if rejected, methodology suspect) |

**Multiple-hypothesis correction:** Bonferroni at family-wise α = 0.05 → α_per = 0.01 per individual test. Sensitivity analyses (ablations, exit-time variants, N variants) are not counted as separate hypotheses; they are robustness checks on existing claims.

---

## 4. Decision summary

### 4.1 User-confirmed (9 decisions)

| # | Topic | Decision |
|---|---|---|
| 1 | Hypothesis scope | Test all 5 classifications, OPPORTUNITY for tradeable edge, others for informational value |
| 2 | Rigor bar | Moderate: Sharpe ≥ 1.0, hit ≥ 55%, DD ≤ 20%, ≥3/4 regimes, p ≤ 0.05 (Bonferroni for 5), in-sample AND forward both positive |
| 3 | Cost model | Zerodha retail base (~10-11 bps round-trip including 5 bps slippage); stress curve at 5/10/20 bps in appendix |
| 4 | Walk-forward | Rolling 2-year train / 3-month test, refit quarterly, ~8 OOS windows over 4 years |
| 5 | Universe | Point-in-time F&O list per historical date; reconstruct from NSE monthly contract archives |
| 6 | Intraday data gap | Two-tier: 4yr in-sample tests directional edge end-of-day; 60-day forward tests true intraday with 14:30 exit using Kite 1-min bars |
| 7 | Position sizing | Top-5 OPPORTUNITY by abs(z-score) per day at ₹50,000 each; max ₹2.5L deployed daily |
| 8 | OI/PCR robustness | Ablation study: Full / No-OI / No-PCR / Degraded; sensitivity tests |
| 9 | Forward test | F3 — replay last 60 days NOW as primary OOS verdict + start live shadow paper-trade from implementation merge date as ongoing confirmation |

### 4.2 Methodology decisions taken by Claude (M1-M4)

| ID | Topic | Decision | Rationale |
|---|---|---|---|
| M1 | Entry timing in 1-min bar | Enter at the next 1-min bar's open after signal scan time | Avoids same-bar lookahead; matches realistic algo execution |
| M2 | Exit timing | Exit at the 14:30:00 bar's open; honor stop-pct and target-pct if hit before 14:30 | Mechanical no-discretion; stops/targets defined in trade_rec already |
| M3 | Regime data source | Recompute regime per historical day using current ETF engine code on `pipeline/data/etf_history/` | ETF engine has been retuned; historical writes aren't comparable. Tests "Phase C with today's regime engine" |
| M4 | "Informational value" bar | Next-day directional accuracy ≥ 53% at p ≤ 0.05 (Bonferroni-corrected to 0.01) | Standard binomial bar for predictive value claims |

---

## 5. Architecture

### 5.1 File structure

```
pipeline/research/phase_c_backtest/
├── __init__.py
├── fetcher.py            Kite + EODHD historical fetcher; daily OHLCV + 1-min bars; on-disk parquet cache
├── universe.py           Point-in-time F&O universe per date (NSE monthly archives)
├── regime.py             Recomputes ETF regime per historical day using current engine code (M3)
├── profile.py            Rolling Phase A profile trainer; refit every 3 months on prior 2yr (W2)
├── classifier.py         Phase C decision-matrix replay; reuses reverse_regime_breaks.classify_break()
├── simulator_eod.py      End-of-day P&L simulator for 4yr in-sample (T2 → directional edge)
├── simulator_intraday.py 1-min bar simulator for 60-day forward (T2 → true intraday, 14:30 exit)
├── cost_model.py         Zerodha retail base + parametric slippage (Cost B)
├── ablation.py           Runs Full / No-OI / No-PCR / Degraded variants (R1)
├── stats.py              Sharpe / DD / hit-rate / regime breakdown / Bonferroni
├── robustness.py         Exit-time variants, N-cap variants, parameter perturbations
├── report.py             Emits markdown tables + matplotlib charts for each doc section
├── live_paper.py         Wires into signal_tracker for ongoing shadow trade (F3 live leg)
├── run_backtest.py       Orchestrator entrypoint
└── data/                 Cached artifacts: minute_bars/, daily_bars/, fno_universe_history/, regime_backfill.json, phase_a_profiles/
```

Tests in `pipeline/tests/research/phase_c_backtest/` follow project TDD discipline.

### 5.2 Data flow

```
[Kite API + EODHD] ──► fetcher.py ──► parquet cache
                                       │
[NSE monthly F&O]  ──► universe.py ────┤
                                       │
[ETF engine code]  ──► regime.py ──────┤──► profile.py (refits quarterly on T-2yr only)
                                       │
                                       ▼
                                  classifier.py  ──► 5-class labels per stock per day
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                            ▼
                 simulator_eod.py            simulator_intraday.py
                 (4yr directional)           (60d intraday, 14:30 exit)
                         │                            │
                         └────────────┬───────────────┘
                                      │
                   cost_model.py → applied to each trade
                                      │
                                      ▼
                              ablation.py × 4 variants
                                      │
                                      ▼
                                  stats.py
                                      │
                                      ▼
                                 report.py ──► docs/research/phase-c-validation/*.md
```

Live leg (F3): `live_paper.py` registers a fresh shadow-trade tag (`PHASE_C_VERIFY_*`) starting on the day of merge; results aggregate into the ongoing-monitoring section of the report, refreshed nightly.

---

## 6. Statistical methodology

### 6.1 Significance tests per hypothesis

| ID | Test | Null | Pass criterion |
|---|---|---|---|
| H1 | Sharpe via bootstrap (10,000 resamples) | Sharpe = 0 | 99% CI lower bound > 1.0 (in-sample) AND > 0.5 (forward) |
| H2 | Binomial test on next-day directional accuracy | Hit rate = 0.50 | p ≤ 0.01 AND hit ≥ 0.53 |
| H3 | Binomial test on next-day return < 0 in WARNING-tagged stocks | Hit rate = 0.50 | p ≤ 0.01 AND hit ≥ 0.53 |
| H4 | Binomial test on next-day return < -1σ stock-regime baseline | Hit rate = baseline | p ≤ 0.01 AND lift > 0 |
| H5 | Binomial test on directional accuracy | Hit rate = 0.50 | Fail-to-reject expected; if rejected, methodology suspect |

### 6.2 Verdict logic — H1 OPPORTUNITY

H1 passes if and only if **all** of these hold:

- In-sample Sharpe 99% CI lower bound > 1.0 at base cost assumption (Zerodha retail ~10-11 bps round-trip including 5 bps slippage)
- Forward-test Sharpe 99% CI lower bound > 0.5 (smaller sample, looser bar)
- Hit rate ≥ 55% in both periods at Bonferroni-adjusted p ≤ 0.01
- Max drawdown ≤ 20% of cumulative P&L in both periods
- Positive edge in ≥ 3 of 4 regimes (each cell clears binomial p ≤ 0.01)
- In-sample AND forward Sharpe within 50% of each other (overfit guard)
- Strategy remains positive in Degraded ablation (survives OI/PCR outage)

### 6.3 Verdict logic — H2-H5 (informational classes)

Each passes iff binomial test rejects null at p ≤ 0.01 AND sample ≥ 60 trades.

### 6.4 Decision tree

```
If H1 passes
  ──► Ship Phase C as intraday-only trading strategy: surfaces in Trading tab as day-trade candidates with mechanical 14:30 IST exit. Live execution wiring (Kite auto-execution) is a separate spec, not in scope here.
       Continue F3 live monitoring; if forward Sharpe trajectory degrades > 50% over 90 days, suspend

If H1 fails AND any of H2-H5 passes
  ──► Phase C remains in Scanner (informational only); no auto-trade
       Document which classes are predictive; surface as alerts only

If all 5 hypotheses fail
  ──► Retire Phase C auto-generation entirely
       Mark `pipeline/break_signal_generator.py` as deprecated
       Treat as manual research signal only; remove from `/api/candidates` signals[]
```

### 6.5 Minimum sample requirements

- ≥ 30 trades per (classification × regime) cell — minimum for binomial/Sharpe test
- ≥ 60 trades — stable Sharpe estimate (Lo 2002 rule of thumb)
- < 30 trades → "insufficient data, no claim made"
- 30-60 → reported but marked "exploratory"
- ≥ 60 → standard reporting

Sample-size projection (rough — actual count emerges from the run): the 5 days of live data contain 1,571 breaks with 10.5% OPPORTUNITY → if that rate holds historically, a 4-year backtest produces several thousand OPPORTUNITY trades, enough for the primary hypothesis. UNCERTAIN (74.5% of current signals) and POSSIBLE_OPPORTUNITY (12.7%) should also be adequate. WARNING (2.3%) and CONFIRMED_WARNING (0% in current week) may have **thin samples** — if so, doc explicitly states "cannot reject null for class X due to N=Y < 30." The actual counts replace these estimates in §08-appendix-statistics.

### 6.6 Robustness grid (appendix)

Reported in robustness section, NOT counted toward Bonferroni adjustment:

| Dimension | Values tested | What's reported |
|---|---|---|
| Slippage | 5 / 10 / 20 bps | Sharpe decay curve |
| Exit time | 13:30 / 14:00 / 14:30 / 15:00 / 15:15 IST | Sharpe per exit; 14:30 is primary |
| Top-N cap | 3 / 5 / 10 / 20 / unlimited | Sharpe vs concurrency |
| Z-score thresholds | ±20% perturbation of all internal thresholds | Sharpe stability grid |
| PCR/OI ablation | Full / No-OI / No-PCR / Degraded | R1 ablation results |
| Profile lookback | 1yr / 2yr / 3yr training window | W2 primary is 2yr |
| Regime source | Current ETF engine / naive MSI / no regime | Edge attribution to regime input |

Headline result: "Strategy remained positive across X of Y parameter settings."

---

## 7. Document structure (deliverable)

```
docs/research/phase-c-validation/
├── 01-executive-summary.md       1 page — verdict + key numbers
├── 02-strategy-description.md    Phase A→B→C in plain English with diagrams
├── 03-methodology.md             Data, walk-forward, costs, ablations, all 13 locked decisions defended
├── 04-results-in-sample.md       4yr directional edge — all 5 classes × 4 ablations × 4 regimes
├── 05-results-forward.md         60-day intraday — primary OOS verdict
├── 06-robustness.md              Slippage, exit times, N caps, parameter perturbation
├── 07-verdict.md                 Pass/fail per hypothesis vs Moderate bar + go-forward decision
├── 08-appendix-statistics.md     Bonferroni math, p-values, sample sizes per cell, raw tables
├── 09-appendix-data.md           Data sources, historical universe per year, regime backfill notes
└── 10-appendix-reproduction.md   Step-by-step to re-run the entire backtest
```

Each section: ≤ 5 pages. Total document ≤ 40 pages.

---

## 8. Defense surface

| Reviewer attack | Pre-empting defense | Code location |
|---|---|---|
| Lookahead via Phase A profile | W2 walk-forward; profile trained only on T-2yr to T | `profile.py` asserts no data ≥ `cutoff_date` |
| Survivorship | U2 point-in-time universe per date | `universe.py` returns universe-at-date |
| Fabricated intraday fills | T2 split — 4yr EOD only, forward 1-min only | `simulator_eod.py` ≠ `simulator_intraday.py` |
| Single-period luck | W2 walk-forward across 8 OOS windows | `run_backtest.py` iterates windows |
| Cost hand-waving | Cost B stress curve at 5/10/20 bps | `cost_model.py` parametric |
| Multiple-hypothesis fishing | Bonferroni for 5 tests | `stats.py` |
| Overfit to one regime | Regime stratification ≥3/4 bar | `stats.py` stratified tables |
| Cherry-picked 14:30 exit | Robustness grid: 13:30/14:00/14:30/15:00/15:15 | `robustness.py` |
| Cherry-picked N=5 cap | Robustness grid: N=3/5/10/20 | `robustness.py` |
| Contaminated forward test | F3 live paper-trade from merge date, independent | `live_paper.py` |
| In-sample / forward divergence | Overfit guard: must be within 50% on Sharpe | `stats.py` verdict logic |

---

## 9. Out of scope

- **Trust-as-beta backtest (Project C from dashboard restructure spec)** — separate project, queued. Both backtests share the `pipeline/research/` subtree but have independent specs.
- **Real-money execution wiring** — verdict triggers a separate spec for Kite live execution if H1 passes.
- **Phase A or Phase B revision** — we're testing Phase C *as-is*. If results disappoint, retuning Phase A's profile is a separate research project.
- **News-overlay enhancement** — adding news sentiment as a 5th decision-matrix input is out of scope; tested only if R1 ablation shows current 4 inputs together aren't enough.
- **Contract roll modeling for futures** — Phase C operates on cash equities. Futures contract rolls don't apply.

---

## 10. Known limitations / open risks

- **Phase A profile re-fit speed.** Current Phase A code may be slow to refit; if quarterly refits over 4 years takes > 4 hours, we cache aggressively and document the cost.
- **Kite minute-bar API rate limits.** Kite caps historical minute requests; the 60-day fetch for 215 stocks may need batching + caching.
- **NSE F&O monthly archives.** May or may not be cleanly accessible; if not, U2 falls back to a documented best-effort reconstruction with explicit per-month gaps.
- **WARNING / CONFIRMED_WARNING sample size.** May be too thin to reject null. Doc will state explicitly if so.
- **The current regime engine may itself be drifting.** M3 says we use "current" engine; if the engine is changing weekly, results aren't reproducible week-over-week. Mitigation: pin the engine version at the start of the backtest run; report which version was used.
- **Survivorship in regime backfill.** ETF universe today may differ from 4 years ago (delisted ETFs, currency-hedged variants). M3 inherits this; document the ETF universe used.

---

## 11. Acceptance criteria for the spec

This spec is complete when:

- [x] All 13 locked decisions captured in §4
- [x] Hypothesis statements precise and falsifiable
- [x] Pass/fail bars numerically defined
- [x] Architecture file-tree decomposed into single-responsibility modules
- [x] Defense surface enumerates known attacks with mitigation each
- [x] Out-of-scope items explicit
- [x] Known limitations honest

Implementation plan to follow in a separate doc once spec is approved.
