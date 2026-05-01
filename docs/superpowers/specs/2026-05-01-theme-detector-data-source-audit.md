# Theme Detector v1 — data source audit

**Document:** `docs/superpowers/specs/2026-05-01-theme-detector-data-source-audit.md`
**Companion to:** `docs/superpowers/specs/2026-05-01-theme-detector-design.md`
**Policy ref:** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md`
**Date:** 2026-05-01
**Status:** DESIGN — not yet operational

This document discharges §6 (registration), §8 (schema contract), §9 (cleanliness gates), §10 (adjustment mode), §11 (PIT correctness), §14 (contamination map) of the data validation policy for each input the theme detector consumes.

---

## Inputs to register

The detector composes signals from 9 distinct data sources, organized by Belief / Confirmation buckets per the design doc §3. Each is registered separately below. NULL entries for Phase 2/3 sources are placeholders pending data acquisition.

| ID | Source | Bucket | Feeds signal(s) | Phase | Status |
|---|---|---|---|---|---|
| TD-D1 | NIFTY-500 / NIFTY-50 free-float weight history | Confirmation | C2 (cap-drift) | 1 | DATA ACQUISITION REQUIRED |
| TD-D2 | Sectoral indices daily history | Confirmation | C1 (RS-breakout), C6 (sector breadth) | 1 | EXISTING — Kite + fno_historical |
| TD-D3 | NSE main-board IPO calendar | Belief | B5 (IPO cluster) | 1 | TRENDLYNE PRO GLOBAL — manual UI export from IPO Center |
| TD-D4 | M&A corporate announcements | Belief | B1 (M&A flow) | 2 | DATA ACQUISITION REQUIRED |
| TD-D5 | Capex disclosure announcements | Belief | B2 (capex disclosure) | 2 | NLP LAYER REQUIRED |
| TD-D6 (auxiliary) | NIFTY-500 constituent membership history | Confirmation | C2/C6 retro-backfill correctness | 1 | DATA ACQUISITION REQUIRED |
| TD-D7 | Quarterly shareholding pattern filings (FII column) | Belief | B3 (FII drift) | 1 | TRENDLYNE PRO GLOBAL — manual UI export, see §TD-D7 below |
| TD-D8 | NSE F&O eligibility list history (additions/drops) | Confirmation | C3 (F&O inclusion) | 1 | OPERATIONAL — pipeline/data/fno_universe_history.json (27 monthly snapshots since 2024-01) |
| TD-D9 | Quarterly EPS surprise data (consensus vs actual) | Confirmation | C5 (earnings breadth) | 1 | TRENDLYNE PRO GLOBAL — manual UI export (PIT correctness pending verification) |
| TD-D10 | NSE block deals (forward-only from 2026-04-24) | Belief | B4 (block deal accumulation) | 3 | FORWARD-ONLY (matures 2027) |
| TD-D11 | Options skew / IV term structure | Confirmation | C4 (options skew) | 3 | FUTURE v2 |

---

## TD-D1: NIFTY-500 / NIFTY-50 free-float weight history (Phase 1)

### §6 Registration

- **Source primary:** NSE Indices ([https://www.niftyindices.com/](https://www.niftyindices.com/)) — monthly index constituent files
- **Source backup:** Bloomberg / Refinitiv terminal export (manual, not yet wired)
- **Coverage required:** 2018-01-01 → present, monthly granularity (or as fine as NSE publishes)
- **Acquisition method:** scrape NSE Indices monthly publication PDFs / CSVs; parse free-float weight column

### §8 Schema contract

```
nifty_500_weights/<YYYY-MM>.parquet
  - month_end_date: date
  - index_id: str   ("NIFTY_500", "NIFTY_50")
  - symbol: str
  - free_float_weight_pct: float
  - free_float_market_cap_inr_cr: float
  - rank_in_index: int
