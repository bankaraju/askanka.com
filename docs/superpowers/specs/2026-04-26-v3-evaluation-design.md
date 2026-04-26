# v3 Standalone Evaluation Project — Design Spec

**Date:** 2026-04-26
**Project owner:** Bharat Ankaraju
**Brainstormed via:** superpowers:brainstorming
**Status:** Spec — pending user approval before writing-plans
**Source of authority:** This spec governs v3 evaluation top-to-bottom. Both `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` (Data Policy) and `docs/superpowers/specs/backtesting-specs.txt` (Backtest Spec) bind every phase.

---

## 1. Goal

Evaluate the v3-CURATED ETF regime engine as a standalone instrument — backtest comprehensively under §0 governance, run a pre-registered forward shadow under §13.1 single-touch holdout, and publish a peer-review-grade attribution catalog with a written go/no-go for production cutover. Treat v3 as its own beast, not as a v2 variant; apply every Data Policy and Backtest Spec gate that v2 (and the spread engine) historically skipped.

## 2. Architecture

A four-phase research project:
- **Phase 0** — v2 lessons catalog + meta-lessons (constraints set for Phases 1–3)
- **Phase 1** — Universe extension to all 273 F&O tickers via Kite minute backfill (background, parallel with Phase 2 start)
- **Phase 2** — Comprehensive 5y OOS backtest with full marker decomposition + every Backtest-Spec gate
- **Phase 3** — Pre-registered forward shadow under §10.4/§13/§14
- **Phase 4** — Attribution catalog + peer-review reproducibility pack + go/no-go

Backtest runs on TWO universe configurations (existing 126-ticker AND extended 273-ticker) so universe-sensitivity is itself measured. Approach 2 (parallel tracks) is locked.

## 3. Tech Stack

- Python 3.13, pandas, numpy, scikit-learn, statsmodels (cluster-robust SE), scipy (permutation null)
- Kite Connect API (minute-bar backfill)
- Existing: `pipeline.autoresearch.etf_v3_research`, `etf_v3_rolling_refit`, `etf_v3_60d_zone_pnl`
- New: `pipeline.autoresearch.etf_v3_eval` module
- pytest for unit + regression tests
- Git for version control + commit-hash provenance

## 4. Phase 0 — v2 Lessons Catalog

### 4.1 Discovery catalog

A single document `docs/v3-evaluation/phase-0-v2-lessons-catalog.md` indexing every v2 discovery from this month + memory files. Each entry has: discovery, evidence file, implication for v3 design, test that v3 must pass to honor it.

Entries (minimum set, expand during Phase 0):

