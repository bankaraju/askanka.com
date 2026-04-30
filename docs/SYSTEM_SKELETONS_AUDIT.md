# System Skeletons Audit — 2026-04-30

> **Purpose:** No system component should run without an FAQ entry or detailed doc. Every "skeleton in the cupboard" — undocumented system, un-backtested trade, stale code path, ambiguous status — surfaced here. Per user directive 2026-04-30: *"each time I ask something skeletons are coming out of the cupboard — let's fix all of them."*
>
> **Scope:** This is a static audit. Each row links to source files for verification. As skeletons are resolved, they get checked off and moved to FAQ / detailed doc.
>
> **Author:** Bharat Ankaraju + Claude (audit run 2026-04-30 evening IST)

---

## A. Inventory snapshot

| Category | Count |
|---|---|
| Scheduled tasks (`pipeline/config/anka_inventory.json`) | 129 |
|   – critical | 49 |
|   – warn | 27 |
|   – info | 53 |
| Hypothesis registry entries | 30 |
| Active paper-trade ledgers | 4 (h_2026_04_26_001 · SECRSI · track_record · phase_c) |
| F&O historical CSVs | 276 (5.0 years, 2021-04-23 → 2026-04-22) |
| Sector panel | 22 sectors × 1235 days |

---

## B. Skeletons identified — summary table

| # | Skeleton | Severity | Existing doc? | Action |
|---|---|---|---|---|
| 1 | 13 INDIA_SPREAD_PAIRS — all firing live on news triggers, **0 backtests** | **CRITICAL** | None per-basket | Task #24 — full 5y regime-conditioned backtest |
| 2 | `AnkaUnifiedBacktest` was 3y not 5y | HIGH | docstring only | **PATCHED today** — line 97 `1095 → 1825` |
| 3 | `AnkaUnifiedBacktest` covers only 6 of 13 baskets | HIGH | docstring only | Replace with Task #24 outputs |
| 4 | `AnkaUnifiedBacktest` reports Sharpe 13.72 → no friction modelled | HIGH | None | Replace; absorb into Task #24 with cost discipline |
| 5 | News pipeline has no provenance trail (URL/hash/published_at) | **CRITICAL** | None | Task #23 spec doc + impl |
| 6 | Two ETF reopt scripts: scheduler runs **legacy V2**; V3 CURATED has no scheduled task | HIGH | partial | §F — needs explicit user nod to re-point |
| 7 | Sector × regime behavior table — missing brain layer | MEDIUM | None | Task #25 spec |
| 8 | Banks × NBFC PDR — discovery passed today, not yet registered | MEDIUM | findings only | Task #26 spec |
| 9 | Expiry-week IV + pinning behavior — no data collection running | MEDIUM | None | Task #31 |
| 10 | Phase C OVERSHOOT slice — disqualified 2026-04-23 but still in code | LOW | direction audit doc | Code cleanup pass |
| 11 | Options paired sidecar covers only Phase C / Pattern Scanner / V1 | MEDIUM | partial | **Frozen** until post-backtest |
| 12 | ~~Hypothesis-registry entries with missing `status` field~~ — **false alarm**, registry uses `terminal_state` / `record_type` per record type | — | None | resolved 2026-04-30 |
| 13 | `INDIA_SPREAD_PAIRS_DEPRECATED` kill-switch logic — silently retires baskets even if they're paying | HIGH | feedback memory | Carve-out: never silent-retire a paying paper book |

---

## C. The 13 INDIA_SPREAD_PAIRS — full disclosure

Every basket below is currently **live in paper trading**, fires on news-keyword triggers (not data-primary), holds overnight, has **NO formal backtest, NO hypothesis-registry entry, NO single-touch holdout**. Per user directive, the news-trigger architecture is being replaced with data-primary + news-as-confirmation-only.

