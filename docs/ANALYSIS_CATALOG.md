# Analysis Catalog

> **Purpose:** Single registry of every signal, filter, hypothesis, and tracker we run.
> When you walk into a session, scan this doc first to know which analyses are PUBLISH-grade, which are MONITOR, which are dead.

**Last revised:** 2026-04-29

## How to read this

Each row has a status, last verdict, and code path. Three states matter:
- **PUBLISH** — N ≥ 30 forward CLOSED trades, real evidence
- **MONITOR** — 10 ≤ N < 30 forward CLOSED trades, watching it grow
- **INSUFFICIENT** — N < 10 forward, do not act on
- **DEAD** — failed a holdout, do not resurrect without new evidence
- **PENDING** — pre-registered but no closed trades yet

**Standards:** all numbers must come from **forward** ledgers, never replay/in-sample. The cleanliness gate (`anka_data_validation_policy_global_standard.md`) must be satisfied for every cited dataset.

---

## A. Stock-selection filters (reach 70%+ on small N)

### A.1. NEUTRAL VWAP-deviation filter
- **Status:** PUBLISH (filter cell), forward-tracking
- **Code:** `pipeline/research/vwap_filter.py` + `pipeline/research/neutral_cohort_tracker.py`
- **Hypothesis:** "On a 2σ correlation-break fade, skip entries where price has already extended past VWAP at 09:30 in the trade direction."
- **Sample:** 105 forward CLOSED H-001 NEUTRAL trades (Apr 27/28/29 2026)
- **Cells:**
  - Drop VWAPSIGN_HI: **70 trades, 70.00% wins, +0.472% mean** ← PUBLISH
  - VWAPSIGN_LO alone: **35 trades, 77.14% wins, +0.77% mean** ← PUBLISH
  - VWAPSIGN_HI (avoid): 35 trades, 37.14% wins, -0.27% ← PUBLISH (negative cell)
- **Ledger:** `pipeline/data/research/neutral_cohort/by_cell_<date>.csv`
- **Live wired:** Display-only tag on `pipeline/data/research/h_2026_04_26_001/recommendations.csv` (KEEP/DROP/WATCH). Surfaced on terminal LIVE tab via `live_monitor._enrich_h001_row`.
- **Holdout:** Display-only during H-001 holdout (until 2026-05-26). Promotion to live-gated requires new pre-registered hypothesis post-holdout.
- **Memo:** `memory/project_neutral_cohort_filter_2026_04_29.md`

### A.2. NEUTRAL ORB-15min range filter
- **Status:** PUBLISH (cell)
- **Cells:**
  - ORB_HI (wide range): 35 trades, 68.57% wins ← PUBLISH
  - ORB_MID (medium range): 35 trades, 45.71% wins ← PUBLISH (negative)
  - ORB_LO (tight range): 35 trades, 62.86% wins
- **Combined ORB+VWAP:** VWAPSIGN_LO + ORB_HI: 13 trades, 92% wins ← MONITOR (n<30)

### A.3. NEUTRAL Bollinger position filter
- **Status:** PENDING — backfill in flight 2026-04-29
- **Plan:** Add BB(20,2) z-position at 09:30 to `neutral_cohort_tracker`. Test if "long-fade when price below lower band" creates additional PUBLISH cell.

---

## B. Forward paper hypotheses (single-touch holdouts)

### B.1. H-2026-04-26-001 (sigma-break mechanical, unconditional)
- **Status:** ACTIVE holdout, PENDING verdict
- **Holdout window:** 2026-04-27 → 2026-05-26
- **Sample so far:** 105 CLOSED, 59.05% wins, +0.225% mean
- **Spec:** `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1-design.md`
- **Code:** `pipeline/h_2026_04_26_001_paper.py`
- **Ledger:** `pipeline/data/research/h_2026_04_26_001/recommendations.csv`
- **Verdict criterion:** Sharpe + hit-rate + drawdown thresholds at end of window.

### B.2. H-2026-04-26-002 (regime-gated sister)
- **Status:** ACTIVE holdout, **0 OPEN** (regime has been NEUTRAL since launch; gate closes)
- **Hypothesis:** Read only `regime_gate_pass=True` rows (regime != NEUTRAL).
- **Open trades to date:** 0/105 (all rows are NEUTRAL — gate correctly closed).
- **Verdict:** Cannot be evaluated until regime shifts.

### B.3. H-2026-04-27-003 (SECRSI sector-RS market-neutral pair)
- **Status:** ACTIVE holdout, MONITOR
- **Holdout:** 2026-04-28 → 2026-07-31 (auto-extends if N<40)
- **Spec:** `docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md`
- **Code:** `pipeline/research/h_2026_04_27_secrsi/`
- **Ledger:** `pipeline/data/research/h_2026_04_27_secrsi/recommendations.csv`

