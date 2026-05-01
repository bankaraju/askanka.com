# H-2026-05-01-phase-c-mr-karpathy-v1 — Regime-Aware Mean-Revert Intraday with 8-Feature Karpathy Search

**Hypothesis ID:** `H-2026-05-01-phase-c-mr-karpathy-v1`
**Strategy class:** `regime-conditional-mean-revert-intraday`
**Family scope:** intraday-mean-revert, single hypothesis (no multiplicity correction)
**Standards version:** 1.0_2026-04-23 (`docs/superpowers/specs/backtesting-specs.txt`)
**Spec version:** v1.0
**Predecessor:** `H-2026-04-26-001` (sigma-break-mechanical-v1) and the legacy Phase C live LAG-routed shadow

---

## 1. Claim

A regime-aware intraday mean-revert engine that:
- enters when an F&O stock crosses |z| ≥ 4 against its (ticker, regime) PIT profile in the **POSSIBLE_OPPORTUNITY** direction (move opposite to expected — the live engine routes LAG; this hypothesis routes the inverse),
- routes only when the V3-CURATED-30 regime label at the snapshot day is in the **{RISK-ON, CAUTION}** set,
- skips on event days (RBI policy / FOMC / Lok Sabha results / Union Budget / GST council, ±1 day),
- and uses a **6-of-8 Karpathy random-search** over a fixed feature library to derive the qualifier filter,

will, on a single-touch forward holdout from 2026-05-04 → 2026-08-01 (≈63 trading days), produce post-S1 net mean ≥ +30 bps per trade with hit rate ≥ 55% and annualised Sharpe ≥ 1.0 over n ≥ 100 trades.

**Stretch graduation criterion:** Sharpe ≥ 1.5 across {RISK-ON ∪ CAUTION} graduates from EXPLORING to SIGNAL tier. Sharpe ≥ 2.0 (which Bharat asked the design to target) would graduate to flagship intraday strategy — registered as a stretch metric, not a gating verdict.

## 2. Pre-exploration disclosure

This hypothesis is registered AFTER observing the 5-year minute-resolution Phase C replay output committed in `5386033` (2026-05-01). The replay revealed:

- LAG-routed live engine: 0 trades on 5y × 100 tickers — structurally untradeable.
- POSSIBLE_OPPORTUNITY routing all-regime: n=433, mean −30.6 bps, hit 51.5%, fails kill criteria.
- POSSIBLE_OPPORTUNITY in **RISK-ON**: n=60, mean **+53.5 bps**, hit **60.0%**, Sharpe ≈ 1.6 (computed post-hoc on the slice).
- POSSIBLE_OPPORTUNITY in **CAUTION**: n=75, mean **+19.4 bps**, hit **61.3%**.
- POSSIBLE_OPPORTUNITY in **NEUTRAL**: n=252, mean **−69.3 bps**, hit 46.4% — the bleed regime.
- 2024-06-04 Lok Sabha results day: 65 trades on a single day, mean −317 bps. Single-event tail risk.

**Observed-on-development-data summary** (this is the in-sample evidence per backtesting-specs §14.4):

| Slice | n | mean bps | hit % |
|---|---:|---:|---:|
| RISK-ON ∪ CAUTION (combined) | 135 | +34.5 | 60.7% |
| RISK-ON ∪ CAUTION ex-event-days | ~125 | ~+45 | ~61% |

**Pre-exploration boundary:**

- Regime gate `{RISK-ON, CAUTION}` is the ONLY parameter chosen with reference to the 5y replay. It is locked at registration.
- Event-day skip is added a-priori from the 2024-06-04 observation; the calendar source (RBI / Fed / NSE / Bharat-supplied) is locked at registration.
- Pass thresholds (mean ≥ +30 bps, hit ≥ 55%, Sharpe ≥ 1.0) are inherited from backtesting-specs §3.1 framework defaults — NOT derived from the +34.5 bps in-sample observation. The mean-bps gate is set ABOVE S1 cost (round-trip ~30 bps after slippage) plus a 100% buffer, not below the in-sample mean.
- The Karpathy 6-of-8 feature subset is **not pre-selected**. It is hyperparameter-searched on a held-out training window (2021-05 → 2024-04, 3 years) before holdout opens. The random search runs once at registration freeze; its output (the chosen subset + Lasso coefficients) is locked.

**No held-out data has been observed.** The 63-day forward window 2026-05-04 → 2026-08-01 is the single-touch holdout. The 2026-05-01 / 02 (today + tomorrow) bars are pre-registration; first holdout bar is 2026-05-04 (Monday).

