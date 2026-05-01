# Theme Detector v1 — design spec

**Document:** `docs/superpowers/specs/2026-05-01-theme-detector-design.md`
**Status:** DESIGN — not built
**Author:** Bharat Ankaraju + Claude Opus 4.7
**Date:** 2026-05-01
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

> **Markets emit observable signatures of structural change BEFORE financial-performance confirmation. A multi-signal detector running weekly on Indian equity market data can identify these themes, classify their lifecycle stage, and rank constituent names — providing a market-derived universe + theme-strength weighting for downstream hypotheses.**

The detector replaces hand-picked sector universes (e.g., the 40-name Banks+IT in `H-2026-05-01-EARNINGS-DRIFT-LONG-v1`) with empirically-detected theme buckets. It does NOT predict price direction; it identifies which structural change is currently occurring.

---

## 2. Why this exists (motivation)

Hand-picked universes age badly. The 40-name Banks+IT frozen for `EARNINGS-DRIFT-LONG-v1` smuggles one analyst's prior into every backtest. Real structural drivers (AI-headwind to mass IT, digital-bank tailwind to private banks, war-economy capex to defence, robotics-adoption to hospitals, data-centre capital-formation cluster) are NOT inferable from sector labels. They emit market-side signatures — capital flow, M&A, capex disclosure, IPO clustering, RS breakouts — that the detector observes.

Two methodological non-negotiables motivated by Bharat's challenge on 2026-05-01:

1. **Don't structurally amputate.** A naive "drop sectors with declining RS" rule kills hospitals at the exact moment robotics-adoption capex begins. The lifecycle classifier explicitly carries a **PRE_IGNITION** stage so leading indicators are not dismissed.
2. **Don't average across regime shifts.** Pre-COVID / COVID / post-COVID / AI-era are structurally different. The detector reports stage age and inversion warnings; downstream hypotheses can window training data accordingly.

---

## 3. Signal families (FROZEN at v1, phased build)

Five signal families. Each emits a per-theme score on `[0, 1]`. A theme is any sectoral or sub-sectoral grouping (defined in §4). The detector aggregates signals across families to assign a lifecycle stage and total theme strength.

### 3.1 Cap-drift (currently-firing) — Phase 1

- **Source:** NIFTY-500 / NIFTY-50 free-float-adjusted weight history (monthly snapshot)
- **Computation:** rolling 6-month change in free-float weight per stock; aggregated by theme membership
- **Score:** `weight_delta_6m / max_abs(weight_delta_6m across all themes)` — clipped to `[0, 1]` for rising direction
- **Threshold:** top quartile of weight delta = "rising"; bottom quartile = "falling"

### 3.2 Sectoral RS-breakout (ignition) — Phase 1

- **Source:** Sectoral indices (NIFTY-IT, NIFTY-BANK, NIFTY-AUTO, NIFTY-DEFENCE, NIFTY-PHARMA, NIFTY-CPSE, NIFTY-METAL, NIFTY-FMCG, NIFTY-PSU-BANK, NIFTY-REALTY, NIFTY-PRIVATEBANK, sub-indices for capex / ER&D / new-economy if available)
- **Computation:** sector-RS = sectoral_index / NIFTY-50, normalized; 200d high breakout flag + 90d slope
- **Score:** `min(slope_z, 3.0) / 3.0` if currently above 200d high, else 0
- **Threshold:** `score > 0.5` AND breakout fresh within 12w = ignition

### 3.3 IPO-cluster (capital-formation) — Phase 1

- **Source:** NSE main-board listings calendar (must be built — currently absent from pipeline)
- **Computation:** per-sub-sector IPO count rolling 6m; per-sub-sector cumulative subscription multiple
- **Score:** `min(ipo_count_6m / 5, 1.0) * (subscription_multiple_avg > 5 ? 1.0 : 0.5)`
- **Threshold:** 3+ IPOs in 6m within a coherent sub-sector = capital-formation theme firing
- **Examples this would have flagged:** New-economy 2021 cohort (Zomato → Nykaa → Paytm → CarTrade → Delhivery), Hospital chains 2021-22, Defence small-caps 2024, Data-centre adjacency 2024-25

### 3.4 M&A flow (smart-capital signal) — Phase 2 (data acquisition required)

