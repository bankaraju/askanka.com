# Regime-Aware Stock / Pair Autoresearch Engine — Design Spec

**Status:** Frozen design, awaiting user approval before writing implementation plan.
**Author:** bharatankaraju + Claude Opus 4.7
**Date:** 2026-04-24
**Supersedes intent of:** `autoresearch template.txt` (this spec is the formalization)

---

## 0. Purpose and Posture

Discover, per ETF regime, which single-stock and stock-pair constructions produce positive out-of-sample risk-adjusted returns that beat the best existing incumbent. Replace ad-hoc, per-strategy hypothesis-generation with one audited pipeline. Every trading strategy going forward — including ones currently running — enters, competes, and either survives or retires under one set of rules.

**Honest reflection on prior work.** Previous compliance rituals ran on partially unverified infrastructure. The H-2026-04-24-003 audit discovered that `pipeline/data/regime_history.csv` does not exist on disk; the runner silently fell back to empty regime features, so 3–4 of its 236 feature dims were zeros-only. Earlier compliance artifacts cannot be treated as §0.3-clean until we rebuild the data foundation. Prior results become exploratory evidence and intuition, not basis for live decisions.

**Posture: Disciplined-Pragmatic.**
- Do not kill live routes for continuity's sake.
- Enter them as incumbents in this engine.
- Compete them against challengers under the new rules.
- Survivors stay live. Losers retire via a logged process.
- No new trading strategy ships outside this engine, ever again.

**Hard retirements (no debate, documented in §15):**
- Phase C cross-sectional geometry (H-2026-04-24-002 abandoned, H-2026-04-24-003 FAIL).
- Any production code path that reads `pipeline/data/regime_history.csv` today — it does not exist, so that code is not regime-aware in practice, only in claim.

**Incumbents who must re-earn their place (seeded in Task 0):**
- Reverse Regime Phase A/B (collapsed to one entry — they are horizon variants of one engine).
- Phase C LAG route (currently alert-only per H-2026-04-23-002 FAIL).
- Spread Intelligence regime-gated spreads (primary flavour).
- Spread Intelligence secondary flavour (sector-neutral / narrower universe).
- Overshoot per-ticker fades v1 (bootstrap-clean per-ticker p-values, no portfolio-level §0.3).
- FCS top-k long-only.
- FCS top-k long/short (market-neutral).
- TA fingerprint / TA scorer v1 (walk-forward validated, never pre-registered).
- OPUS trust-score cross-sectional (trust-tilted).
- Overshoot per-ticker fades, defence-excluded variant.

If Task 0 inventory finds fewer than 10 have clean per-regime Sharpe + CI, the `strategy_results_10.json` artifact ships with fewer rows. Empty slots are fine.

---

## 1. Non-Goals

- Not tuning the 10 existing strategies. Those are frozen incumbents; they do not get updated inside this engine.
- Not a live-execution engine. This is a research + pre-registration + holdout + lifecycle framework. Execution remains the responsibility of the existing `pipeline/` modules (scheduler, Kite adapter, etc.).
- Not a universal hyperparameter optimizer. The DSL is deliberately narrow; broadening it is a v2 spec, not a mid-loop tweak.
- Not replacing `backtesting-specs.txt` (v1.0, Section 0–16). This engine consumes those compliance tools (slippage_grid, permutation null, BH-FDR, Sharpe-CI, CUSUM decay, portfolio gate). It does not redefine them.

---

## 2. Architecture (high level)