| # | Name | Long | Short | News triggers |
|---|---|---|---|---|
| 1 | Upstream vs Downstream | ONGC + OIL | IOC + BPCL | oil_up, escalation, hormuz, sanctions, trump_threat |
| 2 | Defence vs IT | HAL + BEL + BDL | TCS + INFY + WIPRO | escalation, defense_spend, sanctions, trump_threat, hormuz, oil_positive |
| 3 | Reliance vs OMCs | RELIANCE | BPCL + IOC | oil_up, refining_margin, escalation |
| 4 | Coal vs OMCs | COALINDIA | BPCL + IOC | energy_crisis, oil_up, escalation, hormuz, oil_positive |
| 5 | Pharma vs Cyclicals | SUNPHARMA + DRREDDY | TMPV + M&M | escalation, de_escalation, diplomacy |
| **6** | **PSU Commodity vs Banks** ("Commodity-Credit Divergence" in dashboard) | **ONGC + COALINDIA** | **HDFCBANK + ICICIBANK** | escalation, sanctions, hormuz |
| 7 | Defence vs Auto | HAL + BEL | TMPV + MARUTI | escalation, defense_spend, trump_threat |
| 8 | PSU Energy vs Private | ONGC + COALINDIA + OIL | RELIANCE + ADANIENT | oil_up, escalation, hormuz |
| 9 | Pharma vs Banks | SUNPHARMA + DRREDDY | HDFCBANK + ICICIBANK | rbi_policy, de_escalation, diplomacy |
| 10 | Banks vs IT | HDFCBANK + ICICIBANK | TCS + INFY + WIPRO | rbi_policy, de_escalation, diplomacy |
| 11 | PSU NBFC vs Private Banks | HUDCO + NHPC | HDFCBANK + ICICIBANK | rbi_policy, nbfc_reform |
| 12 | EV Plays vs ICE Auto | TMPV + M&M | MARUTI | ev_policy |
| 13 | Infra Capex Beneficiaries | ULTRACEMCO + AMBUJACEM | ADANIENT | infra_capex, tax_reform |

**Source:** `pipeline/config.py:119-202`. Constant name suffix `_DEPRECATED` — kill-switch tied to `H-2026-04-29-intraday-data-driven-v1` passing its holdout (verdict 2026-07-04).