```

### §9 Cleanliness gates

- Sum of `free_float_weight_pct` per (month, index) MUST equal 100.0 ± 0.5
- All `symbol` values MUST be in canonical_fno_research_v3 OR be currently-listed NSE main-board names
- `free_float_market_cap_inr_cr` MUST be > 0
- No duplicate (month, index, symbol) tuples

### §10 Adjustment mode

- Cap and weight are POINT-IN-TIME — corporate actions (splits, bonuses) are reflected by NSE in the published file. No retroactive adjustment.
- Renames: NSE retains old symbol until effective date; theme detector applies symbol-alias mapping (per `reference_pit_ticker_list.md`) when joining to fno_historical bars.

### §11 PIT correctness

- Detector RUN at week W consumes only weight files dated ≤ W − 7 days (1-week buffer to ensure NSE has published)
- Retro-backfill at historical date H consumes weight files dated ≤ H − 7 days

### §14 Contamination map

- **Recency bias:** NSE publishes weights with a 5-7 day lag after month end. Always assume 7-day buffer.
- **Survivorship:** When a name is dropped from NIFTY-500 (delisted / merged), it disappears from subsequent weight files. Retro-backfill MUST keep historical membership in tact (use TD-D6).
- **Free-float methodology change:** NSE has revised free-float methodology twice (2019, 2023). Detector should record `methodology_version` per snapshot.

---

## TD-D2: Sectoral indices daily history (Phase 1)

### §6 Registration

- **Source primary:** Kite Connect API (via existing `KiteClient`) — `historical_data` for index instruments
- **Source backup:** NSE bhavcopy + index files in `pipeline/data/fno_historical/`
- **Coverage required:** 2018-01-01 → present, daily OHLC
- **Indices in scope (frozen at v1):** NIFTY-50, NIFTY-IT, NIFTY-BANK, NIFTY-PRIVATEBANK, NIFTY-PSUBANK, NIFTY-AUTO, NIFTY-PHARMA, NIFTY-FMCG, NIFTY-METAL, NIFTY-REALTY, NIFTY-ENERGY, NIFTY-CPSE, NIFTY-DEFENCE, NIFTY-CONSUMPTION, NIFTY-INFRA

### §8 Schema contract

```
sectoral_indices/<INDEX_ID>.csv
  - Date: date
  - Open, High, Low, Close: float
  - Volume: int  (often 0 for indices, ignored)
```

### §9 Cleanliness gates

- All trading days 2018+ MUST have non-null OHLC
- Close > 0 for all rows
- High >= max(Open, Close), Low <= min(Open, Close)

### §10 Adjustment mode

- Indices are not adjusted for corporate actions on constituents (NSE handles internally)
- Detector treats Close as the canonical level

### §11 PIT correctness

- T-day Close is observable from NSE close time (15:30 IST). Detector consumes T-day Close at T+1 weekly run.
- No look-ahead because RS is computed at run date with `close <= run_date - 1d`.

### §14 Contamination map

- **Constituent reweighting:** When NSE reweights an index (every 6 months), the index level shifts mechanically. RS-vs-NIFTY-50 absorbs the shift in both numerator and denominator, but new-listing inclusion can introduce step-changes. The detector flags any RS jump > 5% in a single day for review.
- **Holiday / partial-day handling:** Diwali muhurat trading and similar partial sessions produce anomalous closes. Detector excludes muhurat sessions from RS computation.

---

## TD-D3: NSE main-board IPO calendar (Phase 1)

### §6 Registration

- **Source primary:** NSE / BSE IPO calendars (public web scrape)
- **Source backup:** SEBI public RHP / DRHP disclosures
- **Coverage required:** 2018-01-01 → present, per-IPO record
- **Acquisition method:** weekly scrape; backfill for historical via NSE archives

### §8 Schema contract

```
ipo_calendar.parquet
  - issue_open_date: date
  - issue_close_date: date
  - listing_date: date
  - symbol: str  (post-listing)
  - company_name: str
  - issue_size_inr_cr: float
  - subscription_multiple_overall: float
  - subscription_multiple_qib: float
  - subscription_multiple_hni: float
  - subscription_multiple_retail: float
  - listing_gain_pct: float  (Day-1 close vs issue price)
  - sub_sector_classification: str  (mapped via SectorMapper extension)
  - is_main_board: bool
