# Data-driven intraday framework — design spec

**Hypothesis registrations:**
- `H-2026-04-29-intraday-data-driven-v1-stocks` (NIFTY-50 stocks)
- `H-2026-04-29-intraday-data-driven-v1-indices` (options-liquid index futures)

**Date:** 2026-04-29
**Status:** Pre-registered, single-touch holdout 2026-04-29 → 2026-06-27 (~44 trading days; auto-extends on infrastructure-failure days)
**Verdict by:** 2026-07-04 (5 trading day computation buffer)
**Owner / proposer:** Bharat Ankaraju
**Data dependency:** `kite_1min_intraday_60d_v1` — see `2026-04-29-kite-1min-data-source-audit.md` (Tier D2, Approved-for-research)
**Predecessors:** This is the deprecation candidate for the news-driven spread framework (`pipeline/political_signals.py`, `pipeline/config.py:120-202` `INDIA_SPREAD_PAIRS`). On V1 pass, news-driven framework is killed and archived; on V1 fail, news-driven incumbent stays running and V1 returns to drawing board.

**Policy binding:** Conforms to `docs/superpowers/specs/backtesting-specs.txt` §0–§16 strict. Single-touch holdout per §10.4 — no parameter changes during the holdout window.

## §0 Pre-flight

- ✅ Spec written before code (this document).
- ✅ Data dependency audited and accepted (`kite_1min_intraday_60d_v1` Tier D2).
- ✅ Hypothesis registry entries staged (twin entries to be appended to `docs/superpowers/hypothesis-registry.jsonl` in same commit as `runner_live.py`).
- ✅ Pre-commit strategy gate enforced — files matching `*_engine.py` ship with hypothesis-registry entry in same commit (CLAUDE.md kill-switch).

## §1 Hypothesis statement

**H-stocks:** A pooled-weight linear combination of 6 intraday features (delta-PCR, ORB, volume-Z, VWAP-deviation, intraday RS-vs-sector, intraday-trend-slope) computed at 09:30 IST predicts the sign of the 09:30 → 14:30 IST return on NIFTY-50 stocks. The framework passes V1 if hit-rate beats per-instrument bootstrap null at p<0.05 (BH-FDR-corrected), realized Sharpe ≥ 0.5, MaxDD ≤ 5%, §9A Fragility ≥ 8/12, and §9B margin ≥ 0.5pp vs the better of always-long/always-short baselines, over a 44-trading-day window with ATR(14)×2 protective stop and mechanical 14:30 IST exit.

**H-indices:** Same feature stack, same pooled-weight structure, same statistical thresholds, fitted independently on options-liquid index futures (NIFTY 50, BANKNIFTY, FINNIFTY, NIFTY MID SELECT, NIFTY NXT 50, NIFTY IT, NIFTY AUTO, NIFTY PHARMA — universe finalized at kickoff per options-liquidity gate).

**Null:** Per-instrument bootstrap of historical 09:30 → 14:30 returns over prior 5-year window (5000 resamples), randomly choosing direction with equal probability. The framework must beat this null at p<0.05 BH-FDR-corrected across instruments.

## §2 Universe & Sample

### V1 universe (locked at kickoff 2026-04-29 09:30 IST)

**Stock pool:** NIFTY-50 constituents as of 2026-04-29 close, frozen for the holdout. Source: `opus/config/nifty50.json`. New additions / removals during the window are NOT applied — universe is static per §10.4.

**Index pool:** All NSE index futures clearing the **options-liquidity gate** (definition below).

**Options-liquidity gate** (computed once at kickoff from prior 20 trading days of `pipeline/data/oi/` snapshots):
- Median ATM call+put daily volume ≥ 5,000 contracts
- Near-month total OI ≥ 50,000 contracts
- Median ATM bid-ask spread ≤ 1.5% of premium
- ≥ 5 strikes traded with non-zero volume on each side

Index candidates that fail any threshold are excluded; expected to admit ~8–12 of the ~15 listed index F&O.

### Sample window

- **In-sample (for monthly Karpathy fit at kickoff):** rolling 60-trading-day window ending 2026-04-28 (approximately 2026-02-02 onward, exact start date resolved at runtime per NSE trading calendar).
- **Holdout:** 2026-04-29 → 2026-06-27 (~44 trading days). Single-touch per §10.4.
- **Monthly recalibration:** Sunday 02:00 IST on the last Sunday of each calendar month, refits on rolling prior-60-trading-day window. First recalibration target: **last Sunday of May 2026** (exact date resolved at runtime). **Recalibration produces a new weight vector applied from the following Monday onward; the prior weight vector's holdout-collected trades remain in the holdout-of-record unchanged.** This is consistent with §10.4 — recalibration is a documented protocol that's part of the registered hypothesis, not a parameter change.