**Action — locked 2026-04-30:** none of these 13 baskets is to be silently retired even when the kill-switch fires. They must be either re-architected as data-primary + news-confirmation hypotheses (Task #23 / #24) OR explicitly archived with a memorial note. Basket #6 is the highest-stakes since it's the most-consistent earner.

---

## D. Hypothesis registry — full status board

| Hypothesis ID | Status (declared) | Spec doc | Holdout window | Notes |
|---|---|---|---|---|
| H-2026-04-23-001 | PRE_REGISTERED | yes | n/a | Phase C direction audit predecessor |
| H-2026-04-23-002 | PRE_REGISTERED | yes | n/a | follow vs fade audit |
| H-2026-04-23-003 | PRE_REGISTERED | yes | n/a | overshoot reversion |
| H-2026-04-24-001 | PRE_REGISTERED → FAIL (mean_auc 0.509) | yes | consumed | TA scorer v1 — failed; rework path |
| H-2026-04-24-002 | ABANDONED_PRE_EXECUTION | yes | — | abandoned before run |
| H-2026-04-24-003 | FAIL | yes | consumed | Persistent-break v2 cross-sectional |
| H-2026-04-25-001 | FAIL | yes | consumed | Earnings decoupling — n=26, p=0.34 |
| H-2026-04-25-002 | FAIL | yes | consumed | ETF stock tail classifier — §9A FRAGILE |
| H-2026-04-26-001 | RUNNING (holdout) | yes | 2026-04-27 → 2026-05-26 | Sigma break unconditional, 145 ledger rows |
| H-2026-04-26-002 | RUNNING (holdout) | yes | 2026-04-27 → 2026-05-26 | Sigma break regime-gated |
| H-2026-04-26-ETF-V3 | RUNNING (forward shadow) | yes | 30 trading days from 2026-04-27 | V3 CURATED-30 production pilot |
| H-2026-04-27-001 | PRE_REGISTERED | yes | n/a | Phase C kill criteria (D9) |
| H-2026-04-27-002 | PRE_REGISTERED | yes | n/a | RISK-ON inverted SHORT |
| H-2026-04-27-003 | RUNNING (holdout) | yes | 2026-04-28 → 2026-07-31 | SECRSI, 16 ledger rows |
| H-2026-04-29-ta-karpathy-v1 | RUNNING (holdout) | yes | 2026-04-29 → 2026-05-28 | TA Karpathy top-10 NIFTY pilot |
| H-2026-04-29-intraday-data-driven-v1-stocks | PAUSED | yes | TBD | Intraday V1 stocks, postponed |
| H-2026-04-29-intraday-data-driven-v1-indices | PAUSED | yes | TBD | Intraday V1 indices, postponed |

**Skeletons here:**
- Some entries have no `status` field in registry JSONL — registry hygiene cleanup needed
- Two entries appear duplicated (PRE_REGISTERED + RUNNING shadow) — by design (one per status transition) but should be visually consolidated in any reader

---

## E. Active paper-trade ledgers

| Ledger | Path | Rows | Hypothesis | Holdout end |
|---|---|---|---|---|
| Sigma break (H-001/002) | `pipeline/data/research/h_2026_04_26_001/recommendations.csv` | 145 | H-2026-04-26-001 / 002 | 2026-05-26 |
| SECRSI | `pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv` | 16 | H-2026-04-27-003 | 2026-07-31 |
| Phase C live shadow | `pipeline/data/research/phase_c/live_paper_ledger.json` | 11 | discovery (no holdout) | open-ended |
| Phase C options paired | `pipeline/data/research/phase_c/live_paper_options_ledger.json` | 12 | forensic-only | open-ended |
| Track Record (official) | `pipeline/data/research/track_record/recommendations.csv` | 42 | aggregate | n/a |

---

## F. The two ETF reopt scripts — which is canonical?

**`pipeline/scripts/etf_reoptimize.bat`** (V2)
- Calls `pipeline.autoresearch.etf_reoptimize`
- Uses raw level features (VIX, NIFTY close, FII, DII) joined to %returns — known broken architecture per 2026-04-26 audit
- **Status:** legacy, broken, NOT canonical

**`pipeline/scripts/etf_v3_curated_reoptimize.bat`** (V3 CURATED-30)
- Calls `pipeline.autoresearch.etf_v3_curated_reoptimize`
- Cycle-3 verdict 2026-04-26: only configuration with positive pooled edge under honest rolling walk-forward (53.55% acc, +1.83pp edge over majority baseline, P>base 78.7%)
- **Status: canonical** — this is what should be running Saturday 22:00 IST

**Skeleton (verified 2026-04-30 evening IST):**
- The Windows scheduler has exactly one ETF reopt task: `AnkaETFReoptimize`. Its "Task To Run" is `C:\Users\Claude_Anka\askanka.com\pipeline\scripts\etf_reoptimize.bat` — i.e. the **legacy V2** path that the 2026-04-26 audit declared broken.
- `etf_v3_curated_reoptimize.bat` references a separate task name `AnkaETFv3CuratedReoptimize` in its header comments, but **no such scheduled task exists**. The canonical V3 CURATED reopt is therefore not on any clockwork — it has only been run manually.
- **Action (decision required from user before flip):** either (a) re-point `AnkaETFReoptimize` at `etf_v3_curated_reoptimize.bat` and retire the V2 module, or (b) create a new `AnkaETFv3CuratedReoptimize` task and disable `AnkaETFReoptimize`. Recommendation: option (a) — single task name, single canonical implementation. Auto-mode does not flip scheduler entries without confirmation.

In the meantime: V2 reopt continues running every Saturday 22:00 IST and writes to legacy paths; downstream consumers already read from the V3 CURATED outputs, so the V2 weekend job is **dead-writing** — no harm, no value.

---

## G. Documentation status — per system component

| Component | Architecture doc | FAQ entry | Spec / hypothesis | Skeleton? |
|---|---|---|---|---|
| Regime engine V3 CURATED-30 | partial (in `etf_v3_curated_signal.py` docstring) | NO | yes | gap: no standalone arch doc |
| Phase A regime playbook | yes | NO | yes | gap: no FAQ |
| Phase B daily ranker | partial | NO | yes | gap: how it gates trades |
| Phase C correlation breaks | yes (multiple) | partial | yes | OK |
| SECRSI | yes | NO | yes (H-2026-04-27-003) | gap: no FAQ |
| H-2026-04-26-001/002 sigma break | yes | NO | yes | gap: no FAQ |
| Pattern Scanner | partial | NO | yes (H-2026-04-27-pattern-scanner) | gap: no FAQ |
| TA Karpathy | yes | NO | yes (H-2026-04-29-ta-karpathy-v1) | gap: no FAQ |
| Trust Score (OPUS ANKA) | yes | partial | n/a | gap: how it gates conviction |
| News pipeline | NONE | NO | NO | **CRITICAL skeleton** |
| INDIA_SPREAD_PAIRS (13 baskets) | NONE per-basket | NO per-basket | NO per-basket | **CRITICAL skeleton** |
| Watchdog | yes | partial | n/a | OK |
| Track Record | yes | NO | n/a | gap |
| Mechanical Replay (60-day) | yes | NO | n/a | gap |
| Sector panel (canonical) | yes (today) | NO | n/a | new — needs FAQ |
| Sector correlation study | yes (today) | NO | n/a | new — needs FAQ |
| Sector pair divergence (PDR) | yes (today) | NO | n/a | new — needs FAQ |
| Options paired shadow | yes (Phase C only) | NO | n/a | gap: SECRSI/sigma-break/spread sidecars not wired |
| Expiry-week IV / pinning | NONE | NONE | NONE | new skeleton |

---

## H. The "we are making money on what news?" anti-pattern

The phrase the user used to describe trading on un-audited news triggers. To prevent recurrence:

1. Every promoted trading rule must declare a `data_primary_trigger` (a quantitative signal) AND optionally a `news_confirmation` field. The data signal alone fires the trade. (Per `feedback_news_is_reassurance_not_trigger.md`.)
2. Mandatory news provenance (URL + sha256 + published_at + fetched_at + source) for any news citation in any trade row.
3. Anti-stale guard — headline `published_at` more than 24h before trade open does NOT count as confirmation.
4. Anti-contradiction guard — data says LONG, news classifier flags opposing-direction event → trade BLOCKED, not opened.
5. Retroactive auditability — at any post-mortem, persisted URL must still resolve and headline body hash must still match. Anything that doesn't survive verification gets flagged "EVIDENCE_VANISHED" and excluded from backtest aggregation.

These five rules are the architectural fix. Implementation: Task #23 spec + code.

---

## I. Action plan locked at this audit

| # | Item | Owner | Status |
|---|---|---|---|
| Patch unified_backtest 3y → 5y | code | done — committing this run |
| Spec for Task #24 (5y backtest of 13 baskets, cost-deducted) | spec doc | drafting now |
| Spec for Task #23 (news provenance protocol) | spec doc | drafting now |
| Spec for Task #25 (sector × regime behavior table) | spec doc | drafting now |
| FAQ document — start populating with Q&As discovered in this conversation | docs/SYSTEM_FAQ.md | drafting now |
| Verify `AnkaETFReoptimize` scheduler task points to V3 CURATED .bat | manual | **verified 2026-04-30: points at LEGACY V2; no V3 task exists.** Awaiting user nod to re-point — see §F |
| Hypothesis registry hygiene — fix entries with missing status | data fix | **verified 2026-04-30: false alarm.** 28/30 use `terminal_state` or `record_type` (canonical for those record types); 2 use `status`. Schema-consistent. No fix needed. |
| Phase C OVERSHOOT slice code cleanup | code | **scoped 2026-04-30:** OVERSHOOT references in 15 files (4 live code: `phase_c_shadow.py`, `website_exporter.py`, `telegram_bot.py`, terminal JS; rest are frozen historical CSVs). Live routing already uses LAG only per #107 audit. Cleanup deferred to dedicated session — not safe to sweep mid-holdout. |

Schedule for runs of these items: **NEXT WEEKEND**, after specs are reviewed and cost-discipline parameters are locked. We are NOT auto-running anything new this week — every backtest must have a registered spec first.

---

## J. Going-forward rule (lock in policy)

> **Every system component must have:**
> 1. An entry in `pipeline/config/anka_inventory.json` (if scheduled)
> 2. A spec or design doc under `docs/`
> 3. An FAQ entry in `docs/SYSTEM_FAQ.md`
> 4. A clear declaration of `data_primary_trigger` (if it generates trades) and provenance fields (if it consumes news)
>
> **Adding a new component without all four is a documentation skeleton.** This audit will be re-run weekly until the table in §G has zero "gap" or "skeleton" rows.

---

_Last audit: 2026-04-30. Next scheduled re-audit: 2026-05-04 (Sunday)._