```

### §9 Cleanliness gates

- listing_date >= issue_close_date
- subscription_multiple_overall > 0 for all listed IPOs
- Total subscription value (size × oversub) > 0

### §10 Adjustment mode

- Issue price and subscription multiples are static at listing — no adjustment
- Sub-sector classification may evolve; detector records `classification_version` per IPO

### §11 PIT correctness

- Detector consumes IPO records where `listing_date <= run_date - 7d` (1-week buffer for late listings to settle classification)

### §14 Contamination map

- **Sub-sector mis-classification:** A "new-economy" IPO might be classified by NSE as "Services" or "Technology" generically — too coarse for theme detection. Detector applies its own `sub_sector_classification` via SectorMapper extension; classification version is logged.
- **Pre-IPO grey-market premium:** GMP is a forward-looking indicator but is a private-market signal not reliably published. NOT used by detector at v1.

---

## TD-D4: M&A corporate announcements (Phase 2)

**STATUS: DATA ACQUISITION REQUIRED. DETECTOR PHASE 2.**

### §6 Registration (target)

- **Source primary:** IndianAPI corporate_actions extension to include `M_AND_A`, `SCHEME_OF_ARRANGEMENT`, `OPEN_OFFER` event kinds
- **Source backup:** SEBI public Open Offer database, BSE corporate filings
- **Coverage required:** 2018-01-01 → present
- **Acquisition method:** TBD — IndianAPI provider does not currently emit M&A events; may require BSE / SEBI scraping

### §8 Schema contract (target)

```
ma_events/<YYYY-MM>.parquet
  - announcement_date: date
  - effective_date: date
  - acquirer_symbol: str (or null if private/foreign)
  - acquirer_name: str
  - target_symbol: str (or null if private)
  - target_name: str
  - deal_kind: str  (ACQUISITION | SCHEME_OF_ARRANGEMENT | OPEN_OFFER | DEMERGER | DELIST)
  - deal_value_inr_cr: float
  - structure: str  (CASH | STOCK | MIXED | TENDER_OFFER)
  - acquirer_sector: str
  - target_sector: str
  - cross_sector_flag: bool
  - cross_border_flag: bool
```

### §11 PIT correctness (target)

- Detector consumes events where `announcement_date <= run_date - 1d` (next-day delay for filing settle)
- `effective_date` is forward-looking; only used for trend-completion analytics

### §14 Contamination map (target)

- **Confidential transactions:** Private-to-private M&A may not be publicly disclosed. Coverage will be incomplete by design.
- **Withdrawn offers:** Some open offers are withdrawn pre-effective. Detector flags `withdrawn` status and excludes from "executed deal flow" but retains in "announced deal flow" for sentiment.

---

## TD-D5: Capex disclosure announcements (Phase 2)

**STATUS: NLP LAYER REQUIRED. DETECTOR PHASE 2.**

### §6 Registration (target)

- **Source primary:** NSE/BSE corporate disclosures (text body) — already scraped in `pipeline/data/disclosures/` (verify)
- **Extraction:** LLM-based classification at v1 (Gemma 4 pilot or Gemini), regex fallback
- **Coverage required:** 2018-01-01 → present (subject to disclosure-archive availability)

### §8 Schema contract (target)

```
capex_disclosures/<YYYY-MM>.parquet
  - filing_date: date
  - symbol: str
  - disclosure_kind: str  (NEW_PROJECT | CAPACITY_EXPANSION | FUND_RAISE_FOR_CAPEX | M_AND_A_FOR_CAPACITY)
  - capex_announced_inr_cr: float (extracted from text)
  - capex_horizon_months: int (extracted)
  - sub_sector: str
  - extraction_method: str  (LLM_v1 | REGEX_v1)
  - extraction_confidence: float (0-1)
  - source_disclosure_id: str
```

### §11 PIT correctness (target)

- Detector consumes records where `filing_date <= run_date - 1d`
- LLM extraction is reproducible: cache extraction outputs by `(disclosure_id, extraction_version)` to allow re-runs

### §14 Contamination map (target)

- **Vague disclosures:** Many filings announce capex without specific INR amount. Detector records `capex_announced_inr_cr = null` for these and weights `disclosure_count` accordingly.
- **Reannouncements:** Companies often reannounce phased capex. Detector deduplicates by `(symbol, capex_program_id_extracted)`; this requires LLM-aware grouping.
- **LLM hallucination:** Extraction confidence < 0.6 → record flagged; not used in scoring at confidence thresholds.

---

## TD-D6: NIFTY-500 constituent membership history (auxiliary, Phase 1)

### §6 Registration

- **Source primary:** NSE Indices semi-annual rebalance announcements
- **Coverage required:** 2018-01-01 → present (every constituent change)
- **Acquisition method:** parse NSE rebalance circulars + monthly weight files (TD-D1) for changes

### §8 Schema contract

```
nifty_500_membership_history.parquet
  - effective_date: date
  - symbol: str
  - action: str  (ADDED | DROPPED | RECLASSIFIED)
  - rebalance_id: str  (e.g., "NIFTY_500_2024_H1")