```
      ┌─────────────────────────────────────────────────────────┐
      │                  Data foundation (Task 0)                │
      │  regime_history.csv   strategy_results_10.json           │
      │  cointegrated_pairs_v1.json   ssf_availability.json      │
      └────────────────┬────────────────────────────────────────┘
                       │
                       v
      ┌─────────────────────────────────────────────────────────┐
      │                 DSL grammar v1 (frozen)                  │
      │  20 features × 4 ops × 8 thresholds × 3 holds            │
      │    × 4 constructions × 5 regimes = 38,400 non-pair       │
      │    + ~864,000 pair points (pair_id is 1-of-~900)         │
      └────────────────┬────────────────────────────────────────┘
                       │
                       v
      ┌─────────────────────────────────────────────────────────┐
      │             Karpathy loop (sees train+val only)          │
      │  LLM proposer → DSL point → in-sample backtest           │
      │  → net-of-cost Sharpe → incumbent-gap test               │
      │  → pass/fail → append to proposal_log.jsonl              │
      └────────────────┬────────────────────────────────────────┘
                       │  qualifies for holdout (beats incumbent ≥Δ, p_gap ≤ 0.05)
                       v
      ┌─────────────────────────────────────────────────────────┐
      │       Pre-registration + holdout gate (one touch)        │
      │  hypothesis-registry.jsonl append → holdout backtest     │
      │  → BH-FDR over holdout family at q=0.1                   │
      │  → HOLDOUT_PASS or REJECTED                              │
      └────────────────┬────────────────────────────────────────┘
                       │
                       v
      ┌─────────────────────────────────────────────────────────┐
      │          Forward shadow (60d / 50 events minimum)        │
      │  paper-trade alongside incumbent → forward Sharpe        │
      └────────────────┬────────────────────────────────────────┘
                       │
                       v
      ┌─────────────────────────────────────────────────────────┐
      │                   Promotion to live                      │
      │  displaces lowest-Sharpe incumbent in that regime        │
      │  ≤ 2 promotions / regime / quarter                       │
      │  promotions.jsonl append                                 │
      └─────────────────────────────────────────────────────────┘
```

Kill switch (git pre-commit hook + CI check) sits outside this diagram and refuses any new file under `pipeline/` that implements a trading rule unless an accompanying `hypothesis-registry.jsonl` entry is present.

---

## 3. Data Foundation (Task 0)

Task 0 is upstream of everything. Nothing else starts until Task 0 outputs validate.

**3.1 `pipeline/data/regime_history.csv`**
- Columns: `date` (ISO), `regime_zone` (one of 5 discrete labels), `score` (numeric regime score), `confidence` (0–100).
- Coverage: 2021-04-23 → today, business days only.
- Causality: each row must be computable using only pre-`date` data. No look-ahead.
- Regression test `pipeline/tests/autoresearch/test_regime_history_integrity.py` that fails loudly if the file is missing, empty, has gaps > 5 business days, has fewer than 4 distinct regime labels, or shows future-referencing values.
- Producer: modify the ETF regime engine (`pipeline/signals/etf_regime/`) to emit historical rows on demand, not only the rolling current label.

**3.2 `pipeline/autoresearch/regime_autoresearch/data/strategy_results_10.json`**
- Frozen at Task 0 completion, refreshed quarterly.
- Per strategy × regime × slippage-level row: `{strategy_id, strategy_name, regime, n_obs, sharpe_point, sharpe_ci_low, sharpe_ci_high, p_value_vs_zero, p_value_vs_buy_hold, compliance_artifact_path, status}`.
- Values populated from existing compliance artifacts where present; `INSUFFICIENT_POWER` flag otherwise.
- Fewer than 10 strategies at launch is acceptable.

**3.3 `pipeline/autoresearch/regime_autoresearch/data/cointegrated_pairs_v1.json`**
- Within-broad-sector pairs only (using 18-sector `BROAD_SECTOR` map from `pipeline/autoresearch/overshoot_reversion_backtest.py`).
- Pair universe: ≈900 pairs pre-filter → cointegration Engle-Granger test on train window only (2021-04-23 → 2024-04-22) → keep pairs with p < 0.05.
- Frozen artifact. Pairs not in this file are not proposable. Refresh at each major spec version bump only.

**3.4 `pipeline/autoresearch/regime_autoresearch/data/ssf_availability.json`**
- Ticker → {is_ssf_available: bool, borrow_cost_bps: int, notes: str}.
- Source: Kite SSF instrument list + Zerodha stock-lending fee table.
- Any proposal involving a short leg on a ticker without SSF availability is auto-rejected before backtest.

**3.5 `pipeline/autoresearch/regime_autoresearch/data/vix_history.csv`**
- Date, vix_close. Same causality rules as regime_history. Currently missing — Task 0 builds it.

---

## 4. Data Split

