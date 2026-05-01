# Theme Detector v1 — elevation plan to main model

**Date:** 2026-05-01
**Status:** plan, gated on retro pass
**Spec ref:** `docs/superpowers/specs/2026-05-01-theme-detector-design.md`
**Audit ref:** `docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md`

## Operating thesis (Bharat, 2026-05-01 conversation)

> Markets are entering shorter cyclical cycles + more thematic cycles where
> AI / Digital / Visual Data / Robotics will change the markets. The Theme
> Detector must become the main strategic engine — not a research scorer —
> with live paper trades visible on Anka Terminal so we can watch our own
> models perform in a live setting.

This document records the elevation path from "Phase 1 build complete + first
frame written" (current state, 2026-05-01) to "main model running live paper
trades on Terminal" (target state).

## The 4-gate validation pipeline (Bharat's explicit framing)

Every model in this system passes through four gates before promotion:

| Gate | What it validates | Theme Detector status (2026-05-01) |
|---|---|---|
| **1. Data validation** | Every input dataset registered, schema-checked, PIT-correct, cleanliness-gated per `anka_data_validation_policy_global_standard.md` §6-§14 | PARTIAL — Phase 1 build status documented, but no formal schema contracts or cleanliness gates yet for the 4 newly-wired Trendlyne sources |
| **2. Backtesting** | Historical retro with proper cost/slippage; in-sample + null baseline | RUNNING NOW — 156-week post-COVID-from-2023 retro on VPS (`retro.py`) |
| **3. Shadow P&L** | Paper trades with real-time mark-to-market; paired (futures + ATM options) ledger per the standing pattern | NOT STARTED — gate is closed until retro passes |
| **4. Terminal LIVE** | Live tab on Anka Terminal: lifecycle stages, transitions, trade ledger, P&L; user watches in real-time | NOT STARTED — gate is closed until shadow runs |

A model cannot reach a higher gate until the prior gate is closed. Failing
any gate kicks back to the previous gate for amendment.

## Forward sequence (gated execution)

### Phase E1 — Retro verdict (in progress, 2026-05-01)
- 156-week retro (2023-05-07 → 2026-04-26) running on VPS as of 23:30 IST
  2026-05-01
- Pass criteria (forward-only equivalent of §8 gates A/B/C/D):
  - **Gate A (lead-time):** ≥5 of 7 in-window §8 reference cycles fire
    PRE_IGNITION ≥4w before their RS-breakout date
  - **Gate B (stability):** ≤35% of PRE_IGNITION transitions invert to DORMANT
    within 12 weeks
  - **Gate C (false-positive discipline):** ≥30% of PRE_IGNITION transitions
    reach IGNITION OR cleanly to FALSE_POSITIVE after ≥26w
  - **Null-baseline check:** real run distinguishable from member-shuffle null
    on lead-time distribution (qualitative this round; bootstrap CI in v2)
- **Outcome path:**
  - PASS → close Gate 2, advance to Phase E2
  - FAIL → register a v1.1 amendment with documented diagnostic; re-run

### Phase E2 — Data validation tightening (gates Gate 1)
Required even if Phase E1 passes, before any shadow P&L:
- Schema contracts for the 4 Trendlyne sources (FII screener, IPO calendar,
  multigroup_curtailed, shareholding_panel) — column names, dtypes, nullability
- Cleanliness gates: row count thresholds, fingerprint deltas across snapshots,
  PIT-cutoff assertions
- Replace the C2 + C5 proxies with their spec sources OR formally accept the
  proxies in §21 with documented fidelity caveats (Bharat decision)
- Resolve the §8 retro-backfill design-doc amendment (currently Path 1
  recommended: forward-only 16-week acceptance gate; supersedes the original
  2018-2024 retro requirement)
- Update `anka_data_validation_policy_global_standard.md` §21 for the detector

### Phase E3 — Shadow P&L wiring (gates Gate 3)
Per the standing paired-shadow pattern (memory:
`feedback_paired_shadow_pattern.md`): every directional view ships with a
paired (futures + ATM options) forward-only OOS shadow ledger.

Theme Detector triggers:
- `DORMANT → PRE_IGNITION` — open SHADOW LONG paired entry on top-N members by
  per-name strength (start with N=3 per theme, configurable)
- `PRE_IGNITION → IGNITION` — scale up size on existing entry
- `IGNITION → MATURE` — hold
- `IGNITION → DECAY` or `MATURE → DECAY` — close paired entry
- `PRE_IGNITION → DORMANT` (inversion) — close at small loss; flag for B-stability accounting
- `PRE_IGNITION → FALSE_POSITIVE` — close

