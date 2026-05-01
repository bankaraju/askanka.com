# H-2026-05-01-NEUTRAL-001 — Neutral Intraday Fair-Value Reversion (NIFR) v1

## 0. Status — TRACK 1 EXPLORATION VERDICT 2026-05-01

**TRACK 1 (forensic 5y replay): NEGATIVE. Not registered. Holdout slot preserved.**

The Track-1 dispersion explorer (`pipeline/research/h_2026_05_01_neutral_fair_value_reversion/dispersion_explorer.py`) ran the §6 trigger on 2021-05-01 → 2024-04-30 across the §4 frozen 100-ticker universe before any registration row was written. Result over 438 NEUTRAL days, 1,029 triggers:

| Metric | Required for Track 2 | Track 1 actual |
|---|---|---|
| Mean bps net S1 | ≥ +25 | **−32.5** |
| Mean bps gross | (informational) | **−2.5** |
| Hit rate | ≥ 55% | **29.0%** |
| Sharpe per-trade net S1 | > 0.15 | **−0.41** |

**Decomposition:** TIME_STOP exits (n=539) earn gross +20 bps at 55.3% hit — the reversion mechanism is real but small. STOP exits at ATR×1.75 (n=490) lose −90 bps at 0% hit — the stop is mis-specified and dominates. Even with a corrected stop, gross +20 bps does not clear the 30 bps S1 cost. No |vwap_z| bucket is profitable; no monotone improvement at higher z.

**Decision:** do **not** burn the single-touch holdout slot on this exact §6 trigger. The Karpathy 6-of-8 qualifier in §10 cannot rescue a setup whose gross expectancy is structurally near-zero — qualifiers select sub-cells, they do not create positive expectancy.

**What stays open:** widened-stop forensic (ATR×3 / ATR×4), VWAP-touch exit, sector-pair NEUTRAL fade — each requires its own exploration before any registration. See `memory/project_h_2026_05_01_nifr_track1_dispersion.md` for the full forensic record. Spec §3-§17 below remains the **definition** of the family — preserved for future reference if a re-attempt is mounted with a different trigger / stop / exit choice (which would be a new hypothesis_id, not an amendment per backtesting-specs §10.4).

---

## 1. Claim

A regime-aware intraday fair-value reversion engine that:

- enters when an F&O stock becomes materially dislocated from **local fair value** during the session, defined as a large standardized deviation from intraday VWAP confirmed by a same-direction deviation from prior 60-minute balance,
- routes only when the V3-CURATED-30 regime label at the snapshot day is in the **{NEUTRAL, CAUTION}** set,
- skips on event days (RBI policy / FOMC / Lok Sabha results / Union Budget / GST council, ±1 day),
- excludes obvious runaway trend conditions using realized-range and cross-asset confirmation filters,
- and uses a **Karpathy random-search over a frozen cross-asset feature library** (index / sector / leader-basket return, volatility, breadth, dispersion, and lead-lag context) to derive the qualifier filter,

will, on a single-touch forward holdout from **2026-05-11 → 2026-08-29** (≈75 trading days), produce post-S1 net mean **≥ +25 bps** per trade with hit rate **≥ 55%** and annualised Sharpe **≥ 1.0** over **n ≥ 120 trades**.

**Stretch graduation criterion:** Sharpe ≥ 1.5 across {NEUTRAL ∪ CAUTION} graduates from EXPLORING to SIGNAL tier. Sharpe ≥ 2.0 is registered as a stretch metric only, not a gating verdict.

## 2. Why this family exists

This hypothesis is registered as a **new family** and is not a retest of the sigma-break POSSIBLE_OPPORTUNITY engine.

The purpose is to attack the unresolved **NEUTRAL** problem directly. Existing regime-aware engines make money mainly outside NEUTRAL, while NEUTRAL remains the dominant calendar bucket and behaves close to coin-toss in prior work.[cite:47][cite:50][cite:112]

This family changes the setup definition itself:

- It does **not** define opportunity as “ticker versus its PIT regime profile.”
- It defines opportunity as “ticker is stretched away from **local intraday fair value** in a market state where continuation pressure is weak.”
- It elevates **cross-asset context** (index, sector, leader basket, dispersion, vol) from a supporting feature pack into a first-class qualifier layer.[cite:175][cite:45]

The working thesis is that intraday “gap-like” dislocations recur throughout the session, not just at the open, and that they are more tradable in **NEUTRAL / CAUTION** when the broader market is not in synchronized trend mode.[cite:175][cite:49]

## 3. Pre-exploration disclosure

This hypothesis is registered **before** any dedicated 5-year minute-resolution replay of this exact family has been used to tune thresholds.

Prior observations motivating the family:

- VWAP distance appears to carry real signal weight in prior intraday feature work, but so far has been embedded inside broader ticker-centric models rather than being the primary setup definition.[cite:52][cite:111]
- Existing engines show that non-NEUTRAL regimes are more exploitable, while NEUTRAL needs a more selective tradability framework rather than more of the same signal logic.[cite:47][cite:112]
- The user has explicitly explored the idea that “gap-fade-like” reversion can happen repeatedly during the day on hourly or sub-hourly intervals, not only at the opening auction.[cite:175]

**Pre-exploration boundary:**

- The regime gate `{NEUTRAL, CAUTION}` is chosen conceptually to target the unresolved regime bucket, not from a known winning replay slice.
- The core setup, feature groups, pass thresholds, and trade rules are frozen at registration.
- The Karpathy qualifier subset / coefficients / threshold are **not pre-selected**. They are searched once on the training/validation schedule and then locked.
- No held-out data has been observed.

## 4. Universe (FROZEN)

Top 100 F&O stocks by ADV as of 2026-05-08 close, derived from `pipeline.research.auto_spread_discovery.liquidity._cached_universe_adv`.[cite:176]

Frozen files:

- `pipeline/research/h_2026_05_01_neutral_fair_value_reversion/universe_frozen.json`
- `pipeline/research/h_2026_05_01_neutral_fair_value_reversion/leader_basket_frozen.json`

### 4.1 Leader basket construction rule

Leader basket is frozen at registration and contains **12 names**:

- 2 Financials leaders
- 2 Energy leaders
- 2 IT leaders
- 2 Auto leaders
- 2 Pharma / Healthcare leaders
- 2 broad-market liquid names with consistently high intraday participation

Selection rule:

- must be in the frozen top-100 universe,
- must have full 5-year 5m coverage,
- must rank in the top decile of intraday traded value on at least 60% of the trailing 120 sessions,
- no discretionary substitutions after registration.

**Why freeze tightly:** lead-lag feature families can quietly explode multiplicity if the leader set is allowed to drift.[cite:45][cite:176]

If a ticker becomes impaired during holdout (suspension, merger, regulatory freeze), it is excluded from holdout evaluation. Verdict still requires n ≥ 120 across the surviving subset.

## 5. Data lineage

| Dataset | Path | Tier | Acceptance status |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| 5m intraday bars | `pipeline/data/fno_intraday_5m/<ticker>.csv` | D2 | Approved-for-research |
| daily OHLC (corp-action adjusted) | `pipeline/data/fno_historical/<ticker>.csv` | D2 | Approved-for-research |
| PIT regime tape v3-CURATED-30 | `pipeline/data/research/etf_v3/regime_tape_5y_pit.csv` | D2 | Approved-for-research |
| live regime label | `pipeline/data/today_regime.json` | D1 | Approved-for-deployment |
| India VIX history | `pipeline/data/india_historical/indices/INDIAVIX.csv` | D2 | Approved-for-research |
| NIFTY / BANKNIFTY / sectoral indices | `pipeline/data/sectoral_indices/*.csv` and `pipeline/data/india_historical/indices/*.csv` | D2 | Approved-for-research |
| corp-action adjustment | empirical on read | D2 | Approved-for-research |
| event calendar | `pipeline/data/research/h_2026_05_01_neutral_fair_value_reversion/event_calendar.json` | D3 | Pending acceptance |

### 5.1 Point-in-time correctness

All features must be PIT-clean:

- every rolling mean, std, percentile, correlation, breadth, or z-score uses only data available at or before the snapshot,
- no end-of-day values from the current session are allowed,
- no leader-basket membership changes after registration,
- no sector mapping changes after registration,
- all standardisations are based on trailing windows ending strictly before the current bar.[cite:45]

### 5.2 Stale-bar and completeness gate

- Any ticker with >5% missing 5m bars during the holdout window is excluded.
- Any sector / index series with missing values at >3% of snapshot timestamps invalidates the affected snapshot.
- Holdout verdict still requires n ≥ 120 valid closed trades.

## 6. Core setup definition

At each 15-minute snapshot from **10:00 → 14:00 IST**, compute:

1. `vwap_dev_z = (snap_px - cumulative_vwap_at_snap_t) / ATR_14_PIT`
2. `hour_balance_dev_z = (snap_px - prior_60m_midpoint) / ATR_14_PIT`
3. `range_spike_pctile = percentile_rank(today_realized_range_so_far, trailing_60d_range_distribution_at_same_snapshot)`
4. `trend_pressure = abs(index_ret_30m_lag1) + abs(sector_ret_30m_lag1)`

A **fair-value dislocation candidate** occurs when all of the following hold:

- regime ∈ {NEUTRAL, CAUTION}
- event_day_flag == 0
- sign(`vwap_dev_z`) == sign(`hour_balance_dev_z`)
- |`vwap_dev_z`| ≥ 1.75
- |`hour_balance_dev_z`| ≥ 1.25
- `range_spike_pctile` ≤ 90
- ticker is not halted / stale
- first-touch only per (date, ticker)