- **Train + validation:** 2021-04-23 → 2024-04-22 (≈750 business days).
  - Inside: 4 purged folds with 2-day embargo for alpha / threshold selection inside a single proposal.
  - Rolling walk-forward CV as used in H-2026-04-24-003's LassoCV alpha selector. Proven code path.
- **Holdout:** 2024-04-23 → 2026-04-23 (≈500 business days).
  - Touched exactly once per pre-registered rule.
  - Holdout-outcomes log `holdout_outcomes.jsonl` is write-once, and the LLM proposer has no read access to it.
  - Per-regime holdout n-estimates (rough): assuming 5 regimes roughly balanced over 500 days → ≈100 days/regime. H-003 had ≈51; this is nearly 2× the power.

**Per-regime n-floor (§9.3 carryover):** if a regime's holdout window has fewer than 50 events for a given rule, the rule gets PARTIAL verdict, not PASS. Not enough power to decide.

---

## 5. DSL Grammar v1 (frozen)

**Slot structure** — every proposal is a tuple:

```
proposal := {
  construction_type ∈ {single_long, single_short, long_short_basket, pair},
  feature ∈ regime_features_v1,        // 20 features, see §6
  threshold_op ∈ {>, <, top_k, bottom_k},
  threshold_value ∈ discrete_grid,     // 8 points, feature-specific
  hold_horizon ∈ {1, 5, 20},           // trading days
  regime ∈ {R1, R2, R3, R4, R5},       // 5 ETF zones
  pair_id                                // only if construction_type == pair; must be in cointegrated_pairs_v1
}
```

**Grammar cardinality:**
- Non-pair (single_long, single_short, long_short_basket): 3 × 20 × 4 × 8 × 3 × 5 = **28,800 points**.
- Pair: 1 × 20 × 4 × 8 × 3 × 5 × ~900 = **~864,000 points**.
- Total: ~892,800 theoretical grammar points.

We treat pair constructions as their own sub-family with independent BH-FDR budget to keep single-stock multiplicity honest. The 500-proposal-per-regime cap applies separately to non-pair and pair sub-families (so up to 500 × 5 × 2 = 5,000 proposals total across all regimes × sub-families).

**Composite-score rules (e.g., linear combos) are v2.** v1 is single-feature thresholds only.

**Rule execution:**
- `single_long`: on regime-R day T, long tickers where feature(T) meets threshold condition. Hold `hold_horizon` days. Equal-weight.
- `single_short`: same, SSF-available tickers only, including borrow cost in net-Sharpe.
- `long_short_basket`: on regime-R day T, long top-k / short bottom-k by feature(T). Market-neutral equal-weight. k ∈ threshold_value discrete grid.
- `pair`: on regime-R day T, evaluate cointegrated spread; trade when spread z-score exceeds threshold_value; exit at threshold_value/2 or after hold_horizon days, whichever first.

**Proposer interface:** LLM emits a JSON object matching the `proposal` schema. Static validator rejects out-of-grammar proposals without charging them to the proposal log (they never existed).

---

## 6. Feature Library v1 (`regime_features_v1`, frozen)

All causal. All derivable from `price_panel + regime_history + ssf_availability + OPUS trust scores`.

**Momentum (5):** `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`, `mom_ratio_20_60`.
**Volatility (3):** `vol_20d`, `vol_percentile_252d`, `vol_of_vol_60d`.
**Cross-sectional residual (3):** `resid_vs_sector_1d`, `z_resid_vs_sector_20d`, `beta_nifty_60d`.
**Breadth / trend (2):** `days_from_52w_high`, `dist_from_52w_high_pct`.
**Macro sensitivity (2):** `beta_vix_60d`, `macro_composite_60d_corr`.
**Microstructure (3):** `adv_20d`, `adv_percentile_252d`, `turnover_ratio_20d`.
**Quality (2):** `trust_score` (OPUS), `trust_sector_rank`.

**Explicitly excluded from v1:**
- `p_regime_*` probability vector — would re-enable soft conditioning and defeat the discrete-regime lock.
- Options / IV / PCR features — insufficient clean historical depth (< 1 year of intraday OI).
- News / sentiment features — not panel-consistent across tickers.

**Adding features requires a new spec version (`regime_features_v2`) and a new hypothesis family, not a mid-loop tweak.**