Ledger files (forensic-only at v1, no live execution):
- `pipeline/data/research/theme_detector/shadow/futures_ledger.csv`
- `pipeline/data/research/theme_detector/shadow/options_ledger.csv`
- `pipeline/data/research/theme_detector/shadow/transitions.csv`

Paired-shadow open/close timing: standing pattern is T+1 09:25 IST open at
Kite LTP, mechanical close at 14:30 IST per the 14:30 cutoff feedback memory.

**45-day shadow window** (Bharat amendment to §8.3): the original 4-week gate
is extended to 45 days to give the credibility-penalty 12-week window meaningful
overlap with the shadow period. ~6.4 weeks. Auto-extend to 60 days if N
transitions < 8 (covering at least 8 stage transitions for sample-size reasons).

### Phase E4 — Terminal LIVE surface (gates Gate 4)
Anka Terminal dependency: existing tab structure (memory:
`project_terminal_tab_map.md`) currently has 10 tabs. Theme Detector becomes
**Tab 11: Themes**.

Tab content (top to bottom):
- **Lifecycle stage banner** — 12 themes with current stage + current_strength
  + age_in_stage_weeks. Sortable by strength desc.
- **Transition timeline** — last 30 days of stage transitions, click-through
  to the underlying weekly frame JSON
- **Per-theme drill-down panel** — selected theme shows: signal_breakdown,
  member contributions, time-series of belief/confirmation/strength,
  paper-trade ledger entries
- **Paired-shadow tape** — live OPEN positions in the shadow ledger with
  Kite LTP-driven mark-to-market P&L, exactly as Phase C paired-shadow tape
  works today
- **Provenance row** — engine version, last run timestamp, data-source
  freshness per `feedback_surface_provenance_in_ui.md`

Rendering: vanilla JS + Lightweight Charts per the locked Terminal stack.

### Phase E5 — Promotion to "main model"
Only after E1-E4 all gate-pass + 45-day shadow window completes successfully:
- Hypothesis registry entry promoting Theme Detector from "infrastructure" to
  "primary universe + weight provider for downstream sizing"
- ETF engine (current "brain") and Theme Detector run in parallel for one
  quarter; if their disagreement rate < 30% AND Theme Detector's per-name
  weighting beats ETF-engine's regime-conditional weighting on shadow P&L,
  Theme Detector becomes primary
- Until this disagreement-test runs, Theme Detector is a **second** opinion,
  not a replacement

## v2 theme expansion (deferred, post-elevation)

Bharat (2026-05-01): "shorter cyclical cycles and more thematic cycles where
AI/Digital/Visual Data/Robotics will change the markets."

Current 12 themes capture ~70% of the post-COVID Indian equity narrative space.
Material gaps for the 2026-2028 cycle:

| Missing theme | What it would capture | Candidate members |
|---|---|---|
| AI_INFRASTRUCTURE_INDIA | Listed names with GPU/AI-compute capex exposure | (TBD — NYK list shortest; PLI for AI compute ramp 2026+) |
| GENERATIVE_MEDIA_VISUAL_DATA | Visual / video / generative AI applications layer | (TBD — Indian listed pure-play candidates thin; possibly TATAELXSI overlap) |
| INDUSTRIAL_ROBOTICS | Industrial automation + factory robotics (separate from HOSPITALS_ROBOTICS_LEAN) | KIRLOSKAR, ABB (overlap with CAPEX_PLI), other CG |
| FAST_CYCLE_DIGITAL | Q-comm + fintech adjacency + consumer-tech expansion of QUICK_COMMERCE | NYKAA (already in QC), PAYTM, POLICYBZR |

v2 also revisits the credibility-penalty 12-week threshold and the 26-week
MATURE/FALSE_POSITIVE threshold — Bharat's "shorter cyclical cycles" point
suggests these may need to compress by ~30% for the 2026+ regime.

## Open questions parked for Bharat

1. §8 retro-backfill — Path 1 (forward-only 16w) or Path 2 (confirmation-only
   retro)? Recommendation Path 1.
2. Scheduler registration — laptop Windows Scheduler now, or wait until VPS
   sync of Trendlyne raw_exports is wired? Recommendation: VPS systemd primary,
   wire Trendlyne sync first.
3. v2 theme expansion — should AI_INFRASTRUCTURE_INDIA be added to the v1
   universe right now (re-freezing themes_frozen.json) or held to v2 freeze
   per the 2026-05-01 freeze contract?

## Documentation lineage

- Spec: `docs/superpowers/specs/2026-05-01-theme-detector-design.md` (FROZEN
  v1.0 2026-05-01)
- Audit: `docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md`
  (Phase 1 Build status appended 2026-05-01; §8 infeasibility finding
  appended 2026-05-01)
- This plan: capturing the 2026-05-01 conversation that elevated the detector
  from research-infrastructure to candidate primary model
