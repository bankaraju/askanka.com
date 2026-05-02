# askanka.com FAQ Index

Curated map of system topics → canonical source documents. Every Hermes FAQ
answer must read at least one source from this index. If a question's topic
is not in this index, Hermes refuses to answer and asks for an INDEX update.

Maintenance: every commit that adds a new spec, hypothesis, or research doc
must update this INDEX in the same commit (per `feedback_doc_sync_mandate.md`).

Validation: `pipeline/scripts/hermes/index_link_check.py` confirms every
source path resolves; runs as part of the Sun 04:00 IST sync.

---

## Tier 1 — ML Methods (Karpathy, Lasso, BH-FDR, Deflated Sharpe, etc.)

### Karpathy random search
- One-line: Cell-level pooled random search over a hyperparameter grid; pick
  the cell whose walk-forward CV Sharpe survives BH-FDR multiple-testing
  correction. Used in per-stock TA Lasso (H-2026-04-29-ta-karpathy-v1) and
  the Phase-C MR (H-2026-05-01-phase-c-mr-karpathy-v1, which FAILED
  registration when 0/448 cells passed).
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
  - docs/superpowers/specs/backtesting-specs.txt

### Lasso L1 regularization
- One-line: L1-penalized logistic regression; sparsity-inducing, picks ~5–10
  features out of ~60 daily TA features per stock. Used per-stock in
  H-2026-04-29-ta-karpathy-v1 and pooled across instruments in
  H-2026-04-29-data-driven-intraday-framework.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md

### BH-FDR multiple-testing correction
- One-line: Benjamini-Hochberg false-discovery-rate adjustment of per-cell
  p-values; required gate before any cell is accepted as a registered
  hypothesis. The killer of H-2026-05-01-phase-c-mr-karpathy-v1 (0/448 cells
  passed; best in-sample Sharpe 3.44 had p=0.30 with n=70 too thin).
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md

### Deflated Sharpe
- One-line: Sharpe ratio adjusted for the multiple-trials selection bias
  inherent in random-search hyperparameter optimization. Report-only at
  v1, gate-blocking at v2 when n≥100 days (per H-2026-04-29-ta-karpathy-v1
  spec v1.1).
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - docs/superpowers/specs/backtesting-specs.txt

### Walk-forward cross-validation
- One-line: Time-respecting CV — train on past, test on future, slide
  window forward; never train on data later than test. Anti-leakage core.
  H-2026-04-29-ta-karpathy-v1 uses 4-fold walk-forward.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md

### Permutation null
- One-line: Shuffle-the-labels resampling to build the null distribution
  of "no edge"; p-value = fraction of nulls beating the model's metric.
  Composed with BH-FDR to control family-wise FDR across cells in the
  Karpathy qualifier-gate stack.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md

---

## Tier 2 — Architecture

### 8-layer Golden Goose pipeline
- One-line: ETF regime → Trust Scores → Spread Intelligence → Reverse Regime
  → Technicals+OI → Conviction → Shadow PnL → Track Record. ETF regime is
  the upstream brain — stale here breaks all downstream.
- Sources:
  - CLAUDE.md
  - docs/SYSTEM_OPERATIONS_MANUAL.md

### ETF regime engine (v3-CURATED-30)
- One-line: 28 global ETFs, ML-optimized weights, 5 regimes (RISK-ON,
  CAUTION, NEUTRAL, RISK-OFF, CRISIS). v3+CURATED-30 won the 2026-04-26
  cycle-3 evaluation with +1.83pp edge over baseline; v2-faithful is dead.
- Sources:
  - docs/SYSTEM_OPERATIONS_MANUAL.md
  - CLAUDE.md

### OPUS ANKA Trust Scores
- One-line: Management-credibility grades (A+ through F) for the 213 F&O
  universe. 207/210 scored as of 2026-04-11 Haiku fallback run; 3
  data-constrained.
- Sources:
  - docs/SYSTEM_OPERATIONS_MANUAL.md
  - CLAUDE.md
  - opus/CLAUDE.md

### Spread Intelligence Engine
- One-line: 5-layer regime-gated pair-trade decision engine — sector rotation,
  scorecard alpha modifier, technicals confirmation, news adjustment,
  Karpathy per-spread sizing.
- Sources:
  - docs/SYSTEM_OPERATIONS_MANUAL.md
  - CLAUDE.md