```

### §11 PIT correctness

- Detector retro-backfill at historical date H uses membership snapshot effective ≤ H

### §14 Contamination map

- **Survivorship bias:** Without membership history, retro-backfill would miss names that were once IN NIFTY-500 but later dropped (e.g., delisted / merged). This is the single largest contamination risk for retro-backfill validation; TD-D6 exists specifically to prevent it.

---

## TD-D7: NSE quarterly shareholding pattern (FII column) (Phase 1)

### §6 Registration

- **Source primary:** NSE Corporate Filings — quarterly shareholding pattern (Reg 31, SEBI LODR) filed within 21 days of quarter end
- **Source backup:** BSE Corporate Filings, IndianAPI shareholding endpoint (verify column availability)
- **Coverage required:** 2018-Q1 → present, quarterly granularity, all NSE main-board names
- **Acquisition method:** scrape NSE corporate filings; parse `Foreign Portfolio Investors (FPI/FII)` row from holding-pattern PDF/XBRL

### §8 Schema contract

```
fii_shareholding/<YYYY-Q>.parquet
  - quarter_end_date: date  (Mar 31 / Jun 30 / Sep 30 / Dec 31)
  - filing_date: date
  - symbol: str
  - fii_holding_pct: float  (0-100)
  - fii_holding_value_inr_cr: float
  - public_shareholding_pct: float  (denominator sanity check)
  - filing_id: str
```

### §9 Cleanliness gates

- `fii_holding_pct` in `[0, 100]`
- `filing_date >= quarter_end_date` (NSE allows 21-day window)
- No duplicate `(quarter_end_date, symbol)` after taking latest filing per quarter
- `public_shareholding_pct + promoter_pct + others_pct == 100 ± 1.0` (cross-row check, separate from this table)

### §10 Adjustment mode

- Holding percentages are POINT-IN-TIME at quarter end. No retroactive adjustment.
- Symbol renames: apply alias mapping per `reference_pit_ticker_list.md` when joining to other tables.

### §11 PIT correctness

- Detector RUN at week W consumes shareholding records where `filing_date <= W − 1d`
- Critical: a Q3 (Sep 30) shareholding may not be filed until Oct 21 — detector must NOT treat Sep-30 as observable on Oct 1.

### §14 Contamination map

- **Reclassification:** SEBI revised FPI categorization in 2019 and 2022. The "FII" definition expanded — apparent FII increases in those quarters are partly methodology, not flow. Detector logs `methodology_version` per quarter and dampens cross-methodology comparisons.
- **Mid-quarter flow not captured:** A name receiving heavy FII inflow in October will not show in Q2 (Sep 30) snapshot — only at Q3 (Dec 31). Lag is structural; B3 is a slow signal by design.
- **Round-trip / parking:** Some FPI holding changes reflect derivative-market parking or cross-listing arrangements rather than directional conviction. Detector cannot distinguish without flow-level data; this is a known precision limit.

---

## TD-D8: NSE F&O eligibility list history (Phase 1)

### §6 Registration

- **Source primary:** NSE Circulars — F&O additions / deletions ("Inclusion of stocks in F&O segment", "Exit of stocks from F&O segment")
- **Source backup:** NSE F&O instruments file historical archives
- **Coverage required:** 2018-01-01 → present, every addition / deletion event
- **Acquisition method:** parse NSE circulars chronologically; cross-validate against existing `canonical_fno_research_v3.json` for current state

### §8 Schema contract

```
fno_eligibility_history.parquet
  - event_date: date  (effective date of inclusion/exclusion)
  - circular_date: date  (date of NSE circular)
  - symbol: str
  - action: str  (ADDED | DROPPED)
  - eligibility_review_date: date  (date NSE evaluated metrics)
  - reason: str  (default "ROUTINE_REVIEW"; some adds/drops have specific reason text)
```

### §9 Cleanliness gates

- `event_date >= circular_date`
- Unique `(symbol, event_date, action)`
- Net additions over coverage window must reconcile with current canonical_fno_research_v3 universe size

### §10 Adjustment mode

- Eligibility events are discrete, no adjustment needed
- Symbol renames: apply alias mapping; if a name was renamed, eligibility carries through at the symbol level (e.g., GMRINFRA → GMRAIRPORT keeps F&O eligibility)

### §11 PIT correctness

- Detector RUN at week W consumes events where `event_date <= W − 1d`
- A name added effective Mar 1 is NOT observable on Feb 28 — the circular itself may be earlier, but eligibility is per `event_date`

### §14 Contamination map

- **Eligibility ≠ liquidity:** A name passing NSE's quantitative threshold doesn't guarantee good fill; detector treats inclusion as the structural signal, NOT a tradability claim. Liquidity cap (60d ADV) is enforced separately at the position-sizing layer.
- **Periodic review windows:** NSE reviews F&O eligibility semi-annually. Bursts of additions/drops cluster around review windows (Mar / Sep). Detector smooths this with rolling 12m window, not raw monthly counts.
- **Voluntary exits:** Some companies request F&O exit (e.g., for buyback). These are treated identically to NSE-initiated drops at v1 — refinement is a v2 candidate.

---

## TD-D9: Quarterly EPS surprise data (Phase 1)

### §6 Registration

- **Source primary:** IndianAPI corporate_actions (quarterly results) + Screener.in consensus history
- **Source backup:** Refinitiv / Bloomberg consensus (manual, not yet wired)
- **Coverage required:** 2018-Q1 → present, all NSE main-board names with active consensus coverage
- **Acquisition method:** EXISTING data path via `pipeline/data/research/h_2026_05_01_earnings_drift/event_factors.csv` (Banks+IT seed); needs widening to all sectors

### §8 Schema contract

```
earnings_surprise/<YYYY-Q>.parquet
  - quarter_end_date: date
  - announcement_date: date
  - symbol: str
  - actual_eps: float
  - consensus_eps: float  (nullable if no consensus coverage)
  - n_consensus_estimates: int
  - eps_surprise_pct: float  ((actual - consensus) / abs(consensus))
  - revenue_actual_inr_cr: float
  - revenue_consensus_inr_cr: float
  - revenue_surprise_pct: float