Direction:

- if `vwap_dev_z` > 0 and `hour_balance_dev_z` > 0 → **SHORT**
- if `vwap_dev_z` < 0 and `hour_balance_dev_z` < 0 → **LONG**

### 6.1 Why this trigger is intentionally narrow

This family should not become “all intraday mean reversion.” The trigger is deliberately narrow so the Karpathy layer is qualifying a **specific mechanical setup**, not manufacturing the setup itself.[cite:45][cite:46]

The two-anchor requirement (VWAP + prior 60m balance) is included because VWAP alone can over-trigger on days where price is simply repricing around a new equilibrium. Requiring both anchors to point the same way increases specificity. If later analysis shows the 60m anchor is redundant, that must be handled by a future sister hypothesis, not quietly removed midstream.[cite:52][cite:111]

## 7. Feature library (FROZEN)

Karpathy search chooses **at most 8 active features** from the frozen library below.

### 7.1 Local dislocation features

- `vwap_dev_z`
- `hour_balance_dev_z`
- `distance_from_open_z`
- `intraday_range_pctile_30m`
- `vwap_slope_30m`
- `time_since_open_bucket`
- `return_since_10am_z`
- `reversion_distance_to_vwap`

### 7.2 Cross-sectional regime features

- `xs_dispersion_snap`
- `xs_vwap_dispersion_snap`
- `nifty200_breadth_prev_close`
- `xsec_corr_delta_5d`
- `advancers_decliners_ratio_snap`

### 7.3 Index / sector / leader context

- `index_ret_15m_lag1`
- `index_ret_30m_lag1`
- `sector_ret_15m_lag1`
- `sector_ret_30m_lag1`
- `leaders_ret_mean_lag1`
- `leaders_ret_dispersion_lag1`
- `index_sector_divergence`
- `sector_vs_ticker_relative_move`
- `leader_confirmation_score`

### 7.4 Volatility / stress context

- `india_vix_level_z`
- `india_vix_change_1d_z`
- `ticker_realized_vol_spike`
- `sector_realized_vol_spike`
- `index_realized_vol_spike`
- `realized_implied_gap_intraday`

### 7.5 Event / structure flags

- `event_day_flag`
- `post_gap_morning_flag`
- `inside_prev_day_range_flag`
- `opened_outside_prev_day_range_flag`

### 7.6 Feature exclusions (explicit)

The following are **out of scope** for v1:

- NLP/news sentiment,
- options chain features,
- per-ticker bespoke indicator libraries,
- nonlinear tree models,
- dynamic leader-basket recomputation,
- per-sector parameter sets.

**Reason:** this is a high-cost family test aimed at falsifying a clear thesis, not maximizing search breadth.[cite:45][cite:46]

## 8. Signal definition

1. Generate a mechanical candidate using §6.
2. Skip if regime ∉ {NEUTRAL, CAUTION}.
3. Skip if `event_day_flag == 1`.
4. Compute all frozen feature values.
5. Apply qualifier model.
6. Trade only if model prediction ≥ frozen qualifier threshold.
7. One trade per ticker per day.

Signal side is always **toward local fair value**:

- above fair value → short,
- below fair value → long.

## 9. Trade rules

- **Entry:** at the 5m bar close of the firing snapshot.
- **Stop:** ATR(14) × 1.75.
- **Time stop:** 14:30 IST mechanical close.
- **Profit-taking:**
  - partial at first VWAP touch,
  - full at either second failure away from VWAP after touch, or 14:30,
  - if no VWAP touch occurs, full exit at 14:30.
- **Sizing:** equal notional, ₹50,000 per leg.
- **No new opens after 14:00 IST.**
- **Daily loss limit:** -₹10,000 across all legs combined → hard halt for the day.
- **Cost model:** S0 = 5 bps/side, S1 = 15 bps/side, S2 = 25 bps/side.[cite:54]

### 9.1 Mechanical baseline for margin test

Baseline comparator is:

- same §6 trigger,
- same regime and event gates,
- same trade rules,
- **no qualifier model**.

This baseline is frozen because the holdout must answer: **does the Karpathy layer add live value beyond a clean mechanical setup?**[cite:45]

## 10. Karpathy hyperparameter search

Run ONCE at registration freeze.

### 10.1 Schedule

- Training window: 2021-05-01 → 2024-04-30
- Validation window: 2024-05-01 → 2025-04-30
- Buffer: 2025-05-01 → 2025-05-31

### 10.2 Search space

- active feature cap K ∈ {4, 6, 8}
- L1 regularisation α ∈ {0.001, 0.01, 0.1, 1.0}
- qualifier threshold ∈ {0.50, 0.55, 0.60, 0.65}
- model family: sparse logistic or sparse linear probability model
- total cells: random-sampled up to 400, frozen by deterministic seed