### Reverse Regime Phase A/B/C
- One-line: A = playbook of regime-transition patterns; B = daily regime-
  conditional ranker; C = intraday correlation-break detection (LAG /
  OVERSHOOT routing per 2026-04-23 audit, only LAG goes live after kill).
- Sources:
  - CLAUDE.md
  - docs/research/phase-c-validation/01-executive-summary.md
  - docs/research/phase-c-validation/07-verdict.md

### Theme Detector v1
- One-line: Weekly Trendlyne snapshot → 12-theme lifecycle frames (B3 drift
  trajectory at 13w, FALSE_POSITIVE detection at 26w). Laptop-only;
  shadow-mode operational, NOT yet citable as evidence per data-policy §21.
- Sources:
  - docs/superpowers/specs/2026-05-01-theme-detector-design.md
  - docs/superpowers/plans/2026-05-01-theme-detector-elevation-plan.md

---

## Tier 3 — Operations

### 80+ scheduled tasks (clockwork)
- One-line: Windows Task Scheduler (laptop) + VPS systemd timers (Contabo)
  fire ~80 daily/weekly/intraday tasks. Canonical inventory in
  `pipeline/config/anka_inventory.json`; CLAUDE.md "Clockwork Schedule"
  is the human-readable map.
- Sources:
  - CLAUDE.md
  - pipeline/config/anka_inventory.json
  - docs/SYSTEM_OPERATIONS_MANUAL.md

### Data-freshness watchdog
- One-line: Reads anka_inventory.json + checks output-file mtimes against
  per-task grace_multiplier; alerts via Telegram on stale critical tasks.
- Sources:
  - pipeline/watchdog.py
  - CLAUDE.md

### 14:30 IST new-signal cutoff
- One-line: No live engine OPENs new positions after 14:30 IST. Mechanical
  TIME_STOPs run at 14:30 — anything opened later has under 60 min before
  forced close. Enforced at source in run_signals.py +
  break_signal_generator.py + arcbe_signal_generator.py.
- Sources:
  - CLAUDE.md
  - pipeline/run_signals.py
  - pipeline/break_signal_generator.py

### Kill-switch (strategy-pattern gate)
- One-line: Pre-commit hook + CI workflow refuse to merge a new
  `*_strategy.py`/`*_signal_generator.py`/`*_backtest.py`/etc. unless the
  same commit registers it in hypothesis-registry.jsonl. Patterns canonical
  at `pipeline/scripts/hooks/strategy_patterns.txt`.
- Sources:
  - CLAUDE.md
  - pipeline/scripts/hooks/strategy_patterns.txt

### anka_inventory.json
- One-line: Source-of-truth registry of every Anka* scheduled task with
  tier, cadence_class, expected outputs, grace_multiplier. Watchdog reads
  this; missing entry → ORPHAN_TASK alert.
- Sources:
  - CLAUDE.md
  - pipeline/config/anka_inventory.json

### VPS execution foundation
- One-line: Contabo VPS (anka@185.182.8.107) runs all heavy/sensitive
  scheduled tasks via systemd; laptop holds context (Obsidian, memory,
  PDFs). Hardened 2026-04-25 (root disabled, ufw, fail2ban, IST tz).
- Sources:
  - CLAUDE.md
  - docs/SYSTEM_OPERATIONS_MANUAL.md

---

## Tier 4 — Active hypotheses

### H-2026-04-25-002 (etf-stock-tail-classifier)
- Status: FAILED 2026-04-26 on §9A FRAGILE (0/6) + §9B.1 margin -0.0090 +
  §11B. Single-touch consumed; A1.1–A1.5 amendments in force.
- Sources:
  - docs/superpowers/specs/2026-04-25-etf-coefficient-stock-tail-classifier-design.md
  - docs/superpowers/hypothesis-registry.jsonl

### H-2026-04-29-ta-karpathy-v1 (per-stock TA Lasso, top-10 NIFTY)
- One-line: Per-stock Lasso L1 logistic regression on ~60 daily TA features,
  4-fold walk-forward + BH-FDR permutation null + qualifier gate. Frozen
  universe: RELIANCE/HDFCBANK/ICICIBANK/INFY/TCS/BHARTIARTL/KOTAKBANK/LT/
  AXISBANK/SBIN. Holdout 2026-04-29 → 2026-05-28. v1.1 Deflated Sharpe
  report-only at v1, gate-blocking at v2 when N≥100 days. Honest expectation:
  0–3 stocks qualify. Predecessor H-2026-04-24-001 FAILED on RELIANCE.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - CLAUDE.md