### B.4. H-2026-04-29-ta-karpathy-v1 (per-stock TA Lasso, top-10 NIFTY pilot)
- **Status:** ACTIVE holdout, **opened today 2026-04-29**
- **Holdout:** 2026-04-29 → 2026-05-28 (~21 trading days)
- **Honest expectation:** 0–3 of 10 stocks pass qualifier gates
- **Spec:** `docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md`
- **Memo:** `memory/project_h_2026_04_29_ta_karpathy.md`

### B.5. H-2026-04-29-intraday-data-driven-v1 (twin: stocks + indices)
- **Status:** POSTPONED 2026-04-29 (no robust edge — V1 design failed)
- **Action:** V2 redesign per `memory/project_intraday_v2_redesign_direction_2026_04_29.md` — discovery across all 273 F&O. No code yet, awaiting spec finetuning.
- **Holdout clock:** PAUSED, not consumed.

---

## C. Live forensic ledgers (descriptive, no edge claim)

### C.1. Phase C live shadow (futures leg)
- **Path:** `pipeline/data/research/phase_c/live_paper_ledger.json`
- **State:** 11 OPEN, 0 CLOSED. First closes due 2026-04-29 EOD.
- **Verdict cadence:** Bootstrap at N=100.

### C.2. Phase C paired ATM-options sidecar
- **Path:** `pipeline/data/research/phase_c/live_paper_options_ledger.json`
- **State:** 12 rows since 2026-04-22:
  - 0 CLOSED
  - 4 OPEN
  - 7 SKIPPED_LIQUIDITY (wide bid-ask spread)
  - 1 ERROR (fixed)
- **Issue:** ~58% skip rate due to liquidity. Investigate strike-selection in `pipeline/research/intraday_v1/options_paired.py`.

### C.3. Pattern Scanner paired shadow
- **Status:** Pattern fit complete (3,276 cells, 172 qualified), paired shadow blocked on Phase C helpers.
- **Memo:** `memory/project_pattern_scanner.md`

### C.4. ARCBE signals
- **Status:** UNKNOWN — runs at 07:15 IST pre-market, writes to `open_signals.json` (currently missing — needs investigation)
- **Code:** `pipeline/arcbe_signal_generator.py`
- **Action:** Audit forward win rate per task #48.

---

## D. Failed / archived hypotheses

| Hypothesis | Status | Date | Reason |
|---|---|---|---|
| H-2026-04-24-001 (TA-Karpathy RELIANCE) | DEAD | 2026-04-23 | mean_auc 0.509 — null |
| H-2026-04-24-003 (persistent-break v2) | DEAD | 2026-04-24 | margin -4.98, p=0.81 |
| H-2026-04-25-001 (earnings-decoupling) | DEAD | 2026-04-25 | beaten by random_direction, p=0.34 |
| H-2026-04-25-002 (etf-stock-tail) | DEAD | 2026-04-26 | §9A FRAGILE 0/6, §9B margin negative |
| ETF v2 (62.3% claim) | RETIRED | 2026-04-26 | v3-CURATED-30 supersedes (54.6→53.2→52.2% no decay) |
| Phase C OPPORTUNITY_LAG slice (when read live) | KILLED | 2026-04-23 | both slice hypotheses FAIL Bonferroni; live now routes only LAG |
| V1 fixed-batch (intraday data-driven, twin) | POSTPONED | 2026-04-29 | LOO + walk-forward dispersion didn't survive train/test |

---

## E. Engines without forward audit (TODO)

These are running but lack a PUBLISH-grade forward win-rate. Each needs the same recipe (ledger pull → baseline → cell aggregation):

1. **ARCBE** — pre-market signals; no forward ledger surfaced
2. **Spread Intelligence** (30+ pre-configured pairs) — display-only on terminal
3. **TA Fingerprint cards** — 5y historical follow-through is descriptive, not forward edge
4. **TA Pattern Scanner** — 172 qualified cells but z mostly anti-predictive
5. **TA Coincidence Scorer (FCS)** — 2026-04-28 verdict FLAT, display-only
6. **Synthetic Options pricer** — engineering deliverable, not a strategy
7. **OI Scanner / max-pain / pinning** — descriptive, no forward signal validation

---

## F. The standard recipe (use this for every new analysis)

1. **Ledger:** signals open + close in a CSV/JSON with timestamps and P&L
2. **Backfill features:** derive features at signal time, append columns
3. **Cell aggregation:** `pipeline/research/neutral_cohort_tracker.py` template — group by (filter cells), compute N + win% + mean PnL per cell
4. **Threshold:** PUBLISH N≥30, MONITOR 10≤N<30, INSUFFICIENT N<10
5. **Memory note:** write `memory/project_<analysis>_<date>.md` with sample, cells, verdict
6. **Catalog row:** add a row in this file under the right section
7. **Master state JSON:** ensure the analysis is included in `pipeline/data/research/master_evidence.json` (built by the unified runner)

**Never claim a number without going through this recipe.**