### Verdict-extension rule

A trading day with `STATUS ∈ {NO_KITE_SESSION, PARTIAL_COVERAGE_ABORT, INTEGRITY_ISSUE, STALE_FEED}` extends the holdout end-date by 1 trading day. Holdout count is "44 *clean* trading days," not "44 calendar trading days." Matches `H-2026-04-27-003 SECRSI` precedent.

## §3 Features

Six features, deterministic, computed at evaluation timestamp `t` (typically 09:30:00 for live, every 15 min for shadow). All features use only data with `timestamp < t` (point-in-time strict per data audit §11).

| # | Feature | Definition | Source |
|---|---|---|---|
| 1 | `delta_pcr_2d` | `PCR(t, next_month)` − `PCR(t-2d, next_month)`, where PCR = put_OI / call_OI on next-expiry options chain | `pipeline/data/oi/{instrument}_{near|next}_chain.json` |
| 2 | `orb_15min` | `(last_close_in[09:15,t) − open_at_09:15) / open_at_09:15` | Kite 1-min cache |
| 3 | `volume_z` | `(cum_volume_t − μ_20d) / σ_20d`, where μ/σ are 20-trading-day mean/std of cumulative volume by minute-of-day at the same time-of-day | Kite 1-min cache |
| 4 | `vwap_dev` | `(close_at_t − VWAP_today) / VWAP_today`, where VWAP is volume-weighted from 09:15 to t-1min | Kite 1-min cache |
| 5 | `rs_vs_sector` | `(instrument_ret_09:15_to_t) − (sector_index_ret_09:15_to_t)` for stocks; for indices, vs `NIFTY 50` ret | Kite 1-min cache + sector mapping from `opus/artifacts/sectors/` |
| 6 | `trend_slope_15min` | OLS slope of close prices on minute-index over `[t-15min, t)` window, normalized by close at start of window | Kite 1-min cache |

**NaN handling:** any feature returning non-finite → instrument excluded from today's pool with `EXCLUDED=feature_nan_<feature_name>` row in audit log. No imputation.

**Stocks vs indices:** features are defined identically across instrument classes; the difference is which sector_index is used for `rs_vs_sector` (sector for stocks, NIFTY 50 for non-NIFTY indices, NIFTY NXT 50 for NIFTY 50 itself).

## §4 Labelling

**For Karpathy fit (in-sample):** continuous return `r = (close_at_14:30 − entry_price) / entry_price`, where `entry_price = open_at_t+1min` (executable price 1 min after eval). Mechanical 14:30 exit; ATR(14)×2 protective stop applied if breached intraday.

**For verdict (holdout):**
- Hit-rate: `1` if `sign(realized_pnl) == sign(predicted_score)`, else `0`.
- Sharpe: `mean(daily_return) / std(daily_return) × sqrt(252)`, where `daily_return` = avg return across all V1 positions opened that day.
- Both directions (long when score > +threshold, short when score < −threshold) — predicted_score sign drives direction, not feature sign.

## §5 Model

### Karpathy random-search optimizer

**Search space:** weight vector `w ∈ ℝ⁶`, each component bounded `[−2, +2]`. Per-instrument score = `w · feature_vector_normalized`, where each feature is z-scored within the in-sample window per instrument-class (one z-score per feature per pool, not per instrument).

**Objective (robust Sharpe):**
```
J(w) = AvgRollingSharpe(w)
     − λ_var × StdRollingSharpe(w)
     − λ_turnover × Turnover(w)
     − λ_dd × MaxDrawdown(w)

λ_var = 0.5
λ_turnover = 0.1
λ_dd = 1.0

Rolling window for AvgRollingSharpe: 10 trading days, sliding by 1 day across in-sample.
```

**Search:** 2,000 random samples uniform in `[−2, +2]⁶`, evaluate `J(w)` for each, retain top-1. Fixed seed `42` for reproducibility per `backtesting-specs.txt §16`.

**Threshold for entry:** the per-instrument score must exceed the in-sample 70th percentile (long) or fall below the 30th percentile (short). Threshold values are stored alongside weights in `weights/<date>_{stocks|indices}.json` and locked across the month until next recalibration.