### 10.3 Objective

Maximise **validation post-S1 Sharpe**.

### 10.4 Survival rules

A cell survives only if all of the following hold:

- BH-FDR adjusted p < 0.05 across all tested cells,[cite:45]
- validation Sharpe ≥ 0.8,
- Sharpe ≥ 0.4 in both calendar halves of validation,
- beats the no-qualifier baseline by **≥ 0.25 Sharpe** and **≥ 8 bps/trade**,
- non-zero coefficient count ≤ 8,
- no single feature contributes >50% of absolute coefficient mass.

If no cell survives, the hypothesis **FAILS at registration** and no holdout opens.

Chosen cell is committed to:
`pipeline/research/h_2026_05_01_neutral_fair_value_reversion/karpathy_chosen_cell.json`

## 11. Pass / fail criteria (holdout)

### 11.1 Primary verdict (S0)

Holdout PASSES if:

- n ≥ 120 closed trades,
- net mean ≥ +25 bps per trade,
- hit rate ≥ 55%,
- annualised Sharpe ≥ 1.0,
- max DD ≤ 20% of cumulative P&L,
- permutation p-value < 0.05.

### 11.2 S1 stress

- Sharpe ≥ 0.8,
- edge present separately in **NEUTRAL** and **CAUTION** sub-slices (Sharpe ≥ 0.4 in both).

### 11.3 Fragility

Split holdout into 3 monthly buckets. Verdict requires Sharpe ≥ 0.4 in at least **2 of 3** buckets.

### 11.4 Margin

Holdout mean must beat the mechanical baseline by **≥ 8 bps/trade**. If not, the qualifier layer adds insufficient live value and the simpler engine is preferred.

### 11.5 Sufficiency rule

If n < 120 by 2026-08-29, auto-extend to 2026-10-31. If still n < 120, declare **INSUFFICIENT_N** and archive.

## 12. Holdout window

- **Open:** 2026-05-11
- **Scheduled close:** 2026-08-29
- **Auto-extend:** 2026-10-31 if n < 120
- **Single-touch:** locked, no parameter changes after open

## 13. Statistical test

At verdict time:

- label-permutation null within (date, regime) buckets,
- 10,000 permutations,
- compare observed mean P&L to null distribution,
- p < 0.05 to PASS.

Multiplicity is paid at search time only.[cite:45]

## 14. Family boundary

This hypothesis belongs to a distinct family:

`neutral-intraday-fair-value-reversion`

It is **not**:

- a retest of sigma-break POSSIBLE_OPPORTUNITY,
- not a LAG continuation variant,
- not an opening-gap-only strategy,
- not a broad “all indicators” sweep.

Any later variant that changes:

- local fair-value definition,
- regime gate,
- stop / target logic,
- feature-family scope,
- or leader-basket construction rule,

re-opens the family for multiplicity accounting.[cite:45]

## 15. Promotion path

| Tier | Required | Action |
|---|---|---|
| EXPLORING | Pre-registered + holdout open | Status at holdout open |
| SIGNAL | §11.1 + §11.2 + §11.3 + §11.4 PASS | Auto-promote to shadow deployment |
| FLAGSHIP | Stretch Sharpe ≥ 2.0 + manual review | Explicit consent required |
| RETIRED | FAIL / FRAGILE / INSUFFICIENT_N | Archive and close family |

## 16. Engine code location

```text
pipeline/research/h_2026_05_01_neutral_fair_value_reversion/
├── universe_frozen.json
├── leader_basket_frozen.json
├── event_calendar.json
├── karpathy_chosen_cell.json
├── feature_library.py
├── fair_value_trigger.py
├── qualifier_model.py
├── holdout_runner.py
├── verdict_writer.py
└── mr_engine.py
```

## 17. Honest expectations

This is not designed to be your highest-Sharpe family. It is designed to answer a more important portfolio question: **is there a stable, tradable intraday reversion structure inside NEUTRAL / CAUTION that is distinct from your existing ticker-profile engine?**[cite:47][cite:112]

Best realistic outcome:

- Sharpe 1.0–1.5 after costs,
- decent trade count,
- a complementary family that covers the regime bucket your current engine does not solve.[cite:50][cite:112]

Main failure modes:

- NEUTRAL dislocations remain too noisy after costs,
- cross-asset context helps less than expected,
- VWAP + 60m balance is still too unstable as a fair-value definition,
- the qualifier adds complexity without sufficient margin over the mechanical baseline.[cite:112][cite:45]

If the holdout delivers only weak margin over baseline, the correct action is to prefer the simpler setup or retire the family rather than keep adding features.

**Spec frozen at registration commit. Single-touch locked.**