- **Source:** NSE corporate announcements (M_AND_A / SCHEME_OF_ARRANGEMENT / OPEN_OFFER), BSE filings, IndianAPI corp_actions extension
- **Computation:** per-theme deal count + deal-value rolling 12m, categorized into:
  - **Old-buys-new** (acquirer GICS != target GICS, target is younger/recently-listed)
  - **New-buys-old** (acquirer is recently-listed or new-economy; target is established)
  - **Intra-sector consolidation** (same GICS, deal-value > theme median)
  - **Cross-border** (Indian acquirer of foreign tech / IP)
- **Score:** weighted sum, normalized to `[0, 1]`
- **Examples this would flag:** RIL → e-commerce assets (old-buys-new), Zomato → Blinkit (new-buys-old), Hospitals 2024 PE rollups (consolidation), Tata → IP rolling (cross-border)

### 3.5 Capex disclosure (forward-leaning) — Phase 2 (NLP layer required)

- **Source:** NSE/BSE corporate disclosures for new-project, capacity-expansion, fund-raise-for-capex
- **Computation:** per-sector disclosure count rolling 6m; cumulative announced INR
- **Extraction:** NLP / regex on disclosure text; LLM tagging in v1 if available, regex fallback
- **Score:** `min(disclosure_count_6m / 10, 1.0) * (cumulative_capex_log_score)`
- **Examples this would flag:** Hospital chains' robotics capex, manufacturing PLI-driven capex, data-centre green-field capex

---

## 4. Theme universe (FROZEN at v1)

Themes are NOT free-form — they are pre-declared sub-sector groupings. Two-tier hierarchy:

- **Tier 1 (sector):** Banks, IT_Services, Auto, Pharma, Hospitals, Capital-goods, Defence, FMCG, Metals, Realty, Energy, Telecom, Power, NBFC
- **Tier 2 (sub-theme):** declared explicitly in `pipeline/research/theme_detector/themes_frozen.json`. Examples:
  - `BANKS_DIGITAL_TAILWIND` = {HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, SBIN, INDUSINDBK}
  - `IT_AI_HEADWIND_MASS` = {TCS, INFY, WIPRO, HCLTECH, TECHM}
  - `IT_AI_TAILWIND_ER_AND_D` = {PERSISTENT, KPITTECH, COFORGE, TATAELXSI, TATATECH, LTTS, CYIENT}
  - `DEFENCE_WAR_ECONOMY` = {HAL, BEL, BDL, MAZDOCK, GRSE}
  - `HOSPITALS_ROBOTICS_LEAN` = {APOLLOHOSP, FORTIS, MAXHEALTH, NH, RAINBOW}
  - `DATA_CENTRES_ADJACENT` = {ANANTRAJ, NETLINK, NXTDIGITAL, RAILTEL} (verify membership at v1 freeze)
  - `NEW_ECONOMY_LISTINGS_2021_COHORT` = {ZOMATO, NYKAA, PAYTM, DELHIVERY, CARTRADE}
  - `POWER_RENEWABLE_TRANSITION` = {ADANIGREEN, NTPC, TATAPOWER, SUZLON, INOXWIND}
  - `CAPEX_PLI_BENEFICIARY` = {LT, BHEL, SIEMENS, ABB, ABBOTINDIA}

The Tier-2 list is authored at v1 freeze, frozen as `themes_frozen.json`, immutable thereafter. New themes added in v2 with version bump.

**Note:** Themes are designed to OVERLAP. A name like KPITTECH may be in `IT_AI_TAILWIND_ER_AND_D` and in `AUTO_TECH_ENABLERS`. The detector reports per-theme strength independently.

---

## 5. Lifecycle classifier (FROZEN at v1)

Every theme is assigned one of 5 lifecycle stages each weekly run:

| Stage | Cap-drift | RS-breakout | IPO/M&A/Capex | Trigger logic |
|---|---|---|---|---|
| **DORMANT** | 0 | 0 | 0 | All signals < 0.2 |
| **PRE_IGNITION** | 0 | 0 | ≥1 firing | Leading-indicator firing, RS not yet broken |
| **IGNITION** | rising | breakout fresh <12w | optional | RS-breakout score > 0.5 AND fresh |
| **MATURE** | rising/stable | held >12w | optional | Cap-drift sustained, RS held above 200d |
| **DECAY** | falling | breakdown | optional | Cap-drift score < 0 AND RS below 200d |

**Stage age** is tracked (in weeks) and exposed in output. **Inversions** (e.g., IGNITION → DECAY in <12w) trigger a manual-review flag — these are usually data-error or theme-redefinition issues, not real reversals.