**Stocks pool fit and indices pool fit are completely independent** — no shared weights, no joint optimization, no cross-leakage. Each pool gets its own (weight_vector, long_threshold, short_threshold) tuple per month.

### Why pooled, not per-instrument

`H-2026-04-29-ta-karpathy-v1` uses per-stock Lasso L1 logistic regression with the honest expectation that "0–3 of 10 stocks qualify." Per-stock weight fits on thin intraday data overfit by construction. Pooled fit shares strength across the universe and produces "steady weights" per the user's anti-overfit mandate (`feedback_pragmatic_model_definition.md`).

## §6 Validation

### In-sample fit reproducibility (pre-deploy)

- Same seed + same in-sample window → identical weight vector across 10 reruns. Tested in `tests/test_karpathy_fit_reproducible.py`.
- Same weight vector + same feature vector → identical score across 100 evaluations. Tested in `tests/test_features_deterministic.py`.

### Walk-forward sanity (pre-deploy)

Apply the §5 Karpathy fit to **prior** rolling-60-day windows ending 2026-01-31, 2026-02-28, 2026-03-31, 2026-04-28 (4 backtests). Each window's fit is evaluated on the **next 22 trading days**. Required: median realized Sharpe across the 4 windows ≥ 0.3. **This is a sanity check, not a passing-gate** — it confirms the fitter doesn't catastrophically misfit; it does NOT pre-validate the holdout.

### Out-of-sample (the holdout — §9, §10)

See §9 thresholds and §10 single-touch.

## §7 Multiple-comparison correction

**BH-FDR across instruments per pool:** stocks-pool has 50 simultaneous binomial tests (one per stock against per-stock bootstrap null); indices-pool has ~8–12 tests. Benjamini-Hochberg controls FDR at q=0.05.

**Aggregate-pool tests are NOT BH-corrected** — those are single hypothesis tests on the pooled hit-rate vs random-direction null. Per-instrument tests *are* corrected.

**Twin-hypothesis correction:** the two pools (stocks, indices) are tested as **separate hypotheses**, NOT pooled into a 60-instrument joint test. No additional multiple-comparison correction across pools — they fail or pass independently. Justified: structurally different instrument classes with independent weight fits.

## §8 Robustness

§9A Fragility test (see §9A below) is the single robustness gate.

Subsidiary robustness checks (informational, do NOT gate verdict):
- Performance by month (May, Jun within holdout — does the framework work in both?)
- Performance by ETF regime (RISK_ON / RISK_OFF / NEUTRAL via ETF v3 curated_30 zone) — descriptive only
- Per-instrument breakdown (which stocks contributed most? Concentration on 1–2 names is a warning, not a fail)

## §9 Statistical thresholds

**Per-pool aggregate gate (must clear ALL):**

| Threshold | Value | Rationale |
|---|---|---|
| Hit-rate vs random-direction null | p < 0.05 (single-tailed) | §9 standard |
| Realized Sharpe (annualized) | ≥ 0.5 | Distinguishable from noise; below this is unsightly given execution costs |
| Max drawdown (peak-to-trough on cumulative P&L) | ≤ 5% | Capital-preservation floor |
| Margin vs always-long (always-short) baseline | ≥ +0.5pp hit-rate | Not just market drift |

### §9A Fragility (perturb-and-retest)

Perturb each of the 6 weight-vector components by ±10% (12 perturbed vectors per pool) and recompute holdout Sharpe under each perturbation. **Required: ≥ 8 of 12 perturbations remain Sharpe-positive AND hit-rate > 50%.** Below this threshold = FRAGILE = FAIL regardless of other gates passing.

The 8-of-12 threshold preserves the 67% pass-ratio of the §9A precedent (4-of-6 from `H-2026-04-25-002` and `project_etf_stock_tail_h_2026_04_25_002.md`, which failed at 0/6) while testing both directions of perturbation per feature.

### §9B Margin vs always-baseline

Compute hit-rate of "always go long" and "always go short" baselines on the holdout. The framework must beat the better of the two by ≥ 0.5pp. Otherwise, FAIL on §9B regardless of other gates passing. Same precedent as the H-2026-04-25-002 failure.

## §10 Single-touch holdout