- **regime_history.csv contamination** — built with hindsight v2 weights, NOT a production audit trail. v3 must record zone-as-emitted, not zone-as-rebuilt.
- **PCR/OI multi-confirmation throttled trades** — v3 must not bolt PCR/OI back on as a second gate.
- **OPPORTUNITY split into LAG/OVERSHOOT** (#107 audit) — v3's gate must be tested separately on LAG vs OVERSHOOT slices, not pooled.
- **σ bucket × regime coupling** — v3 evaluation cannot treat σ buckets as regime-independent.
- **POSSIBLE_OPPORTUNITY beat OPPORTUNITY_LAG** — wrong slice was live; v3's gate-decision granularity must match the actual P&L-bearing slice.
- **Single-touch holdout discipline (§13.1)** burned 3 times in April — v3 forward-test window must be pre-registered, single-use.
- **SECTOR_FLIP exit is the leak** (−69 bps) — exit-rule changes interact with regime; v3 evaluation must hold the exit rule fixed unless explicitly testing it.
- **Z_CROSS in NEUTRAL = +41 bps** — v3-NEUTRAL-day refinements have unexploited room.
- **Sector dynamics on NEUTRAL days are real** — PSU BANK, BANK, PSE, ENERGY, INFRA SHORT-fades win on v3-NEUTRAL days (mean +200 to +390 bps); AUTO/IT/FMCG SHORT-fades lose. Sector-conditional gating is a credible Phase 2 marker.
- **ETF coefficient rotation is a real "regime change marker"** — weeks with large weight-rotation magnitude (51.8 std units on 2025-12-30; 37.2 on 2026-04-16) align with v3 zone shifts.
- **5y vs 3y lookback is +6.3pp swing** — v3 with longer history is materially better at its own forecasting job.
- **v3 NEUTRAL gate misapplied to H-001 SHORT engine kills P&L** — v3 forecasts next-day NIFTY direction; H-001 fades intraday extremes. Different time scales. Conceptual mismatch confirmed.

### 4.2 Meta-lessons section

Things v2 (and the spread engine) never did, that v3 evaluation now treats as table-stakes:

| Gate v2 lacked | Why it mattered | How v3 honors it |
|---|---|---|
| 5y training history | v2 trained on 3y → missed regime cycles; cycle-3 acc 47% | v3 evaluation tests 3y vs 5y vs full-panel |
| Data validation policy (§6 registration) | ETF panel used without §6 audit; SectorMapper artifacts went missing on Contabo | Phase 1 dataset registration is a hard gate before Phase 2 |
| §13A run-manifest reproducibility | Spread engine results not reproducible — no commit hash, no requirements freeze | Every Phase 2 + 3 run produces a manifest |
| §14 hypothesis pre-registration with §14.5 family denominator | Spread variants tested without declaring family — multiplicity denominator was retroactive | Phase 3 hypothesis pre-registered with family denominator declared at lock |
| §11A implementation-risk simulation | v2 backtests assumed perfect execution | Phase 2 runs all 10 §11A.1 scenarios |
| §10.4 single-use OOS | H-001/H-002/H-003 re-tested against same 60d window — 3 holdout burns this month | Phase 3 window single-use; rerun requires new window |
| §9A parameter fragility | Cadence sweep on single seed; never proved local stability | Phase 2 fragility test mandatory |
| Cross-source reconciliation (§13) | Kite minute bars never sample-checked vs EOD parquet | Phase 1 mandates 5-ticker sample reconciliation |

### 4.3 Phase 0 deliverable

[`docs/v3-evaluation/phase-0-v2-lessons-catalog.md`](../../v3-evaluation/phase-0-v2-lessons-catalog.md) — committed before Phase 1 starts. Re-read at start of each subsequent phase as constraint review. **Status:** committed at Phase 0 task 3.

## 5. Phase 1 — Universe Extension

### 5.1 Scope

Extend the 60-day intraday-break replay from 126 → 273 tickers (full F&O universe per `canonical_fno_research_v3.json`). 147 tickers added.

### 5.2 Backfill

- Kite minute-bar pull for the 60-day window (2026-02-26 → 2026-04-23) per missing ticker
- Replay engine re-run on the extended universe to produce new `intraday_break_replay_60d_v0.2_ungated.parquet`
- Failed tickers (unavailable, illiquid, name-change unresolved) documented in `tickers_failed.csv`

### 5.3 Data-policy compliance (must pass before Phase 2 reads the new parquet)

| Section | Action |
|---|---|
| §6 Source registration | `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md` |
| §7 Lineage | Per-ticker: Kite endpoint, API version, retrieval timestamp, code commit hash |
| §8 Schema contract | Frozen schema doc; CI test parquet conforms |
| §9 Cleanliness gates | Per-ticker missing-bar %, after-hours noise %, intraday gap %, holiday handling — pass §9.2 thresholds |
| §10 Adjustment mode | Declared per ticker; corp actions in window logged |
| §11 PIT correctness | Bars written as Kite emitted; no ex-post correction |
| §12 Survivorship | Universe construction documented; delisted tickers flagged |
| §13 Cross-source reconciliation | 5 tickers sample-aggregated minute→daily, compared to EOD parquet, max delta < 0.5% |
| §14 Contamination map | Bulk-deals/insider/news channels mapped per ticker |
| §17 Acceptance ladder | Must reach **Approved-for-Tier-2-research** before Phase 2 uses it |
| §21 Model binding | Confirms downstream model approval is gated on this dataset's status |

### 5.4 Deliverables

- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/kite_backfill_log.txt`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_added.csv`
- `pipeline/data/research/etf_v3_evaluation/phase_1_universe/tickers_failed.csv`
- `docs/superpowers/specs/2026-04-26-kite-minute-bars-fno-273-data-source-audit.md`
- `pipeline/autoresearch/data/intraday_break_replay_60d_v0.2_ungated.parquet`

## 6. Phase 2 — Comprehensive Backtest

### 6.1 Scope

5y OOS walk-forward of v3-CURATED, run on BOTH 126-ticker (existing) and 273-ticker (Phase 1 output) replays. Marker decomposition for every plausible signal. Every Backtest-Spec gate honored with evidence.

### 6.2 Walk-forward variants

- Lookback: 3y (756d), 5y (1200d), full (1236d)
- Refit cadence: 5d (weekly, locked)
- Karpathy iterations: 2000 per window (locked)
- Eval window: full 5y panel out-of-sample, with purged walk-forward per §10

### 6.3 Marker decomposition

Per marker, compute: standalone gate P&L, incremental contribution vs prior markers, cluster-robust SE (clustered by trade_date), permutation null p-value, fragility score.

Markers:
- **Zone gate** — NEUTRAL band sweep at ±0.25σ, ±0.5σ, ±1.0σ
- **Sector overlay** — restrict to sector-list ∈ {PSU BANK, BANK, PSE, ENERGY, INFRA, FIN SERVICE, REALTY, METAL, CONSR DURBL} (the empirical winners on NEUTRAL days)
- **Coef-delta marker** — week-over-week |Δweight| > P75 of historical → "regime in transition" flag
- **σ bucket conditional** — extreme (≥3.5σ) vs rare (2.5–3.5σ) vs mild (2.0–2.5σ)
- **Regime transition** — yesterday-zone vs today-zone change detection
- **Exit-rule** — held fixed at TIME_STOP 14:30 + ATR(14)×2 stop unless explicitly testing alternatives

### 6.4 Backtest-Spec compliance (per matrix)

| Section | Phase 2 obligation |
|---|---|
| §0.1–0.8 | All 8 research-integrity principles documented as honored |
| §1 Slippage grid | Run at S0/S1/S2 minimum (S3 informational) |
| §2 Metrics per slip | Per-slip Sharpe, mean P&L, MaxDD, hit rate |
| §3 Pass/fail | OPPORTUNITY-class trades satisfy §3.1 at S0, §3.2 at S1, §3.3 at S2 |
| §5A Data audit | Per-run cleanliness audit logged |
| §6 Survivorship | Universe construction disclosed |
| §7 Entry/exit timing | No look-ahead; §7.3 audit hook |
| §8 Direction audit | v3-zone direction vs realized direction cross-check |
| §9 Min sample size | Power analysis; trade count meets §9.1 |
| §9A Parameter fragility | Local-neighborhood test; **all 3 stability conditions** per §9A.2 |
| §9B Permutation null | Naive benchmarks (random_direction, always_short, always_long, never_trade) per §9B.1; permutation n≥10,000 |
| §10 OOS discipline | Purged walk-forward; §10.4 single-use enforced |
| §11 Liquidity | ADV threshold per ticker checked |
| §11A Implementation risk | All 10 §11A.1 failure scenarios simulated |
| §11B Alpha-after-beta | Benchmark regression against NIFTY |
| §11C Portfolio correlation | Gate per §11C.1 |
| §12 Edge decay | Rolling edge plot; regime-change detection per §12.2 |
| §13A Reproducibility | Run manifest per §13A.1; immutable artifact storage |
| §14 Hypothesis registry | Pre-registered entry per §14.1 BEFORE Phase 3 |

### 6.5 Universe sensitivity test

After Phase 1 completes, re-run every Phase 2 analysis on the 273-ticker replay. Compare:
- Does any marker's ranking change?
- Does any pass/fail verdict flip?
- Cluster-robust SE on the larger n — does any marginal claim become significant or vice versa?

### 6.6 Deliverables

- `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/runs/<run_id>/` — per-run manifests, configs, outputs, logs, pip_freeze
- `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/markers_decomposition.md`
- `pipeline/data/research/etf_v3_evaluation/phase_2_backtest/universe_sensitivity.md`
- `pipeline/autoresearch/etf_v3_eval/` — new module with backtest runners, marker decomposers, statistical tests

## 7. Phase 3 — Forward Shadow

### 7.1 Pre-registration

The strategy locked at end of Phase 2 (one specific marker combination, one gate, declared explicitly) is pre-registered:
- New hypothesis ID `H-2026-04-27-XXX` in `docs/superpowers/hypothesis-registry.jsonl`
- SHA-256 hash of pre-registration document committed; hash printed in commit message
- Family denominator declared per §14.5

### 7.2 Window

- Start: 2026-04-27 (next trading day after spec lock)
- Length: 30 trade-eligible days minimum; extend to 60 if vol-low
- Single-use per §10.4 — **no parameter changes during window**

### 7.3 Mechanics

- Daily paper trade with Kite LTP entry (per signal trigger time) + exit (mechanical TIME_STOP 14:30 or ATR stop)
- Ledger appended daily to `phase_3_forward_shadow/ledger.parquet` — immutable
- Kill-switch per §13.3: cumulative drawdown > 3× backtest MaxDD → halt and review

### 7.4 Backtest-Spec compliance

| Section | Phase 3 obligation |
|---|---|
| §10.4 single-use OOS | Strict |
| §13.1 Weekly drift report | Generated weekly; recorded in `phase_3_forward_shadow/drift_reports/` |
| §13.2 Trade-by-trade reconciliation | Daily |
| §13.3 Kill-switch | Implemented per 7.3 |
| §14.1 Pre-registration | Per 7.1 |
| §14.5 Family denominator | Declared per 7.1 |
| §15.1 Gate ladder | Outcome maps to RESEARCH / PAPER-SHADOW / LIVE-PILOT / DEPLOYED ladder |
| §15.4 Waiver register | Any waiver explicitly logged |

### 7.5 Deliverables

- `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.md`
- `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/pre_registration.sha256`
- `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/ledger.parquet`
- `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/drift_reports/<week>.md`
- `pipeline/data/research/etf_v3_evaluation/phase_3_forward_shadow/results.md` (written ONLY after window closes)

## 8. Phase 4 — Attribution Catalog & Go/No-Go

### 8.1 Success criterion (S1 + S4 combined)

**S1 quantitative bar (must pass for GO):**
- Forward-shadow cluster-robust mean P&L > 0 with p < 0.05 (clustered by trade_date)
- Beats `random_direction` permutation null (n ≥ 10,000) at p < 0.05
- ≥ 30 trade-eligible days in shadow window
- Slippage S1 result still positive

**S4 attribution catalog (always written):**
- Per-marker: standalone P&L, cluster-robust SE, incremental contribution, fragility score, permutation p-value
- Universe-sensitivity delta (126 vs 273)
- Per-v2-lesson pass/fail verdict
- Per-Backtest-Spec section: evidence link

### 8.2 Decision rule

- Both S1 conditions pass + ≥ 7 of 10 S4 markers contribute positive incremental P&L → **GO** for production cutover (separate follow-on project, not this spec)
- Either S1 condition fails → **NO-GO**, retire v3 in current form, document why
- S1 conditions inconclusive (n too low or p between 0.05 and 0.10) → **EXTEND-SHADOW** to 60 trade-days max, then re-decide

### 8.3 Peer-review reproducibility pack

Single-script replication harness `pipeline/scripts/etf_v3_eval_reproduce.sh` that, from raw `data/etf_panel.parquet` + `intraday_break_replay_60d_v0.2_ungated.parquet`, regenerates every output file. CI test runs it weekly to catch regressions.

Per Data-Policy §16 + Backtest-Spec §13A:
- Every dataset has SHA-256 hash + registration audit doc
- Every analysis has commit hash + pip_freeze + seed + config + run log
- Every statistical claim has test name + reference + effect size + CI + p-value + n + cluster level
- Every conclusion has source-citation footnote
- Counter-evidence section: what would invalidate, did we check

### 8.4 Deliverables

- `pipeline/data/research/etf_v3_evaluation/phase_4_attribution/final_catalog.md`
- `pipeline/data/research/etf_v3_evaluation/phase_4_attribution/go_no_go.md`
- `pipeline/data/research/etf_v3_evaluation/phase_4_attribution/reproducibility_index.md`
- `pipeline/scripts/etf_v3_eval_reproduce.sh`

## 9. File / Output Layout

```
pipeline/data/research/etf_v3_evaluation/
├── manifest.json
├── phase_0_v2_lessons/
│   └── catalog.md
├── phase_1_universe/
│   ├── kite_backfill_log.txt
│   ├── tickers_added.csv
│   ├── tickers_failed.csv
│   └── data_audit.md
├── phase_2_backtest/
│   ├── runs/<run_id>/
│   │   ├── config.json
│   │   ├── pip_freeze.txt
│   │   ├── output.parquet
│   │   ├── stdout.log
│   │   └── manifest.json
│   ├── markers_decomposition.md
│   └── universe_sensitivity.md
├── phase_3_forward_shadow/
│   ├── pre_registration.md
│   ├── pre_registration.sha256
│   ├── ledger.parquet
│   ├── drift_reports/<week>.md
│   └── results.md
└── phase_4_attribution/
    ├── final_catalog.md
    ├── go_no_go.md
    └── reproducibility_index.md
```

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Phase 1 Kite backfill fails for some tickers | §6 registration requires per-ticker status; failed tickers documented but excluded; Phase 2 runs without them |
| Phase 2 finds no marker passes statistical bar | S4 catalog still written; project still produces value (honest confirmation) |
| Phase 3 vol-low → < 30 trade-days | Spec allows extending shadow up to 60 trade-days before declaring inconclusive |
| Mid-project temptation to test "one more variant" | Spec explicitly forbids parameter changes after Phase 3 lock; new variant requires its own follow-on with new holdout |
| Universe extension changes Phase 2 verdict | Universe-sensitivity test in §6.5 explicitly measures this; verdict held until both run on both universes |
| 5y refit overfits despite higher pooled accuracy | §9A parameter fragility test must pass; in-fit vs OOS gap > 10pp triggers caution flag |
| Phase 3 burns the holdout for nothing | Pre-registration discipline + family denominator declared up-front; no post-hoc re-framing allowed |

## 11. Testing Approach

- **Phase 0:** doc only, no tests
- **Phase 1:** backfill script — unit tests for ticker validation, schema conformance, gap detection; integration test against 1-ticker live Kite call
- **Phase 2:** every backtest runner — regression test against fixed seed + tiny universe; cluster-robust SE function — unit test against statsmodels; permutation null — unit test against known synthetic edge cases
- **Phase 3:** paper-trade ledger writer — integration test with simulated Kite LTP stream
- **Phase 4:** replication harness — CI weekly run; spec self-review per superpowers

## 12. Dependencies & Sequencing

```
Phase 0 ──┐
          ├──> Phase 2 (126-ticker) ──┐
Phase 1 ──┤                            ├──> Phase 2 (273-ticker, universe-sensitivity) ──> Phase 3 (lock + run) ──> Phase 4
          │                            │
          └──────────────────────────┘
```

Phase 0 + Phase 1 start together. Phase 2 (126-ticker arm) starts after Phase 0 finishes. Phase 2 (273-ticker arm) waits for Phase 1. Phase 3 waits for Phase 2 fully complete (both arms). Phase 4 written after Phase 3 window closes.

## 13. Timeline Estimate

| Phase | Days |
|---|---|
| 0 — v2 lessons catalog | 1–2 |
| 1 — Universe extension (background) | 2–3 |
| 2 — Comprehensive backtest (both arms) | 5–7 |
| 3 — Forward shadow | 30–60 trade-days = ~6–12 calendar weeks |
| 4 — Attribution catalog | 1–2 |

**Total active research:** ~9–14 working days (Phases 0, 1, 2, 4)
**Plus forward-shadow window:** ~6–12 calendar weeks

## 14. Out of Scope (this project)

- Production cutover of v2 → v3 (separate follow-on, depends on Phase 4 GO outcome)
- v3 reoptimizer or daily-signal job re-architecture
- Telegram / dashboard / website wiring of v3
- Spread-engine v3 evaluation (different engine, different P&L; could be a parallel project under same governance)

## 15. Approval

This spec must be approved by the user before writing-plans skill is invoked. Per superpowers:brainstorming hard-gate.