**Noted for v2 consideration only:** swap one momentum slot for an earnings_yield / book-to-price feature from OPUS once the fundamentals panel is clean.

---

## 7. Proposer Interface and Karpathy Loop

**Proposer:**
- LLM constrained to the DSL grammar (§5).
- Can read:
  - Prior proposal log entries **where `stage == "in_sample"`** — full JSON including `dsl_point`, `net_sharpe_in_sample`, `gap_vs_incumbent`, `p_gap`, `result`, `rejection_reason`. Capped to the last 200 entries per regime to bound context size.
  - Current `strategy_results_10.json` with regime-incumbent Sharpe targets.
  - `regime_features_v1` spec (feature definitions, allowed threshold ops, threshold grids).
- Cannot read: `holdout_outcomes.jsonl`, `forward_shadow_ledger.jsonl`, `promotions.jsonl`. Enforced by filesystem ACL on the directory containing these logs (see §9, §13).
- Model selection: Haiku 4.5 or Sonnet 4.6 — not Opus — since the proposer's job is narrow (fill DSL slots). Pinned to a specific model version in `constants.py`; upgrading requires a spec version bump.

**Loop per regime:**

```
while proposals_this_regime < 500 AND consecutive_no_improve < 50:
    proposal = proposer.generate(regime, seen_proposals_in_sample_only)
    if not grammar_validator(proposal): continue  # not logged
    if proposal involves short leg on no-SSF ticker: reject_with_reason, log
    backtest_in_sample(proposal, train_val_window)
      → net_sharpe_in_sample (after slippage + borrow)
    incumbent = best_incumbent_for_regime_or_buy_hold_fallback
    gap = net_sharpe_in_sample - incumbent.sharpe
    p_gap = bootstrap_test(gap)
    if gap >= Δ_in AND p_gap <= 0.05:
        append to proposal_log as qualified_for_holdout
        append to hypothesis-registry.jsonl (full pre-registration JSON)
    else:
        append to proposal_log as rejected_in_sample
        consecutive_no_improve += 1
    proposals_this_regime += 1
```

**Iteration modes (user-locked Q3):**
- **Mode 1 (human-in-loop):** first 50–100 proposals per regime run interactively. User sees the proposer's suggestions, watches rejection reasons, confirms behavior is non-degenerate. Default mode for the first regime.
- **Mode 2 (autonomous):** after Mode 1 validation, remaining proposals run as an overnight batch job. Still writes to the same proposal_log. Still gated by 500 hard cap and 50-consecutive-no-improvement soft cap.

**Stopping rules (both active):**
- Hard: 500 proposals per regime — no more.
- Soft: 50 consecutive proposals with no net-Sharpe improvement over best-qualified-to-date → stop this regime.

**Constant Δ_in (in-sample gap hurdle):** 0.15 net Sharpe. This is the bar to qualify for holdout, not the bar to pass holdout. Purpose is to filter obvious noise from reaching holdout.

---

## 8. Proposal Log Schema

Append-only JSONL at `pipeline/autoresearch/regime_autoresearch/data/proposal_log.jsonl`. One row per DSL point the proposer emits (including rejected). This file is the BH-FDR multiplicity denominator.

```json
{
  "proposal_id": "P-000123",
  "timestamp_iso": "2026-04-24T08:32:11Z",
  "regime": "NEUTRAL",
  "dsl_point": { ...full tuple from §5... },
  "stage": "in_sample",
  "backtest_window": {"start": "2021-04-23", "end": "2024-04-22"},
  "n_events_in_sample": 284,
  "net_sharpe_in_sample": 0.42,
  "gross_sharpe_in_sample": 0.68,
  "transaction_cost_bps": 19.2,
  "borrow_cost_bps": 0.0,
  "incumbent_regime_benchmark": {"strategy_id": "spread_intel_primary", "sharpe": 0.31},
  "gap_vs_incumbent": 0.11,
  "p_gap": 0.24,
  "result": "rejected_in_sample",
  "rejection_reason": "p_gap > 0.05",
  "qualifies_for_holdout": false,
  "ssf_check_passed": true,
  "grammar_validator_passed": true,
  "proposer_model": "claude-haiku-4-5-20251001"
}
```