**Per `backtesting-specs.txt §10.4` strict:**
- No parameter changes during 2026-04-29 → 2026-06-27. Specifically:
  - 6 features locked
  - 70th/30th percentile thresholds at fit-time, locked between recalibrations
  - ATR(14)×2 stop locked
  - 14:30 mechanical exit locked
  - Karpathy seed=42 locked
  - λ_var, λ_turnover, λ_dd locked
- Monthly recalibration (Sunday 02:00) is **part of the registered hypothesis**, not a parameter change. The recalibration protocol itself is locked: 2,000 random samples, robust-Sharpe objective, prior-60-day window. Only the resulting weight vector changes monthly.
- One-shot bug fix exception: if a code-level bug is discovered that contaminates the holdout (e.g., off-by-one in feature compute), the fix may be applied with a **public log entry** in `verdict_2026_07_04.json` documenting before/after — but this consumes a "bug-fix touch" and any further fixes invalidate the holdout. Matches `H-2026-04-27 H-001 regime-source-bug` precedent (`project_h_001_regime_bug_2026_04_27.md`).

## §11 Promote criteria (V1 → production-tradeable)

V1 holdout passes if **either** pool clears ALL of:
- §9 hit-rate, Sharpe, MaxDD thresholds
- §9A Fragility ≥ 4/12
- §9B margin vs baseline ≥ 0.5pp

If only one pool clears, the other is archived as "FAILED at V1, may revisit at V2 with revised features." The passing pool moves to V1.1 (universe expansion to full F&O for stocks; or sector-index expansion for indices) under a new single-touch holdout.

If both pools fail, V1 is archived and the framework returns to drawing board. News-driven incumbent stays running. Per `feedback_pragmatic_model_definition.md` — money beats taxonomy; we accept the data telling us no.

### §11B Cross-regime stability (informational)

Compute per-regime hit-rate breakdown (RISK_ON / RISK_OFF / NEUTRAL via ETF v3 curated_30) on the holdout. Required for V1.1 promotion (not for V1 pass): no regime contributes a ≥ 5pp drag on aggregate hit-rate. Below 5pp drag is acceptable; ≥ 5pp drag flags the framework as regime-fragile and triggers a regime-conditional V1.1 re-spec.

## §12 Operational

### Live trade execution

**Paper-only.** No real capital. P&L is computed at Kite LTP at entry (open_at_t+1min) and exit (14:30 close or stop trigger). Stops are LTP-checked every 5 min via the existing intraday cycle.

**Three ledgers:**

| Ledger | File | Role | §10.4 lock |
|---|---|---|---|
| Holdout-of-record | `pipeline/data/research/h_2026_04_29_intraday_v1/recommendations.csv` | Live_v1 (09:30 fixed batch) | YES |
| Paired-options sidecar | `pipeline/data/research/h_2026_04_29_intraday_v1/options_paired.csv` | Forensic (futures + ATM options on same direction) | NO (forensic-only) |
| Continuous shadow | `pipeline/data/research/h_2026_04_29_intraday_v1/shadow_recs.csv` | Forensic (15-min cycle) | NO (V1.1 promotion criterion only) |

### Schedules (Windows Scheduler / VPS systemd)

| Time IST | Task | Action |
|---|---|---|
| 04:30 | `AnkaIntradayV1LoaderRefresh` | Kite 1-min cache delta refresh |
| 09:30 | `AnkaIntradayV1Open` | live_v1 batch + options_paired open |
| 09:30, 09:45, 10:00, …, 13:00 (15 entries) | `AnkaIntradayV1Shadow_HHMM` | shadow_recs append |
| 14:30 | `AnkaIntradayV1Close` | mechanical exit, all 3 ledgers |
| Sunday 02:00 (monthly) | `AnkaIntradayV1Recalibrate` | Karpathy refit, write new weights |
| 22:00 (daily during holdout) | `AnkaIntradayV1Watchdog` | integrity checks (row counts, weight age, status anomalies) |

All tasks added to `pipeline/config/anka_inventory.json` in same commit as the engine code (per `feedback_doc_sync_mandate.md`).

### Failure handling

See §14 of the data audit for the contamination map. Specific to V1 engine:
- Kite session expired at 09:30 → retry, write `STATUS=NO_KITE_SESSION`, holdout extends 1 day.
- Feature compute returns NaN for an instrument → exclude with reason, continue with available instruments.
- ≥20% of universe excluded → write `STATUS=PARTIAL_COVERAGE_ABORT`, no live_v1 trades that day, holdout extends.
- Weight-vector file missing on Monday → use last-known-good via `weights/latest_{pool}.json` symlink, Telegram alert.
- 14:30 close task fails → 14:35 backup task; on second fail, EOD reconciliation marks `EXIT_FORCED_AT_CLOSE_PRICE`, day flagged `INTEGRITY_ISSUE`.