```

### §9 Cleanliness gates

- `announcement_date >= quarter_end_date`
- `n_consensus_estimates >= 3` for surprise computation; else `eps_surprise_pct = null`
- Detector ignores names with `consensus_eps = null`

### §10 Adjustment mode

- EPS reported per company's own accounting standard (Ind-AS); no normalization at v1
- One-off items (impairments, exceptional gains): NOT separated at v1; this introduces noise in surprise computation that the detector accepts as a known limit

### §11 PIT correctness

- Detector RUN at week W consumes records where `announcement_date <= W − 1d`
- Consensus must be the SNAPSHOT as of `announcement_date - 1d`, NOT the post-announcement consensus (which is contaminated by the print itself)

### §14 Contamination map

- **Selective consensus coverage:** Mid-cap and small-cap names often have 0-3 analyst estimates; surprise signal degrades. Detector requires `n_consensus_estimates >= 3`; rest scored as `null`.
- **Restatements:** If a company restates Q3 EPS in Q4, the original surprise should NOT be retroactively adjusted (PIT correctness). Use first-print actual.
- **Whisper numbers:** Buy-side whisper consensus diverges from sell-side published consensus. Detector uses ONLY published sell-side consensus at v1.

---

## Cross-source consistency checks

The detector's combined output must satisfy these invariants:

1. Every name in any theme's member list MUST exist in `canonical_fno_research_v3.json` OR be a recently-listed name with explicit `is_recent_listing: true` tag.
2. `theme_strength_per_name` for any name MUST be in `[0, 1]`. Excursions outside this range indicate a normalization bug.
3. The lifecycle stage transitions per theme MUST be monotonic in stage ordering OVER A 12W WINDOW (excepting documented inversions). DORMANT → IGNITION without passing through PRE_IGNITION is a legitimate fast-ignition (e.g., regulatory event), but flagged.
4. Sum of `theme_strength_per_name × free_float_weight_pct` across all themes a name appears in MUST be ≤ name's total `free_float_weight_pct` × 1.5 (allowing some overlap, but not unbounded).

---

## Acceptance gate (per data validation policy §21)

The theme detector v1 cannot be cited as evidence for ANY downstream hypothesis until:

- TD-D1, TD-D2, TD-D3, TD-D6, TD-D7, TD-D8, TD-D9 are operational and pass cleanliness gates (Phase 1 sources)
- TD-D4, TD-D5 are operational OR the detector emits `null` scores for B1/B2 with explicit `data_unavailable` flag (Phase 2)
- TD-D10, TD-D11 are explicitly tagged Phase 3 — detector emits `null` for B4/C4 at v1; not a blocker
- Retro-backfill validation per design doc §8 passes all four gates (A lead-time, B stability, C false-positive discipline, D no-amputation)
- The detector itself is registered (this audit doc + design doc both committed)
- A first weekly run completes successfully + 4-week shadow window per design doc §8.3

If a downstream hypothesis (e.g., EARNINGS-DRIFT-LONG v2) attempts to register before this gate passes, the registration is a violation of policy §21 and must be rejected.

---

## Doc-sync companions

When this audit is satisfied:

- `pipeline/config/anka_inventory.json` — add data-collection task entries for TD-D1, TD-D3, TD-D6, TD-D7, TD-D8 (TD-D9 already partially covered by existing earnings ingest)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — document data sources under "Theme Detector Data Layer" subsection
- `memory/reference_theme_detector_data_sources.md` — quick-reference for future sessions