## 3. Universe (FROZEN)

Top 100 F&O stocks by ADV as of 2026-04-30 close, derived from `pipeline.research.auto_spread_discovery.liquidity._cached_universe_adv`. Frozen list cached to `pipeline/research/h_2026_05_01_phase_c_mr_karpathy/universe_frozen.json` at registration time.

**Why these 100:** matches the existing 5y 5m intraday cache (we have data for 100/158 F&O tickers; rest are below ADV cutoff or missing 5y depth). No survivorship bias since universe is locked from current liquid set, not back-projected.

If a ticker is materially impaired during the holdout (suspension, regulatory action, merger), it is excluded from holdout evaluation but the verdict still requires n ≥ 100 across the active subset.

## 4. Data lineage

| Dataset | Path | Tier | Acceptance status |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| 5m intraday bars | `pipeline/data/fno_intraday_5m/<ticker>.csv` | D2 | Approved-for-research (5y, full session, 99.4% coverage verified 2026-05-01) |
| daily OHLC (corp-action adjusted) | `pipeline/data/fno_historical/<ticker>.csv` | D2 | Approved-for-research |
| PIT regime tape v3-CURATED-30 | `pipeline/data/research/etf_v3/regime_tape_5y_pit.csv` | D2 | Approved-for-research |
| live regime label | `pipeline/data/today_regime.json` | D1 | Approved-for-deployment (live tape; PIT-correct per `project_h_001_regime_bug_2026_04_27`) |
| India VIX history | `pipeline/data/india_historical/indices/INDIAVIX.csv` | D2 | Approved-for-research |
| sectoral indices | `pipeline/data/sectoral_indices/*.csv` | D2 | Approved-for-research |
| corp-action adjustment | empirical (computed from daily/5m disagreement) | D2 | Approved-for-research (committed `679841c`, 16 unit tests) |
| event calendar | `pipeline/data/research/h_2026_05_01_phase_c_mr_karpathy/event_calendar.json` (NEW) | D3 | Pending acceptance — see §4.1 |
| Phase C profile training | `pipeline.research.phase_c_backtest.profile.train_profile` | D2 | Approved-for-research |

**Adjustment mode:** corp-action adjusted on read via empirical factor (daily-close / 5m-last-close ratio per date). Documented in `pipeline/research/phase_c_minute/corp_action_adjuster.py`.

**Point-in-time correctness:** verified — all features computed from bars dated < snapshot day. Walk-forward profile training has 1-month buffer between train end and holdout start. Regime tape is the v3-CURATED-30 PIT version (NOT the contaminated `regime_history.csv` per `memory/reference_regime_history_csv_contamination`).

**Stale-bar gate:** any 5m series with > 5% missing bars during the holdout window disqualifies that ticker from the holdout. Verdict requires n ≥ 100 across the surviving subset.

### 4.1 Event calendar dataset