Rejected proposals are tracked with the same schema but `result ∈ {rejected_in_sample, rejected_no_ssf, rejected_insufficient_power}`. This keeps the multiplicity honest — family size for BH-FDR at q=0.1 is `count(result != rejected_no_ssf)` (we don't count rules that were infeasible to run).

---

## 9. Holdout Outcomes Log

Write-once JSONL at `pipeline/autoresearch/regime_autoresearch/data/holdout_outcomes.jsonl`. Filesystem ACL denies read to the proposer's runtime user.

```json
{
  "proposal_id": "P-000123",
  "hypothesis_id": "H-2026-05-12-001",
  "timestamp_iso": "2026-05-12T09:00:00Z",
  "regime": "NEUTRAL",
  "dsl_point": { ...copy from proposal log... },
  "holdout_window": {"start": "2024-04-23", "end": "2026-04-23"},
  "n_events_holdout": 97,
  "net_sharpe_holdout": 0.38,
  "gap_vs_incumbent_holdout": 0.07,
  "p_gap_holdout": 0.04,
  "bh_fdr_family_size": 142,
  "bh_fdr_rank": 7,
  "bh_fdr_threshold": 0.00493,
  "result": "holdout_pass",
  "next_state": "forward_shadow"
}
```

BH-FDR is computed once per holdout-touch batch, not per individual touch. Rules are batched at regular intervals (e.g., monthly) and BH-FDR applied to the batch's p-values.

---

## 10. Cost Model and SSF Integration

**Slippage:** every backtest runs through `pipeline/autoresearch/overshoot_compliance/slippage_grid.py` with the `zerodha-ssf-2025-04` cost model. Net-of-cost Sharpe at slippage level S1 (realistic) is the headline metric. S0 (frictionless) and S2 (stressed) are also reported.

**SSF gate:** any proposal with a short leg must be restricted to SSF-available tickers. Proposals that reference non-SSF short tickers are rejected pre-backtest (logged as `rejected_no_ssf`, excluded from BH-FDR denominator).

**Borrow cost:** for SSF short legs, `borrow_cost_bps` from `ssf_availability.json` is subtracted from gross P&L daily. Most F&O stocks: 10–30 bps annualized.

**Minimum turnover filter:** if a rule's implied turnover exceeds 400% annualized (i.e., rebalance every ≤ 6 days on 25% of universe), the cost drag typically exceeds the gross Sharpe. Proposals passing this filter are rare; we don't impose a hard cap, but the `transaction_cost_bps` field in the proposal log makes the cost visible.

---

## 11. Incumbent Hurdle (with scarcity fallback)

For each regime R:
1. Look up incumbent candidates from `strategy_results_10.json` filtered to `regime == R AND status == LIVE AND sharpe_ci_low > 0`.
2. **If ≥ 3 clean incumbents exist:** `incumbent_for_R = max(candidates, key=lambda s: s.sharpe_point)`. Hurdle is "beat this Sharpe by Δ with p_gap ≤ α_in in-sample, and by Δ_holdout in holdout."
3. **If < 3 clean incumbents exist (scarcity fallback):** incumbent is regime-conditional buy-and-hold (long Nifty during regime-R days). Hurdle is the H-2026-04-24-003 S1 margin test (net Sharpe margin ≥ Δ, p_gap ≤ α). This is identical to H-003's naive-comparator logic and prevents scarcity-rich regimes from becoming p-hacking sweet spots.

**Δ values:**
- `Δ_in = 0.15` (in-sample gap to qualify for holdout).
- `Δ_holdout = 0.10` (holdout gap to earn HOLDOUT_PASS status). Lower than Δ_in because holdout sample is smaller; too high a bar blocks real finds.

---

## 12. Lifecycle State Machine

```
PROPOSED
  │  proposer emits, grammar-validated
  │  in-sample backtest: gap ≥ Δ_in AND p_gap ≤ 0.05
  v
PRE_REGISTERED
  │  entry appended to hypothesis-registry.jsonl
  │  single holdout touch
  │  BH-FDR q=0.1 over current holdout batch
  v
HOLDOUT_PASS
  │  enters forward shadow for ≥60 trading days / ≥50 events
  │  paper-trades alongside incumbent
  │  forward net-Sharpe ≥ incumbent net-Sharpe on same window
  v
PROMOTED_LIVE
  │  displaces lowest-Sharpe incumbent in regime R
  │  subject to rate limit: ≤ 2 promotions / regime / quarter
  │  promotions.jsonl append

RETIRED   (incumbent displaced OR CUSUM recent-24m < 50% per §12 of backtesting-specs)
DEAD      (hard retirement, cannot re-enter: Phase C cross-sec, regime-cond on missing data)
REJECTED  (failed at any earlier gate)
```

**10 slots per regime, not 10 total.** A strategy can occupy slots in multiple regimes.

**Fewer than 10 at launch is fine.** Task 0 populates what exists; empty slots invite challengers.

**Every state transition is a git commit** to `pipeline/autoresearch/regime_autoresearch/data/promotions.jsonl`. No silent transitions.

---

## 13. Kill Switch (no-bypass invariant)

**Pre-commit git hook** at `pipeline/scripts/hooks/pre-commit-strategy-gate.sh`:
- Scans staged files under `pipeline/`.
- Flags any new file matching `*_strategy.py`, `*_signal_generator.py`, `*_backtest.py`, `*_ranker.py`, `*_engine.py` unless accompanied by a new row in `docs/superpowers/hypothesis-registry.jsonl` with `status ∈ {PRE_REGISTERED, LIVE}`.
- Rejects the commit with a message pointing at this spec.

**CI check** at `.github/workflows/strategy-gate.yml`:
- Same scan on every PR.
- Required check before merge to master.

**Why this matters:** every bypass of this gate in the past year has ended in a FAIL or abandonment (H-001, H-002, H-003). This hook makes future bypasses impossible-by-default, not discouraged-by-culture.

---

## 14. Success Criteria

For v1 to be considered a success, six months after launch we must have:
1. `regime_history.csv` complete and passing its integrity test on every run.
2. `strategy_results_10.json` populated with per-regime Sharpe+CI or INSUFFICIENT_POWER for every incumbent.
3. At least one full proposer loop run per regime (500 or 50-consecutive-no-improve, whichever first).
4. Each regime either: (a) has a HOLDOUT_PASS challenger entering forward shadow, or (b) has zero challengers that beat the incumbent — an informative negative result.
5. Zero strategy code merged to master that bypasses the registry. Zero.
6. Full audit trail: every proposal, rejection, pre-registration, holdout touch, forward-shadow result, promotion, retirement captured in the JSONL logs.

Not required for success: profitable promotions. It's fine if the engine produces zero promotions in v1 and a lot of clean negative results. That's still the right epistemic state.

---

## 15. Hard Retirements (deprecation notice)

On Task 0 completion the following deprecations go live in the same commit:

- **Phase C cross-sectional geometry** (`pipeline/autoresearch/phase_c_cross_sectional/` as a live strategy). Code stays for artifact reproducibility but is marked `DEAD` in `strategy_results_10.json`. Cannot re-enter the engine without a new hypothesis registration.
- **All production code reading `pipeline/data/regime_history.csv` before Task 0 emits it.** `grep -rn "regime_history.csv" pipeline/` during Task 0 produces the retirement list. Each is either fixed (upgraded to read the new file once built) or retired (removed / marked DEAD).

The deprecation commit carries a message referencing this spec's commit SHA.

---

## 16. File Layout

```
pipeline/autoresearch/regime_autoresearch/
├── __init__.py
├── constants.py                    # ΔΔ's, n-floors, grammar cardinalities
├── dsl.py                          # Grammar validator + rule compiler
├── features.py                     # regime_features_v1 computations (causal)
├── proposer.py                     # LLM-driven DSL proposer
├── in_sample_runner.py             # train+val backtest + incumbent-gap test
├── holdout_runner.py               # single-touch holdout backtest + BH-FDR
├── forward_shadow.py               # paper-trade supervisor for HOLDOUT_PASS rules
├── promotions.py                   # state transitions + displacement logic
├── incumbents.py                   # loads strategy_results_10.json, computes hurdles
├── data/
│   ├── strategy_results_10.json
│   ├── cointegrated_pairs_v1.json
│   ├── ssf_availability.json
│   ├── proposal_log.jsonl
│   ├── holdout_outcomes.jsonl      # ACL: proposer-runtime no read
│   ├── forward_shadow_ledger.jsonl
│   └── promotions.jsonl
└── tests/
    ├── test_regime_history_integrity.py
    ├── test_dsl_grammar.py
    ├── test_proposer_view_isolation.py
    ├── test_bh_fdr_multiplicity.py
    ├── test_lifecycle_state_machine.py
    └── test_kill_switch.py
```

Compliance reuse from existing `pipeline/autoresearch/overshoot_compliance/`: slippage_grid, metrics, manifest, data_audit, beta_regression, cusum_decay, portfolio_gate. Not re-implemented.

---

## 17. Task Roadmap

1. **Task 0 — Data foundation.** Build `regime_history.csv` + integrity test; build `strategy_results_10.json` from existing compliance artifacts; build `cointegrated_pairs_v1.json`; build `ssf_availability.json`; build `vix_history.csv`. Commit deprecation of Phase C cross-sec + regime-conditioned-on-phantom-data code in the same commit.
2. **Task 1 — DSL grammar + feature library.** Implement `dsl.py` (validator + compiler), `features.py` (20 features, all causal, covered by unit tests).
3. **Task 2 — Proposer + in-sample runner.** Implement the LLM proposer against the DSL, the in-sample backtest loop, cost model integration, proposal log schema.
4. **Task 3 — Holdout runner + BH-FDR.** Implement the holdout-touch pipeline, BH-FDR batch logic, proposer-read-isolation (filesystem ACL).
5. **Task 4 — Forward shadow supervisor.** Paper-trade runner for HOLDOUT_PASS rules; integrates with existing shadow-ledger infrastructure.
6. **Task 5 — Lifecycle + promotions.** State transitions, displacement logic, rate-limit enforcement, promotions.jsonl schema.
7. **Task 6 — Kill switch.** Pre-commit hook + CI workflow.
8. **Task 7 — First regime pilot.** Run Mode 1 (human-in-loop) on one regime (suggest NEUTRAL, since that's the ETF engine's default state and highest n).
9. **Task 8 — Incumbent re-qualification audit.** For each current incumbent, verify its `strategy_results_10.json` row is consistent with the latest compliance artifact. Flag any stale.
10. **Task 9 — Docs sync.** Update `SYSTEM_OPERATIONS_MANUAL.md` with the autoresearch pipeline, `CLAUDE.md` with the kill-switch policy, memory index.
11. **Task 10 — Success-criteria verification stub.** A script that emits a monthly report against §14 criteria.

The implementation plan (produced by `writing-plans` after this spec is approved) will expand each into bite-sized TDD tasks.

---

## 18. Out of Scope for v1

- Composite-score rules (linear combos of features).
- Options-derived features (IV, PCR, OI flow).
- News / sentiment features.
- Cross-regime rules (rules that condition on regime-transition, not regime-state).
- LLM-generated free-form rule descriptions outside the DSL grammar.
- Re-tuning of the 10 incumbents.
- Automatic re-fitting of incumbents' internal parameters.
- Live execution of promoted rules (rules go live-shadow only; live-capital decision is manual, outside the engine).

These land in v2 and later, after v1 produces its first forward-shadow result.

---

## 19. Open questions for user review

1. **Forward-shadow floor.** Is 60 trading days / 50 events the right minimum, or should we go longer (90/75) given H-003's small-n brittleness? Recommendation: start at 60/50, measure forward-Sharpe CI width on the first 3 HOLDOUT_PASS candidates, tighten in v2 if too noisy.
2. **VIX history provenance.** Do we have a clean 2021–2024 India VIX close source? Recommendation: yfinance `^INDIAVIX` primary, NSE archive fallback. Validate causality and gap-fill policy (forward-fill ≤ 2 bars only) in Task 0 itself.
3. **BH-FDR batch cadence.** §9 says holdout BH-FDR runs per batch. Is monthly right, or should we fire when ≥10 PRE_REGISTERED rules have accumulated, whichever first? The implementation plan will pin a specific rule — confirm your preference.