### Telegram alerts

`[V1]` subject prefix on all CRITICAL and WARN events. No alerts for routine `EXCLUDED=feature_nan` rows.

### Surface in EOD digest

`pipeline/telegram_bot.py:format_eod_dashboard()` extends to render V1 P&L alongside the existing legacy framework output during the 44-day holdout. The user sees both side-by-side every evening, building the deprecation case in real-time.

## §13 Deprecation gate (news-driven framework)

**On V1 holdout pass (one or both pools clear §9+§9A+§9B):**
1. `pipeline/political_signals.generate_signal_card()` — kill switch flips. The function logs `KILLED_2026_07_04_PER_V1_PROMOTE` and returns empty signal card.
2. `pipeline/run_signals._run_once_inner()` — news-event-triggered spread path returns early with `KILLED_NEWS_DRIVEN_FRAMEWORK` log.
3. `pipeline/break_signal_generator.generate_break_candidates()` — unaffected; correlation-break engine survives independently (memory: `project_phase_c_kill_criteria.md` has its own deprecation criteria).
4. `pipeline/config.py:120-202` — `INDIA_SPREAD_PAIRS` renamed to `INDIA_SPREAD_PAIRS_DEPRECATED`. Importers updated in same commit.
5. All open news-driven positions close at next 14:30 mechanical exit.
6. Ledgers archived under `pipeline/data/research/news_driven_archive_2026_07/`.
7. CLAUDE.md updated to remove news-driven from clockwork schedule.
8. V2 spec drafted (cross-class long-short pairing on the passing pool).

**On V1 holdout fail (both pools fail):**
1. News-driven framework keeps running unchanged (incumbent).
2. V1 returns to drawing board. §10.4 single-touch consumed for both `H-2026-04-29-intraday-data-driven-v1-stocks` and `-indices`.
3. Failure analysis writes a post-mortem to `docs/research/h_2026_04_29_v1/post_mortem_2026_07_04.md` per `feedback_alpha_vs_timing_luck.md`.

## §14 V2 promote (cross-class long-short pairing) — deferred

Spec for V2 written **after** V1 verdict, not now. Sketch only:
- Combined 60-instrument scoring on a comparable z-score basis
- Pair construction: long top-quartile / short bottom-quartile, sector-balanced or market-cap-matched
- Cross-class natural pairs: long top-quartile-stock / short bottom-quartile-index (e.g., long RELIANCE / short NIFTY when scores diverge)
- New single-touch holdout, ~3 month window
- Variance-reduction targets: pair Sharpe ≥ 1.5× sum-of-leg-Sharpes ⇒ pairing earns its complexity

V2 only fires if V1 passes for at least one pool.

## §15 Documentation sync (per CLAUDE.md doc-sync mandate)

Same-commit updates required:
1. ✅ `docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md` (this file)
2. ✅ `docs/superpowers/specs/2026-04-29-kite-1min-data-source-audit.md` (the data audit)
3. `docs/superpowers/hypothesis-registry.jsonl` — twin entries
4. `pipeline/config/anka_inventory.json` — 19 new task entries (1 loader + 1 open + 15 shadow + 1 close + 1 recalibrate)
5. `docs/SYSTEM_OPERATIONS_MANUAL.md` — append V1 section under "Intraday Cycles" + flag deprecation candidate
6. `CLAUDE.md` — append V1 hypothesis paragraph (after H-2026-04-29-ta-karpathy-v1 paragraph)
7. `docs/SYSTEM_FAQ.md` — Sub-project B parallel deliverable
8. Memory: `project_h_2026_04_29_intraday_v1.md` — new memory file for V1 state tracking; `MEMORY.md` index updated

## §16 Reproducibility

- All Karpathy fits: random_state=42, deterministic.
- All test data fixtures: committed under `pipeline/research/intraday_v1/tests/fixtures/`.
- Holdout verdict computation: `verdict.py` is pure-functional, takes ledgers as input, emits `verdict_2026_07_04.json` deterministically.
- Re-running `verdict.py` on the same ledgers must yield byte-identical JSON (test: `test_verdict_deterministic.py`).