A NEW dataset is registered as part of this hypothesis. Schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "events": [
    {"date": "YYYY-MM-DD", "type": "RBI_POLICY|FOMC|ELECTION_RESULTS|UNION_BUDGET|GST_COUNCIL", "country": "IN|US"}
  ]
}
```

Pre-registration calendar covers 2021-05-01 → 2026-08-31. Source: NSE published calendar + RBI website + manual entry of historic Lok Sabha results days (2024-06-04, 2019-05-23, 2014-05-16, 2009-05-16). File audited per `anka_data_validation_policy_global_standard.md` §6/§8 before holdout opens.

The skip rule fires for `event_date - 1 ≤ snapshot_day ≤ event_date + 1` (3-day window around event).

## 5. Feature library (FROZEN, 8 features)

Karpathy random search picks 6 of these 8 as the active feature subset for the qualifier model.

### 5.1 Cross-sectional dispersion (1)
`xs_dispersion_1100` = std of intraday %chg-from-open across the F&O top-100 universe at the snapshot's snap_t. Computed PIT (universe at snap_day, %chg from snap_day's open).
**Why:** distinguishes "rotation NEUTRAL" (high dispersion = tradeable) from "compressed grind" (low dispersion = coin toss). Pre-registered as #1 feature.

### 5.2 Realized vs implied vol gap (1)
`realized_implied_gap` = (today's first-30min ATR pct) / (India VIX × √(30/(252×6.25*60)) ) — i.e., realised 30-min vol over implied 30-min vol.
**Why:** >1.2 = trend day, <0.8 = mean-revert day. Should make POSSIBLE_OPPORTUNITY work better when this ratio is low.

### 5.3 NIFTY-200 breadth (1)
`breadth_pct_above_20dma` = % of NIFTY-200 with close > 20-DMA on the snap day's previous close.
**Why:** continuation/reversion regime detector independent of the V3 regime label.

### 5.4 Event-day flag (1)
`event_day_flag` = 1 if snap_day is in the ±1 window of any event in §4.1 calendar; else 0.
**Why:** binary kill-feature. The Karpathy search will (likely) learn to filter event_day_flag == 1 to no-trade.

### 5.5 Sector relative-strength z-score (1)
`sector_rs_zscore` = (today's sector intraday %chg-from-open at snap_t) − (sector 20d mean intraday %chg-from-open at snap_t equivalent), divided by the 20d std. Sector mapping from `pipeline.scorecard_v2.sector_mapper.SectorMapper` (frozen at registration).
**Why:** today's actual mover, not yesterday's leader.

### 5.6 Cross-sector correlation collapse (1)
`xsec_corr_delta_5d` = average pairwise sector intraday-return correlation today (across the 8 sectors at snap_t) − the trailing 5-day mean of the same.
**Why:** sharp drop = rotation regime favours mean-revert; sharp rise = trend regime favours continuation. Should help the model differentiate when POSSIBLE_OPPORTUNITY edge is real.

### 5.7 VWAP deviation z-score (1)
`vwap_dev_zscore` = (snap_px − cumulative_vwap_at_snap_t) / ATR_14_PIT.
**Why:** existing live signal formalised as a numerical feature.

### 5.8 News density z-score (1)
`news_density_zscore` = (count of EODHD news items mentioning the ticker in the last 24h before snap_t) z-scored against the 60-day rolling distribution.
**Why:** news-driven moves tend to trend (less mean-revertable) — high news-density should down-weight mean-revert signal. Honest read: weakest of the 8 features, kept for completeness.

## 6. Signal definition

At each 15-min snapshot from 09:30 → 14:00 IST:

1. Compute `intraday_ret = (snap_px − prev_close) / prev_close` (corp-action adjusted).
2. Look up (ticker, regime) profile expected_return + std_return from PIT walk-forward profile (training window 2021-05 → 2024-04).
3. Compute `z = (intraday_ret − expected_return) / std_return`.
4. Apply classifier (`pipeline/research/phase_c_minute/replay.py::_classify`) — fire only on `POSSIBLE_OPPORTUNITY` (|z| ≥ 4 AND opposite-sign-from-expected).
5. Skip if regime ∉ {RISK-ON, CAUTION}.
6. Skip if `event_day_flag` == 1.
7. Apply Karpathy qualifier model. Trade only if model output ≥ qualifier threshold (Lasso-derived per the search; locked at registration).
8. First-touch dedup per (date, ticker) — same as live.

Signal direction: `synth_side = expected_direction` (mean-revert toward expected — same convention as the v1 replay).

## 7. Trade rules

- **Entry:** at the 5m bar's close at the firing snapshot.
- **Stop:** ATR(14) × 2.0 — same as live LAG routing (per CLAUDE.md 14:30 cutoff invariant).
- **Time stop:** 14:30 IST mechanical close at the next 5m bar's close.
- **Sizing:** equal notional across legs, ₹50,000 per leg (matches Phase C live shadow notional).
- **No new opens after 14:30 IST** (CLAUDE.md cutoff is enforced by snap times ending at 14:00).
- **Cost model:** 5 bps per side baseline (S0); evaluation also runs at S1 (15 bps/side) and S2 (25 bps/side).

## 8. Karpathy hyperparameter search

Run ONCE at registration freeze, then locked.

- **Objective:** in-sample Sharpe (post-S1) on training window 2021-05-01 → 2024-04-30.
- **Grid:**
  - Feature subset: 6 of 8 features (`C(8, 6) = 28` combinations)
  - Lasso α (regularisation): {0.001, 0.01, 0.1, 1.0}
  - Qualifier threshold: {0.0, 0.1, 0.2, 0.3} (Lasso prediction ≥ threshold to trade)
  - Total grid: 28 × 4 × 4 = 448 cells
- **BH-FDR multiplicity correction** across the 448 cells (per backtesting-specs §0.3).
- **Survival rule:** the cell with highest in-sample Sharpe AND BH-FDR adjusted p < 0.05 wins. If no cell survives BH-FDR, the hypothesis FAILS at registration and is not committed to the registry — predecessor (LAG-routed Phase C) stays the live tape.
- **Fragility check** (backtesting-specs §9A): the chosen cell must produce post-S1 Sharpe ≥ 0.5 in BOTH calendar halves of the training window (2021-05/2022-10 vs 2022-11/2024-04). Otherwise FAIL.
- **Margin check** (backtesting-specs §9B.1): the chosen cell's in-sample Sharpe must beat the regime-gated-but-no-Karpathy baseline (POSSIBLE_OPPORTUNITY + {RISK-ON, CAUTION} only) by ≥ 0.3 Sharpe. Otherwise FAIL — the Karpathy layer adds no value.

If §8 produces a valid cell, it is committed to `pipeline/research/h_2026_05_01_phase_c_mr_karpathy/karpathy_chosen_cell.json` and locked.

## 9. Pass / fail criteria (holdout)

Per backtesting-specs §3.1 / §3.2 / §9 / §9A / §9B.

### 9.1 Primary verdict (S0 base costs)
Holdout PASSES if:
- n ≥ 100 closed trades over the holdout window
- Net mean ≥ +30 bps per trade
- Hit rate ≥ 55%
- Annualised Sharpe ≥ 1.0
- Max DD ≤ 20% of cumulative P&L
- Permutation p-value < 0.05 (label-permutation null, 10,000 perms, single hypothesis — no multiplicity)

If n < 100 by 2026-08-01, auto-extend to 2026-10-31 (or n = 100, whichever first). If n < 100 by 2026-10-31, declare INSUFFICIENT_N and auto-archive.

### 9.2 S1 stress (backtesting-specs §3.2)
- Sharpe ≥ 0.8
- Max DD ≤ 25%
- Edge present (Sharpe ≥ 0.5) in both regime sub-slices (RISK-ON alone AND CAUTION alone)

If S1 fails, the strategy is "Fragile to realistic slippage" and stays in research-only.

### 9.3 Stretch graduation (informational, not gating)
- Sharpe ≥ 1.5 → graduates EXPLORING → SIGNAL.
- Sharpe ≥ 2.0 → graduates SIGNAL → FLAGSHIP. Bharat's stretch target.

### 9.4 Fragility (backtesting-specs §9A)
Holdout split into 3 monthly buckets. Verdict requires Sharpe ≥ 0.5 in ≥ 2 of 3 buckets (else FRAGILE → research-only).

### 9.5 Margin (backtesting-specs §9B.1)
Holdout net mean must beat the regime-gated-no-Karpathy baseline (POSSIBLE_OPPORTUNITY + {RISK-ON, CAUTION}, no qualifier model) by ≥ 10 bps per trade. Else the Karpathy layer adds no live value and the simpler regime-gated rule is the better candidate for v2.

## 10. Slippage stress grid

Run S0, S1, S2 on the holdout output (per backtesting-specs §1.1). Reported in the verdict; only S0 is gating per §9.1, S1 per §9.2.

## 11. Holdout window

- **Open:** 2026-05-04 (Monday)
- **Scheduled close:** 2026-08-01 (≈63 trading days)
- **Auto-extend rule:** if n < 100 by 2026-08-01, extend to 2026-10-31 (no parameter changes during extension per §10.4 strict).
- **Min n for verdict:** 100
- **Single-touch:** locked. No parameter changes (regime gate / event calendar / Karpathy cell / pass thresholds) between 2026-05-04 and verdict date.

## 12. Statistical test

Label-permutation null: at verdict time, shuffle trade labels (LONG↔SHORT) 10,000 times within (date, regime) buckets, recompute mean P&L on each shuffle, compare observed mean to the null distribution. p < 0.05 to PASS.

Single hypothesis — no Bonferroni or BH-FDR correction at verdict (the multiplicity was paid in §8's grid search).

## 13. Multiplicity correction

- Search-time: BH-FDR across 448 cells in §8.
- Verdict-time: single hypothesis, no correction.
- Family scope: this hypothesis is registered as a single member of the `regime-conditional-mean-revert-intraday` family. Any sister hypothesis (e.g., a NEUTRAL-only variant) registered later would re-open the family and require Bonferroni adjustment of this verdict.

## 14. Predecessor relationship

| Predecessor | Relationship | Status |
|---|---|---|
| `H-2026-04-26-001` (sigma-break-mechanical-v1) | Same-family directional sigma-break engine, opposite routing. H-001 routes LAG (continuation); this routes POSSIBLE_OPPORTUNITY (mean-revert). | Live holdout 2026-04-27 → 2026-05-26. Both run in parallel — distinct families. |
| Phase C v1 live shadow (LAG-routed) | Same engine, this hypothesis adds 5 layers on top: regime gate, event-day skip, Karpathy qualifier, distinct trade direction (POSSIBLE_OPPORTUNITY vs LAG). | Phase C v1 stays live until H-001 holdout closes 2026-05-26; pivots to v2 IF this hypothesis PASSES holdout. |
| Mechanical 60-day replay (`project_mechanical_60day_replay`) | Source of original POSSIBLE_OPPORTUNITY-beats-LAG observation at daily-bar resolution. | Closed; this hypothesis tests at minute-resolution. |

**No parameter from any predecessor is being re-run.** The regime gate is new (predecessor was regime-agnostic). The Karpathy qualifier is new. The event-day skip is new. The pass thresholds are framework defaults, not predecessor-derived.

## 15. Stop-loss / position sizing

- Per-leg ATR(14) × 2.0 stop (matches Phase C live).
- Notional ₹50,000 per leg.
- No leverage. No averaging-down. No correlation hedge across baskets.
- Daily loss limit: -₹10,000 across all legs combined → hard halt for the day.

## 16. Promotion path

| Tier | Required | Action |
|---|---|---|
| EXPLORING | Pre-registered + holdout open | Status at 2026-05-04. |
| SIGNAL | §9.1 + §9.4 + §9.5 PASS at verdict | Auto-promote, terminal post added to `pipeline/scripts/scheduled_tasks/` for live shadow. |
| FLAGSHIP | Stretch §9.3 PASS (Sharpe ≥ 2) | Manual review by Bharat; explicit consent required to re-allocate live capital. |
| RETIRED | §9.1 FAIL OR §9.4 FAIL OR §9.5 FAIL | Spec marked CONSUMED in registry; v2 cannot re-test same parameter set. |

## 17. Engine code location

```
pipeline/research/h_2026_05_01_phase_c_mr_karpathy/
├── universe_frozen.json                       # frozen at registration
├── event_calendar.json                        # frozen at registration
├── karpathy_chosen_cell.json                  # locked after §8 search
├── feature_library.py                         # 8 PIT feature computers
├── regime_gate.py                             # {RISK-ON, CAUTION} gate
├── event_day_skip.py                          # ±1 window skip
├── mr_signal_generator.py                     # POSSIBLE_OPPORTUNITY routing + qualifier  ## strategy-gate-tracked
├── mr_engine.py                               # backtest + holdout orchestrator           ## strategy-gate-tracked
├── karpathy_search.py                         # §8 grid search runner
├── holdout_runner.py                          # daily holdout fire
└── verdict_writer.py                          # §9 verdict at scheduled close
```

## 18. Doc-sync mandate (CLAUDE.md)

This commit MUST update in lockstep:
1. This spec doc.
2. `docs/superpowers/hypothesis-registry.jsonl` — single new row.
3. `pipeline/config/anka_inventory.json` — 2 new scheduled-task rows (open at 09:30, close at 14:30).
4. `CLAUDE.md` Clockwork Schedule section.
5. `memory/project_h_2026_05_01_phase_c_mr_karpathy_v1.md` — new memory file with this hypothesis tracked.

## 19. Honest expectations

Bharat asked for Sharpe > 2. The 5-y replay's RISK-ON slice gave Sharpe ≈ 1.6 ungated (no Karpathy filter, no event-day skip). Adding the Karpathy qualifier should add 0.2-0.4 Sharpe by removing weak signals; event-day skip should add 0.1-0.2 by removing tail blowups. Combined honest expectation: **Sharpe 1.8 - 2.0** in the holdout — *if* the in-sample regime conditioning persists out-of-sample.

The single biggest failure mode is regime non-stationarity: 2024 was a much worse year for POSSIBLE_OPPORTUNITY than 2022-23, even excluding the 2024-06-04 event. If 2026-Q2/Q3 looks like 2024 rather than 2022, the holdout fails.

If the holdout returns Sharpe 1.0-1.5, that's still useful: PASS at §9.1, EXPLORING-tier deployment, real edge identified, just below the stretch target. If it returns Sharpe < 1.0, the v2 line of investigation closes and we pivot to the gap-fade direction noted in `project_phase_c_kill_criteria`.

---

**Spec frozen at registration commit. Single-touch locked.**