The PRE_IGNITION → IGNITION transition is the **alpha-relevant signal**. Names in PRE_IGNITION are NOT yet in everyone's universe; the IGNITION transition is when they become consensus. Downstream hypotheses can either (a) accumulate during PRE_IGNITION at small size, or (b) wait for IGNITION confirmation.

---

## 6. Output schema (FROZEN at v1)

Weekly artefact: `pipeline/data/research/theme_detector/themes_<YYYY-MM-DD>.json`

```json
{
  "run_date": "2026-05-03",
  "detector_version": "v1.0",
  "n_themes_total": 32,
  "n_dormant": 18,
  "n_pre_ignition": 7,
  "n_ignition": 4,
  "n_mature": 2,
  "n_decay": 1,
  "themes": [
    {
      "theme_id": "DATA_CENTRES_ADJACENT",
      "lifecycle_stage": "IGNITION",
      "lifecycle_stage_age_weeks": 8,
      "first_detected_date": "2025-09-12",
      "current_strength": 0.78,
      "signal_breakdown": {
        "cap_drift_score": 0.65,
        "rs_breakout_score": 0.82,
        "ipo_cluster_score": 0.50,
        "ma_flow_score": null,
        "capex_score": null
      },
      "members": [
        {"symbol": "ANANTRAJ", "theme_strength_per_name": 0.81, "free_float_weight_pct": 0.012, "adv_60d_inr_cr": 95.4},
        {"symbol": "NETLINK", "theme_strength_per_name": 0.74, "free_float_weight_pct": 0.008, "adv_60d_inr_cr": 28.7}
      ],
      "warnings": []
    }
  ]
}
```

Per-name `theme_strength_per_name` is the position-weight input for downstream hypotheses (capped by liquidity).

---

## 7. Cadence + governance

- **Cadence:** Weekly Sunday 23:00 IST (after weekly bhavcopy + after AnkaETFReoptimize at 22:00 IST Sat)
- **Runtime location:** VPS systemd timer (`anka-theme-detector.service`)
- **Output:** writes `themes_<YYYY-MM-DD>.json` + appends to `theme_history.parquet` (long format for diffing)
- **Watchdog inventory entry:** `AnkaThemeDetector`, tier=warn, cadence=weekly
- **Failure mode:** if any signal family errors, detector emits partial output with `warnings` populated; does NOT silently fall back

---

## 8. Validation: retroactive backfill 2018 → 2024

Before v1 ships, the detector must pass a **retro-skill test**: would it have flagged known structural cycles BEFORE consensus / RS confirmation?

### Known reference cycles (theme_id, ignition date approximation, RS-breakout date approximation, financial-confirmation date)

| Theme | Ignition (best estimate) | RS-breakout | Financial confirmation | Detector PRE_IGNITION should fire by |
|---|---|---|---|---|
| New-economy 2021 listings | 2020-Q4 (capital-formation) | 2021-07 (Zomato listing) | 2024+ (profitability) | 2021-Q1 |
| PSU-bank rerating | 2022-H1 (PSU-credit-cycle) | 2023-Q2 | 2024-Q1 | 2022-Q2 |
| Defence | 2022-Q3 (Russia-Ukraine) | 2023-Q3 | 2024+ | 2022-Q4 |
| Power-renewable | 2023-Q1 (PLI batteries) | 2024-Q2 | 2025+ | 2023-Q2 |
| Data-centres adjacency | 2024-Q3 (capex announcements) | 2024-Q4 | 2025+ | 2024-Q4 |
| Hospitals consolidation | 2024-Q1 (PE rollup) | 2024-Q4 | 2025+ | 2024-Q2 |

### Pass criteria

- **Lead time:** detector flags PRE_IGNITION ≥4 weeks before RS-breakout in **at least 4 of 6** reference cycles
- **False-positive rate:** of all PRE_IGNITION flags fired in backfill, ≥40% transition to IGNITION within 26w (the rest are acceptable noise — pre-ignition signal is not a guarantee)
- **No structural amputation:** for the 6 reference cycles, detector must NOT have flagged DECAY in the 12w window before ignition

If the detector fails any of these, v1 is rebuilt before deployment. NOT a single-touch hypothesis — this is infrastructure, retry-permitted with documented amendment.

---

## 9. What downstream hypotheses get from this

A hypothesis registered after the detector ships (e.g., v2 of EARNINGS-DRIFT) would:

1. **Universe** = all names in themes with `lifecycle_stage in {PRE_IGNITION, IGNITION, MATURE}` AND `current_strength > 0.4`, snapshotted at registration time
2. **Position weights** = `theme_strength_per_name` × liquidity-cap × hypothesis-specific signal strength (Kelly-style multi-factor)
3. **Auto-recalibration** = at v2 spec freeze, the universe is FROZEN. The detector's subsequent output is informational; the hypothesis does NOT silently follow theme changes mid-flight (would violate §10.4 strict)
4. **Lifecycle gate** = if a theme's stage shifts to DECAY mid-flight, hypothesis can choose to pause new entries on that theme (declared at registration)

The detector is the SOURCE of universe selection, not the operator of trades.

---

## 10. Phasing (build sequence)

### Phase 1 — buildable now (data exists)

- Cap-drift signal (NIFTY-500 weight history — needs scraping from NSE)
- RS-breakout signal (sectoral indices — already in fno_historical or available via Kite)
- IPO-cluster signal (NSE main-board listings calendar — needs scraping)
- Lifecycle classifier
- Output writer
- Retro-backfill harness

**Estimated effort:** 2 sessions

### Phase 2 — buildable after data acquisition

- M&A flow (needs NSE corporate-actions extension to include M_AND_A / SCHEME_OF_ARRANGEMENT)
- Capex disclosure (needs NLP / regex extraction from corporate filings)

**Estimated effort:** 2 sessions for data acquisition + 1 session for signal logic

### Phase 3 — future enhancements (v2)

- Options skew signal (puts vs calls premium)
- FII shareholding trend (quarterly disclosures)
- Block-deal pattern detection
- Cross-border deal tracker

---

## 11. Files at v1 freeze

| Asset | Path |
|---|---|
| Spec (this doc) | `docs/superpowers/specs/2026-05-01-theme-detector-design.md` |
| Data audit | `docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md` |
| Frozen theme universe | `pipeline/research/theme_detector/themes_frozen.json` |
| Module dir | `pipeline/research/theme_detector/` (NO `*_signal_generator.py` etc — kill-switch-clean naming) |
| Detector entrypoint | `pipeline/research/theme_detector/detector.py` |
| Signal families | `pipeline/research/theme_detector/signals/{cap_drift.py, rs_breakout.py, ipo_cluster.py, ma_flow.py, capex.py}` |
| Lifecycle classifier | `pipeline/research/theme_detector/lifecycle.py` |
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

1. **EARNINGS-DRIFT-LONG v2** — universe = current PRE_IGNITION + IGNITION themes; theme-strength-weighted sizing
2. **Theme-rotation overlay** — long top-3 IGNITION themes / short top-3 DECAY themes (a Markowitz-on-themes portfolio)
3. **Pre-event positioning** — when a theme is in PRE_IGNITION, scan for upcoming earnings within member names and bias toward LONG drift
4. **Cross-theme M&A pair** — when M&A flow flags "old-buys-new" within a sector, pair-trade old-economy buyer vs sector index
5. **IPO follow-up scanner** — names within an IPO-cluster theme, run shadow performance vs cohort

Each is a separately-registered hypothesis with the detector output as a frozen input.

---

## 14. Caveats and known gaps

- **Theme list is hand-authored at v1.** The detector measures THEME STRENGTH but doesn't propose new themes. v2 may attempt unsupervised theme discovery (clustering on RS / cap-drift co-movement); not at v1.
- **Signal families have unequal data availability.** Phase-2 signals (M&A, capex) will have NULL scores until data acquisition completes; output schema accommodates this.
- **Lifecycle stage thresholds are FROZEN at v1.** They will need recalibration after the retro-backfill validation; that recalibration is part of v1 design, not a post-deployment amendment.
- **Detector is NOT a trading rule.** Downstream hypotheses still must register and pass §9 gates on their own merits.
- **Retro-backfill uses today's theme list.** Names that were once in `DATA_CENTRES_ADJACENT` may have changed (renamed, delisted, or sub-sector reclassified). Retro-backfill must use historically-correct membership; this is a known data-quality issue documented in the audit doc.

---

## 15. Approval

To be filled at v1 freeze:

- [ ] Bharat reviews and approves design
- [ ] Data audit doc complete
- [ ] Phase 1 implementation complete
- [ ] Retro-backfill validation passes §8 criteria
- [ ] Doc-sync companions updated
- [ ] First weekly run lands at 2026-05-XX (date TBD on freeze)
