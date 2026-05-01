# Theme Detector v1 — design spec

**Document:** `docs/superpowers/specs/2026-05-01-theme-detector-design.md`
**Status:** DESIGN — not built
**Author:** Bharat Ankaraju + Claude Opus 4.7
**Date:** 2026-05-01 (revised after Bharat's feedback in `additions to the plan.txt`)
**Standards version:** 1.0_2026-04-23 (`docs/superpowers/specs/backtesting-specs.txt`)
**Data validation policy:** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`

---

## 0. Why this is NOT a hypothesis

The theme detector does NOT claim alpha. It is **infrastructure** that downstream hypotheses consume:

- It does NOT enter or exit positions.
- It does NOT constitute a trading rule under the kill-switch regex.
- It does NOT need a `hypothesis-registry.jsonl` row.
- Its file names will NOT match `*_signal_generator.py` / `*_backtest.py` / `*_engine.py` / `*_strategy.py` / `*_ranker.py`.

It DOES need: a design spec (this doc), a data audit (companion doc), validation evidence, governance, and a test suite. The output it produces (`themes_<date>.json`) becomes a **frozen input** at registration time of any downstream hypothesis that consumes it.

---

## 1. Claim

> **Markets emit observable signatures of structural change BEFORE financial-performance confirmation. A multi-signal detector running weekly on Indian equity market data can separate BELIEF (early capital movement) from CONFIRMATION (public price/breadth validation), classify themes into a 5-state lifecycle (including a FALSE_POSITIVE state for narrative-without-capital), and rank constituent names — providing a market-derived universe AND a market-derived weighting input for downstream hypotheses.**

The detector replaces hand-picked sector universes (e.g., the 40-name Banks+IT in `H-2026-05-01-EARNINGS-DRIFT-LONG-v1`) with empirically-detected theme buckets. It does NOT predict price direction; it identifies which structural change is currently occurring AND distinguishes durable themes from press-release noise.

---

## 2. Why this exists (motivation)

Hand-picked universes age badly. The 40-name Banks+IT frozen for `EARNINGS-DRIFT-LONG-v1` smuggles one analyst's prior into every backtest. Real structural drivers (AI-headwind to mass IT, digital-bank tailwind to private banks, war-economy capex to defence, robotics-adoption to hospitals, data-centre capital-formation cluster) are NOT inferable from sector labels. They emit market-side signatures — capital flow, M&A, capex disclosure, IPO clustering, RS breakouts — that the detector observes.

Three methodological non-negotiables (per Bharat 2026-05-01):

1. **Don't structurally amputate.** A naive "drop sectors with declining RS" rule kills hospitals at the exact moment robotics-adoption capex begins. The lifecycle classifier explicitly carries a **PRE_IGNITION** stage so leading indicators are not dismissed.
2. **Don't average across regime shifts.** Pre-COVID / COVID / post-COVID / AI-era are structurally different. The detector reports stage age and inversion warnings; downstream hypotheses can window training data accordingly.
3. **Don't promote narrative-without-capital.** Capex headlines and M&A chatter often never become durable themes. The lifecycle classifier explicitly carries a **FALSE_POSITIVE** state — when belief signals fired but no confirmation followed within a defined window. Without this state, the engine over-promotes story stocks.

---

## 3. Signal families — Belief vs Confirmation (FROZEN at v1)

The detector splits all signals into TWO independent buckets, deliberately. Belief signals reveal where early/strategic capital is positioning; confirmation signals reveal where public price/breadth has validated. This separation is the core architectural commitment — it directly enables:
- **Scope decisions** (who's in the universe) driven by Belief OR Confirmation
- **Weight decisions** (how big the position) driven primarily by Confirmation, with Belief as a small uplift
- **FALSE_POSITIVE detection** when Belief fires but Confirmation never follows

### 3.1 BELIEF signals (early capital / strategic positioning)

Each emits a per-theme score on `[0, 1]`. Aggregated into `belief_score`.

| ID | Signal | Phase | Source |
|---|---|---|---|
| B1 | M&A flow | 2 | NSE/BSE corporate announcements (M_AND_A, SCHEME_OF_ARRANGEMENT, OPEN_OFFER) |
| B2 | Capex disclosure | 2 | NSE/BSE corporate filings (NEW_PROJECT, CAPACITY_EXPANSION, FUND_RAISE_FOR_CAPEX) |
| B3 | FII shareholding drift | 1 | Quarterly NSE shareholding pattern filings (rolling 4-quarter delta in FII holding %) |
| B4 | Block deal accumulation | 2 | NSE block-deals (forward-only from 2026-04-24); historical NOT available |
| B5 | IPO cluster | 1 | NSE main-board listings calendar (3+ IPOs in same sub-sector in 6m) |

**Aggregation:** `belief_score = max(weighted_sum(B1..B5), 0)` clipped to `[0, 1]`. Weights frozen at v1 freeze.

### 3.2 CONFIRMATION signals (public validation)

Each emits a per-theme score on `[0, 1]`. Aggregated into `confirmation_score`.

| ID | Signal | Phase | Source |
|---|---|---|---|
| C1 | RS-breakout | 1 | Sectoral indices (NIFTY-IT, NIFTY-BANK, etc.); 200d RS-vs-NIFTY-50 + 90d slope |
| C2 | Cap-drift | 1 | NIFTY-500 free-float weight history (rolling 6m delta) |
| C3 | F&O inclusion | 1 | NSE F&O eligibility list; promotion = institutional-depth crossing threshold |
| C4 | Options skew | 3 | Future v2 — IV term structure / put-call premium |
| C5 | Earnings breadth | 1 | % of theme members posting QoQ EPS surprise > 0; rolling 2-quarter |
| C6 | Sector breadth | 1 | % of theme members above 200d MA; rolling 4-week |

**Aggregation:** `confirmation_score = max(weighted_sum(C1..C6), 0)` clipped to `[0, 1]`. Weights frozen at v1 freeze.

### 3.3 Theme credibility penalty (FROZEN at v1)

Per Bharat's "don't promote narrative-without-capital":

```
credibility_penalty = (belief_score - confirmation_score - 0.4) clipped to [0, 1]
                    if belief_score > confirmation_score + 0.4 AND age >= 12w
                    else 0
```

A theme that has been firing on belief for 12+ weeks WITHOUT any confirmation gets penalized. The penalty SUBTRACTS from the strength score and pushes the theme toward `FALSE_POSITIVE` classification (see §5).

The 12w threshold is FROZEN — it represents "two earnings seasons should have produced confirmation, and didn't."

### 3.4 Why F&O inclusion is treated as confirmation

NSE F&O eligibility depends on:
- Average market cap (top quartile of all listed)
- Median quarter-on-quarter delivery value
- Cumulative open interest depth
- Order book depth metrics

A name being **added** to F&O is NSE certifying that institutional tradability has crossed a quantitative threshold — this is a market-revealed structural promotion, not a cosmetic label. Names being **dropped** from F&O is the equivalent confirmation of decay.

Theme-level F&O inclusion score = `(F&O_added - F&O_dropped) / theme_member_count` over rolling 12m.

### 3.5 Phase 1 vs Phase 2 — what's buildable now

Phase 1 (data already exists or simple scrape):
- B3 (FII drift), B5 (IPO cluster)
- C1 (RS-breakout), C2 (cap-drift), C3 (F&O inclusion), C5 (earnings breadth), C6 (sector breadth)

Phase 2 (data acquisition + NLP):
- B1 (M&A), B2 (capex)

Phase 3 (future v2):
- B4 (block deals — needs forward-only collection to mature)
- C4 (options skew)

At v1 ship, missing Phase 2 signals emit `null` scores; the aggregator skips them and recalibrates weights of available signals to sum to 1.0 within each bucket.

---

## 4. Theme universe AND link rules (FROZEN at v1)

Themes are NOT free-form. Two-tier hierarchy:

- **Tier 1 (sector):** Banks, IT_Services, Auto, Pharma, Hospitals, Capital-goods, Defence, FMCG, Metals, Realty, Energy, Telecom, Power, NBFC
- **Tier 2 (sub-theme):** declared explicitly in `pipeline/research/theme_detector/themes_frozen.json`

### 4.1 Stock-to-theme link rules (FROZEN at v1)

Per Bharat's caution that this is the biggest hidden source of subjectivity, every theme MUST have an explicit, declared link rule. Three permitted rule kinds:

**Rule kind A — Explicit roster:** an enumerated list of symbols. Used when membership is small and stable (e.g., DEFENCE_WAR_ECONOMY = HAL/BEL/BDL/MAZDOCK/GRSE).

**Rule kind B — Filter rule:** a deterministic predicate over name attributes (sector, sub-sector, market cap, listing year, F&O status). Used when membership is dynamic (e.g., NEW_ECONOMY_LISTINGS_2021_COHORT = `listing_year in [2020, 2021, 2022] AND sector in {Consumer-services, Tech, Logistics} AND was_loss_making_at_listing`).

**Rule kind C — Quantitative score-rank:** ranking by an explicit formula (e.g., AI_TAILWIND_ER_AND_D = `top 10 names by (R&D_capex_ratio + Engineering_services_revenue_share)` re-ranked annually). Used when membership reflects continuous attribute, not categorical.

**Each theme MUST declare exactly ONE rule kind in `themes_frozen.json`.** Rules are immutable post-freeze; new themes get added with version bump (v1.1, v1.2, ...).

### 4.2 Authored Tier-2 themes at v1 freeze (DRAFT — Bharat to confirm before freeze)

| Theme ID | Rule kind | Members / formula |
|---|---|---|
| `BANKS_DIGITAL_TAILWIND` | A | HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, SBIN, INDUSINDBK |
| `BANKS_PSU_REREATING` | A | SBIN, BANKBARODA, PNB, CANBK, UNIONBANK, INDIANB |
| `IT_AI_HEADWIND_MASS` | A | TCS, INFY, WIPRO, HCLTECH, TECHM |
| `IT_AI_TAILWIND_ER_AND_D` | A | PERSISTENT, KPITTECH, COFORGE, TATAELXSI, TATATECH, LTTS, CYIENT |
| `DEFENCE_WAR_ECONOMY` | A | HAL, BEL, BDL, MAZDOCK, GRSE, COCHINSHIP |
| `HOSPITALS_ROBOTICS_LEAN` | A | APOLLOHOSP, FORTIS, MAXHEALTH, NH, RAINBOW, KIMS |
| `DATA_CENTRES_ADJACENT` | A | (membership pending verification — will be authored at freeze) |
| `NEW_ECONOMY_LISTINGS_2020_22_COHORT` | B | `listing_year in [2020, 2021, 2022] AND was_loss_making_at_listing` |
| `POWER_RENEWABLE_TRANSITION` | A | ADANIGREEN, NTPC, TATAPOWER, SUZLON, INOXWIND, JSW_ENERGY |
| `CAPEX_PLI_BENEFICIARY` | A | LT, BHEL, SIEMENS, ABB, ABBOTINDIA, CGPOWER |
| `QUICK_COMMERCE` | A | ZOMATO, DELHIVERY (limited liquidity for now) |
| `EVS_AND_AUTO_TECH` | A | TATAMOTORS, M&M, OLAELECTRIC, SONACOMS, BOSCHLTD |

**Bharat must approve this list before v1 freeze.** Themes are designed to OVERLAP — KPITTECH appears in both `IT_AI_TAILWIND_ER_AND_D` and `EVS_AND_AUTO_TECH`. The detector reports per-theme strength independently for each.

### 4.3 Anti-subjectivity guardrails

- **No theme may be added for a single name.** Themes must have ≥3 members (rule kind A) or have a filter rule that produces ≥3 members at every historical month over backfill.
- **No theme may be added retroactively to fit a known winner.** Theme freeze date is logged; backfill must use themes-as-of-then membership only.
- **Themes are reviewed annually for membership drift.** Member adds/drops require version bump and explicit rationale.

---

## 5. Lifecycle classifier — 5 states (FROZEN at v1)

Every theme gets one stage per weekly run, computed from `(belief_score, confirmation_score, age_in_stage_weeks)`.

| Stage | Belief | Confirmation | Trigger | Age handling |
|---|---|---|---|---|
| **DORMANT** | < 0.2 | < 0.2 | Both signals quiet | Default state |
| **PRE_IGNITION** | ≥ 0.4 | < 0.4 | Belief firing, confirmation hasn't | Reset to 0 on first entry |
| **IGNITION** | optional | ≥ 0.5 (fresh, < 12w in stage) | Confirmation breaks out | Reset to 0 on first entry |
| **MATURE** | optional | ≥ 0.5 (held > 12w in stage) | Confirmation sustained | Increments weekly |
| **DECAY** | optional | < 0.3 AND falling | Confirmation reversing | Reset to 0 on first entry |
| **FALSE_POSITIVE** | ≥ 0.4 | < 0.4 | PRE_IGNITION held > 26w without confirmation | Captures narrative-without-capital |

Transition rules (FROZEN):

```
DORMANT → PRE_IGNITION   when belief_score >= 0.4
PRE_IGNITION → IGNITION  when confirmation_score >= 0.5 (within 26w of PRE_IGNITION entry)
PRE_IGNITION → FALSE_POSITIVE  when 26w in PRE_IGNITION without IGNITION transition
IGNITION → MATURE        when 12w in IGNITION (confirmation sustained)
MATURE → DECAY           when confirmation_score drops < 0.3 AND 4-week trend negative
DECAY → DORMANT          when confirmation_score < 0.2 for 8 consecutive weeks
FALSE_POSITIVE → DORMANT when belief_score < 0.2 for 8 consecutive weeks
                         (themes can re-enter PRE_IGNITION later, fresh)
```

**Why FALSE_POSITIVE matters operationally:** downstream hypotheses MUST NOT enter new positions on FALSE_POSITIVE themes. They are scored, tracked, and visible — but suppressed for entry. This prevents narrative-only themes (capex chatter / press releases / M&A rumors that never close) from generating phantom universes.

**Inversion warnings:** legitimate fast transitions exist (e.g., regulatory event → IGNITION skipping PRE_IGNITION). The detector logs these as `fast_ignition` warnings — not errors, but flagged for review.

---

## 6. Output schema (FROZEN at v1)

Weekly artefact: `pipeline/data/research/theme_detector/themes_<YYYY-MM-DD>.json`

```json
{
  "run_date": "2026-05-03",
  "detector_version": "v1.0",
  "n_themes_total": 32,
  "stage_counts": {
    "DORMANT": 18, "PRE_IGNITION": 7, "IGNITION": 4,
    "MATURE": 2, "DECAY": 1, "FALSE_POSITIVE": 0
  },
  "themes": [
    {
      "theme_id": "DATA_CENTRES_ADJACENT",
      "lifecycle_stage": "IGNITION",
      "lifecycle_stage_age_weeks": 8,
      "first_detected_date": "2025-09-12",
      "first_pre_ignition_date": "2025-09-12",
      "first_ignition_date": "2026-03-08",
      "belief_score": 0.50,
      "confirmation_score": 0.78,
      "credibility_penalty": 0.0,
      "current_strength": 0.78,
      "signal_breakdown": {
        "B3_fii_drift": 0.45, "B5_ipo_cluster": 0.55,
        "C1_rs_breakout": 0.82, "C2_cap_drift": 0.65,
        "C3_fo_inclusion": null, "C5_earnings_breadth": 0.70, "C6_sector_breadth": 0.85
      },
      "members": [
        {"symbol": "ANANTRAJ", "theme_strength_per_name": 0.81,
         "free_float_weight_pct": 0.012, "adv_60d_inr_cr": 95.4,
         "fno_eligible": true},
        {"symbol": "NETLINK", "theme_strength_per_name": 0.74,
         "free_float_weight_pct": 0.008, "adv_60d_inr_cr": 28.7,
         "fno_eligible": false}
      ],
      "warnings": [],
      "downstream_entry_permitted": true
    }
  ]
}
```

`downstream_entry_permitted` is FALSE for `FALSE_POSITIVE` and `DECAY` themes; downstream hypotheses MUST honor this gate.

---

## 7. Cadence + governance

- **Cadence:** Weekly Sunday 23:00 IST (after weekly bhavcopy + after AnkaETFReoptimize at 22:00 IST Sat)
- **Runtime location:** VPS systemd timer (`anka-theme-detector.service`)
- **Output:** writes `themes_<YYYY-MM-DD>.json` + appends to `theme_history.parquet` (long format for diffing)
- **Watchdog inventory entry:** `AnkaThemeDetector`, tier=warn, cadence=weekly
- **Failure mode:** if any signal family errors, detector emits partial output with `warnings` populated; signal weights renormalized within bucket

---

## 8. Validation: lead-time + stability, NOT "did it predict the winners"

Per Bharat's correction: a detector that only flags Zomato-2021 or Defence-2023 AFTER everyone sees them is a lagging taxonomy engine, not useful infrastructure. Validation criteria measure FORWARD utility:

### 8.1 Reference cycles for retro-backfill 2018 → 2024

| Theme | Best-estimate ignition | RS-breakout | Detector PRE_IGNITION should fire by |
|---|---|---|---|
| New-economy 2020-22 listings | 2020-Q4 (capital formation) | 2021-07 (Zomato listing wave) | 2021-Q1 |
| PSU-bank rerating | 2022-H1 | 2023-Q2 | 2022-Q2 |
| Defence | 2022-Q3 (Russia-Ukraine) | 2023-Q3 | 2022-Q4 |
| Power-renewable | 2023-Q1 (PLI batteries) | 2024-Q2 | 2023-Q2 |
| Data-centres adjacency | 2024-Q3 (capex) | 2024-Q4 | 2024-Q4 |
| Hospitals consolidation / robotics | 2024-Q1 (PE rollups) | 2024-Q4 | 2024-Q2 |
| Quick commerce | 2023-Q3 (Blinkit GMV inflection) | 2024-Q1 | 2023-Q4 |
| Capital goods / PLI | 2022-H2 | 2023-Q3 | 2023-Q1 |

### 8.2 Pass criteria (FROZEN before deployment)

Three independent gates, ALL must pass:

**Gate A — Lead time:**
PRE_IGNITION fires ≥4 weeks before RS-breakout in **at least 5 of 8** reference cycles. Median lead time across cycles ≥6 weeks. NOT scored on whether the eventual winner was identified — scored on whether the theme as a whole was flagged early.

**Gate B — Stability:**
Of all themes that entered PRE_IGNITION during backfill, no more than 35% inverted to DORMANT within 12 weeks (excluding legitimate FALSE_POSITIVE classifications). High inversion rate = noisy detector.

**Gate C — False-positive discipline:**
Of all themes that reached PRE_IGNITION, at least 30% transition to either IGNITION (true positive) or stayed in PRE_IGNITION ≥26w then transitioned cleanly to FALSE_POSITIVE (correctly filed). Themes that bounced between states without resolution are scored as detector error.

**Gate D — No structural amputation:**
For the 8 reference cycles, detector must NOT have flagged DECAY in the 12w window before ignition. Catching this with the PRE_IGNITION stage is the whole architectural point.

If the detector fails any gate, v1 is rebuilt before deployment. NOT a single-touch hypothesis — this is infrastructure, retry-permitted with documented amendment.

### 8.3 Forward acceptance gate

Even if retro-backfill passes, the detector ships in **shadow mode** for 4 weeks before any downstream hypothesis can register against it. During shadow:
- Output is produced and stored
- Stage transitions are logged
- Manual review compares detector output to current market commentary
- After 4 weeks, if no glaring failures, detector is promoted to live

---

## 9. Downstream consumption — scope vs weight separation (FROZEN at v1)

Per Bharat: scope and weight are different decisions. The detector exposes both signals; downstream hypothesis declares how to use each.

### 9.1 Scope rules (universe selection)

Downstream hypothesis at registration time selects ONE of:

- **`scope = stages_in {IGNITION, MATURE}`** — only ride confirmed themes
- **`scope = stages_in {PRE_IGNITION, IGNITION, MATURE}`** — accumulate during pre-ignition
- **`scope = stages_in {IGNITION, MATURE, DECAY}`** — explicit short-side / mean-revert universe
- **`scope = custom_predicate(stage, belief, confirmation)`** — explicit formula

`FALSE_POSITIVE` themes are NEVER eligible for entry, regardless of scope rule.

### 9.2 Weight rules (position sizing)

Position weight per name = `theme_strength_per_name × edge_score × win_rate_score × stage_multiplier`, then capped by liquidity.

`stage_multiplier` (FROZEN at v1):
- PRE_IGNITION: 0.3 (exploratory; small size)
- IGNITION: 1.0 (full size)
- MATURE: 0.7 (trim trail)
- DECAY: 0.0 for new entries; 1.0 for mean-revert / short-side hypotheses

Liquidity cap: `max_position_inr = min(position_inr, 0.10 × name_60d_ADV_inr)` — never take more than 10% of average daily turnover. This is a HARD cap, not a sizing input.

### 9.3 Equal-weight is forbidden as a default

Per Bharat: equal-weight is itself an economic claim. A v2 hypothesis that consumes the detector MUST declare its weight rule explicitly at registration. If the analyst really wants equal-weight, they declare `weight_rule = equal` and own the choice.

### 9.4 Lifecycle gate during execution

Downstream hypothesis declares behavior on stage transition during a position's life:

- `pause_new_entries_on_decay` (default TRUE)
- `force_exit_on_false_positive` (default TRUE — if a position's theme transitions to FALSE_POSITIVE during the trade, exit immediately)
- `auto_size_down_on_decay` (default FALSE — let stops handle it)

---

## 10. Phasing (build sequence, revised per feedback)

Bharat's endorsed sequence: **spec first → backfill validation → only then wire into a hypothesis.**

### Phase 1 — buildable now (data exists / simple scrape)

- B3 (FII shareholding drift), B5 (IPO cluster)
- C1 (RS-breakout), C2 (cap-drift), C3 (F&O inclusion), C5 (earnings breadth), C6 (sector breadth)
- Lifecycle classifier with all 5 states
- Output writer + theme_history.parquet
- Retro-backfill harness with all 8 reference cycles
- Theme credibility penalty mechanic

**Estimated effort:** 2-3 sessions

### Phase 2 — buildable after data acquisition

- B1 (M&A flow) — needs IndianAPI extension or BSE/SEBI scraper
- B2 (capex disclosure) — needs LLM extraction layer

**Estimated effort:** 2 sessions for data acquisition + 1 session for signal logic

### Phase 3 — future v2

- B4 (block deals) — forward-only collection maturing 2027+
- C4 (options skew) — IV term-structure + put-call premium

### Phase 4 — only AFTER detector ships in shadow + retro-validation passes

Wire detector into a downstream hypothesis (likely `EARNINGS-DRIFT-LONG-v2`). NEW hypothesis_id, distinct single-touch from v1.

---

## 11. Files at v1 freeze

| Asset | Path |
|---|---|
| Spec (this doc) | `docs/superpowers/specs/2026-05-01-theme-detector-design.md` |
| Data audit | `docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md` |
| Frozen theme universe + link rules | `pipeline/research/theme_detector/themes_frozen.json` |
| Module dir | `pipeline/research/theme_detector/` (NO `*_signal_generator.py` etc) |
| Detector entrypoint | `pipeline/research/theme_detector/detector.py` |
| Belief signals | `pipeline/research/theme_detector/signals/belief/{ma_flow.py, capex.py, fii_drift.py, block_deals.py, ipo_cluster.py}` |
| Confirmation signals | `pipeline/research/theme_detector/signals/confirmation/{rs_breakout.py, cap_drift.py, fo_inclusion.py, earnings_breadth.py, sector_breadth.py, options_skew.py}` |
| Lifecycle classifier | `pipeline/research/theme_detector/lifecycle.py` |
| Credibility penalty | `pipeline/research/theme_detector/credibility.py` |
| Retro-backfill harness | `pipeline/research/theme_detector/retro_backfill.py` |
| Output schema | `pipeline/research/theme_detector/output_schema.json` |
| Tests | `pipeline/research/theme_detector/tests/` |

---

## 12. Doc-sync companions (per CLAUDE.md doc-sync mandate)

When v1 ships:

- `pipeline/config/anka_inventory.json` — add `AnkaThemeDetector` weekly task entry
- `CLAUDE.md` — add to clockwork schedule under Weekly section
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — document detector as a layer above the strategy stack
- `memory/project_theme_detector.md` — project memo
- `memory/MEMORY.md` — index entry

---

## 13. What this UNBLOCKS

Once shipped, the following become possible without needing me to hand-pick anything:

1. **EARNINGS-DRIFT-LONG v2** — universe = current PRE_IGNITION + IGNITION themes (declared scope rule); theme-strength-weighted sizing
2. **Theme-rotation overlay** — long top-3 IGNITION themes / short top-3 DECAY themes
3. **Pre-event positioning** — when a theme is in PRE_IGNITION, scan for upcoming earnings within member names and bias toward LONG drift (with reduced size at stage_multiplier=0.3)
4. **M&A pair (Phase 2)** — when M&A flow flags "old-buys-new" within a sector, pair-trade old-economy buyer vs sector index
5. **IPO follow-up scanner** — names within an IPO-cluster theme, run shadow performance vs cohort
6. **Narrative-detector audit** — FALSE_POSITIVE themes accumulate as a register of "story stocks that never delivered" — useful for retrospective lesson capture

Each is a separately-registered hypothesis with the detector output as a frozen input.

---

## 14. Caveats and known gaps

- **Theme list is hand-authored at v1.** The detector measures THEME STRENGTH but doesn't propose new themes. v2 may attempt unsupervised theme discovery (clustering on RS / cap-drift co-movement); not at v1.
- **Signal families have unequal data availability.** Phase-2 belief signals (M&A, capex) will have NULL scores until acquisition completes; aggregator renormalizes within bucket.
- **Lifecycle stage thresholds are FROZEN at v1.** They will need recalibration after retro-backfill validation; that recalibration is part of v1 design, not a post-deployment amendment.
- **FALSE_POSITIVE detection is asymmetric.** A theme correctly classified as FALSE_POSITIVE that later genuinely re-ignites will look like a detector error in retrospect, but isn't — it just re-enters PRE_IGNITION fresh. Track ID-level transition history, not just current state.
- **Detector is NOT a trading rule.** Downstream hypotheses still must register and pass §9 gates on their own merits.
- **Retro-backfill uses today's theme list AS OF backfill date.** Historical membership must be reconstructed; this is the largest data-quality risk and is documented in the audit doc (TD-D6).

---

## 15. Approval

To be filled at v1 freeze:

- [ ] Bharat reviews and approves §4.2 theme list authored at freeze
- [ ] Bharat approves §3.3 credibility penalty parameters (12w threshold, 0.4 spread)
- [ ] Bharat approves §5 lifecycle transition timing (26w PRE_IGNITION → FALSE_POSITIVE)
- [ ] Bharat approves §8 validation gate criteria (≥5 of 8 cycles, median lead time ≥6w)
- [ ] Data audit doc complete
- [ ] Phase 1 implementation complete
- [ ] Retro-backfill validation passes §8 criteria
- [ ] 4-week shadow run completes without glaring failure
- [ ] Doc-sync companions updated
- [ ] First weekly run lands at 2026-XX-XX (date TBD on freeze)