### H-2026-04-29-intraday-data-driven-v1 (twin: stocks + indices)
- One-line: Pooled-weight Karpathy random search over 6 intraday features
  on NIFTY-50 stocks AND options-liquid index futures. Holdout 2026-04-29
  → 2026-06-27, verdict by 2026-07-04. PASS criteria: §9 (hit-rate p<0.05,
  Sharpe ≥ 0.5, MaxDD ≤ 5%) AND §9A Fragility ≥ 8/12 AND §9B Margin ≥ 0.5pp.
  On PASS → kills news-driven framework. On FAIL → news-driven incumbent
  stays.
- Sources:
  - docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md
  - docs/superpowers/plans/2026-04-29-intraday-v1-framework.md
  - CLAUDE.md

### H-2026-04-27-003 SECRSI (sector RS intraday pair)
- One-line: Trend-continuation, regime-agnostic, market-neutral. 11:00 IST
  sector snapshot ranks ~25 sectors by median per-stock %chg-from-open;
  LONG top-2 stocks of top-2 sectors + SHORT bottom-2 stocks of bottom-2
  sectors (8 legs equal-weight). Single-touch holdout 2026-04-28 → 2026-07-31.
  Full 5y 5m replay 2026-05-01 STRONG NEGATIVE PRIOR (mean +0.68 bps vs
  ≥+30 needed; hit 50.3% vs ≥55%; Sharpe 0.26 vs ≥1.0). Holdout untouched
  per §10.4.
- Sources:
  - docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md
  - CLAUDE.md

### H-2026-05-01-EARNINGS-DRIFT-LONG-v1
- One-line: PRE_REGISTERED 2026-05-01. Quad-filter LONG (vol_z, short_mom,
  realized_vol, regime). Frozen universe: 19 Banks + 21 IT (40 names).
  Single-touch holdout 2026-05-04 → 2026-08-01, auto-extend until n≥20 OR
  2026-10-31. Tasks pending registration.
- Sources:
  - docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
  - docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md
  - CLAUDE.md

### H-2026-05-01-phase-c-mr-karpathy-v1
- Status: REGISTRATION_FAIL 2026-05-01 — 0/448 cells passed BH-FDR (best
  in-sample Sharpe 3.44 with p=0.30, n=70 too thin). Predecessor LAG-routed
  Phase C stays live. Re-attempt requires fresh hypothesis-registry row +
  longer training window (n≫70) per backtesting-specs.txt §10.4 strict.
- Sources:
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
  - CLAUDE.md

---

## Tier 5 — Standards

### backtesting-specs.txt
- One-line: 16-section governance spec for every backtest and strategy
  launch. §0 (no waivers), §6 (statistical rigor), §9 (pass criteria),
  §9A (fragility), §9B (margin), §10.4 (no parameter retries on same
  registration).
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt

### anka_data_validation_policy_global_standard.md
- One-line: 26-section data-governance policy. Every dataset must be
  registered (§6), have schema contract (§8), pass cleanliness gates (§9),
  declare adjustment mode (§10), be PIT-correct (§11), have contamination
  map (§14). §21 binds dataset acceptance to model approval ladder.
- Sources:
  - docs/superpowers/specs/anka_data_validation_policy_global_standard.md
  - CLAUDE.md

### Doc-sync mandate
- One-line: Every code change updates ALL of: code, SYSTEM_OPERATIONS_MANUAL,
  anka_inventory.json (if scheduled), CLAUDE.md (if architecture), memory.
  Same commit, no exceptions.
- Sources:
  - CLAUDE.md

### No-hallucination mandate
- One-line: Absolute rule — slow and correct beats fast and wrong. Zero
  fabricated numbers; failed lookups print "—", never a guessed value.
- Sources:
  - CLAUDE.md

### Single-touch holdout (§10.4 strict)
- One-line: Once a holdout window opens, no parameter changes, no re-runs
  on the same registration. Failure → fresh hypothesis-registry row, longer
  training window, new holdout.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt

### Subscriber language (plain English)
- One-line: No jargon, no internal numbering. "n=10" → "worked 7 of 10".
  Every public-facing string must be intelligible to a non-quant subscriber.
- Sources:
  - CLAUDE.md
