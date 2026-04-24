# Correlation-Break Hardening + Narrative Plan (PENDING)

> **Status:** Pending. Write-up only. Do not execute until prioritised.
> **Owner:** Bharat
> **Drafted:** 2026-04-24

## Context — why this plan exists

Three days of live Phase C correlation-break trades have produced strong P&L
(5/5 overnight winners at +3% to +9%, mixed same-day results). At the same
time, every formal backtest of adjacent hypotheses has **FAILED** under
compliance gates:

| Hypothesis | What it tested | Verdict |
|---|---|---|
| H-2026-04-23-002 | Persistent break, EOD classification, T+1..T+5 drift | FAIL |
| H-2026-04-24-003 | Asymmetric threshold Lasso on EOD features | FAIL |

**The gap:** all failed backtests use **daily OHLC bars**. The live strategy
is fundamentally **intraday** — σ>1.5 setups may persist only minutes, the
Z_CROSS exit fires at 15-min scan frequency, and the 14:30 mechanical stop
flattens unresolved trades same-day. Daily bars cannot see this. We have been
invalidating the wrong strategy.

The live strategy also has three execution inconsistencies that make its P&L
hard to trust:

1. **Open-snap look-ahead** (#112) — entry price stamped at 09:16 open, but
   signal doesn't fire until 09:25+. Records an impossible-to-achieve fill.
2. **Path-dependent exits** — Z_CROSS (intraday thesis completion), 14:30
   time-stop (same-day mechanical), or overnight hold (no exit by 14:30)
   are mixed without a clean rule. Overnight winners are a byproduct of the
   time-stop not firing, not a deliberate strategy.
3. **Stale `expected_return`** (#109) — computed overnight, never refreshed
   during the day despite regime/VIX shifts.

These three together mean: we cannot claim the shadow P&L reflects real edge,
and we cannot put any of this on the public website without risking publishing
fiction.

## Goal

Turn correlation breaks from "mysteriously profitable paper strategy" into
"intraday-tested strategy with clean execution rules and a narrative fit to
publish." Three workstreams, each independently shippable.

---

## Workstream A — Intraday backtest (the real test)

**Hypothesis to register:** `H-2026-04-XX-intraday-lag`
> *For the F&O universe, when a stock's open→T price diverges > 1.5σ from
> its regime-conditional peer-cohort expectation, and classifies as LAG,
> entering at the next 15-min scan price and exiting at first subsequent
> scan where σ drops < 1.5 (or 14:30 time-stop) produces a positive Sharpe
> net of 20 bps round-trip costs over 24 months.*

**Dataset:**
- 15-min OHLC bars for the full F&O universe (~215 tickers), 2024-01 → 2026-04
- Source: Kite historical 15-min, or reconstruct from `pipeline/data/intraday_bars/`
  archive if available
- Phase A regime profile frozen at training vintage (no look-ahead on
  `drift_1d_mean` / `drift_5d_std`)
- Regime-timeline from `regime_history.csv` (already daily — use day-open
  regime as today's regime for intraday scans)

**Simulation engine:**
- For each historical trading day, walk the 15-min grid from 09:30 to 14:30
- At each scan, compute `actual_return = (price / today_open - 1) * 100` and
  `z_score` per `reverse_regime_breaks.py:446-451`
- On trigger (σ > 1.5, classification == OPPORTUNITY_LAG):
  - Entry = **next** scan's price (kill look-ahead)
  - Walk forward 15-min steps: exit on first scan where σ drops below 1.5
    OR 14:30 bar, whichever comes first
- Compute per-trade P&L with 20 bps round-trip cost

**Outputs (primary):**
- **Median break duration** (minutes from trigger to Z_CROSS)
- **Same-day Z_CROSS hit rate** (% triggers that resolve before 14:30)
- **Net Sharpe** per regime, per direction, per time-of-day bucket
- **Cost-adjusted edge** vs random-basket null (reuse v2 null-basket framework)

**Gate for promotion:** net Sharpe ≥ 0.5 with p < 0.05 on 100k permutation
null, cost-adjusted, over the full 24-month sample. Below that → park as
exploratory only.

**Deliverable:** `pipeline/autoresearch/intraday_break_compliance/` package
matching the existing `overshoot_compliance/` structure. Runs as a
compliance gate with 12-section artefact.

---

## Workstream B — Execution rule hardening

Fix the three inconsistencies that make live P&L untrustworthy:

### B1. Deterministic entry (#112)
- Kill open-snap entry price
- Entry price = first scan price **after** trigger detection
- Concretely: if the 09:45 scan detects the break, entry is the
  09:45 LTP, not the 09:16 open
- Shadow ledger records `entry_scan_timestamp` alongside `entry_price`

### B2. Deterministic exit ladder
Replace the current mixed exit logic with a clean ladder:
1. Z_CROSS at any intraday scan → close immediately at that scan's LTP
2. 14:30 mechanical time-stop → close at 14:30 LTP
3. **No overnight holds.** If neither Z_CROSS nor 14:30 fires (shouldn't —
   14:30 is unconditional), log an exception.

Today's 5/5 overnight winners were a side-effect of the time-stop not
executing on late-day triggers. That's a bug, not a feature. The strategy
is explicitly **same-day**.

### B3. Refresh `expected_return` intraday (#109)
- Currently stale all day (computed at overnight batch)
- Refresh at every 15-min scan using current-day peer cohort returns
- Keeps the thesis honest if peer behaviour shifts post-open

### B4. Align classify_break timing
- Classification should use the scan-time σ, not the trigger-time σ
- Ensures Z_CROSS fires cleanly when gap truly closes

**Deliverable:** `signal_tracker.py` + `reverse_regime_breaks.py` changes
with TDD coverage; backfill the 2026-04-22..2026-04-24 live trades under
the new rules and compare P&L deltas to what was booked.

---

## Workstream C — Website narrative (trader language)

Once A validates and B is shipped, the strategy can be publicly described.
Source material = the terminal's OPPORTUNITY LAG explanation text. Problems
with the current terminal copy:

- "FOLLOW thesis (aligned with backtest FADE)" — internally contradictory
- "Target: 5-day drift mean of regime-conditional returns" — incomprehensible
- "Stop: 1.5σ against entry" — σ means nothing to readers without a number
- "mild (<2σ — noise floor)" label shown on trades we *took* — confusing

**Rewrite framework (trader voice):**

> *When the market's risk mood shifts, stocks move in cohorts. On days like
> today (CAUTION regime), stocks like DIVISLAB typically fall ~0.9% intraday
> with the rest of their cohort. When DIVISLAB hadn't moved (only -0.12%)
> while its peers had already dropped 0.87%, the gap was 2σ wide — roughly a
> 1-in-22-day dislocation.*
>
> *We short the laggard, betting the gap closes before 2:30 PM. Today it
> did: DIVISLAB fell 0.63% after entry. We exited when the gap closed. No
> overnight risk, no guessing — the cohort leads, the laggard follows, or
> we're out by 2:30.*

**Deliverables:**
- One-page "The Correlation Break Playbook" piece written in the above voice
- Published to `askanka.com/playbooks/correlation-break.html`
- Live daily examples (redacted — no ticker names intraday) appended to the
  article from the 14:30 close log
- Explicit disclosure: sample size, regime coverage, cost assumptions, and
  the specific Sharpe/hit rate numbers from Workstream A
- Never publish before A passes. Never publish based on 3-day live P&L.

---

## Sequencing

| Step | Workstream | Blocks |
|---|---|---|
| 1 | A full build + 24m run | B, C |
| 2 | B1 + B2 + B3 + B4 shipped to live | C |
| 3 | Re-run A against live logs under B's new rules | — |
| 4 | If edge confirmed → C, else park | — |

## Estimated effort

- A: 5-7 days (depends on 15-min bar availability — first task is audit
  `pipeline/data/intraday_bars/` for coverage gaps)
- B: 2 days (clean fix given existing `signal_tracker.py`)
- C: 1 day of writing + publishing

## Non-goals

- Do NOT register this as a new trading strategy file (`*_strategy.py`)
  until both A passes AND B is shipped. The current live run is paper-only.
- Do NOT publish the narrative before A passes.
- Do NOT widen the σ threshold or fiddle with the 0.3 lag test while
  testing — those are the knobs the engine uses today, the backtest must
  match them.

## Acceptance

- [ ] `H-2026-04-XX-intraday-lag` registered in `hypothesis-registry.jsonl`
- [ ] Intraday backtest package shipped with 12-section compliance artefact
- [ ] 24-month run complete; verdict recorded in `terminal_state.json`
- [ ] Workstream B rules live in production + tested
- [ ] Playbook article published OR strategy parked with honest post-mortem

## Related memory

- `memory/project_phase_c_follow_vs_fade_audit.md` — prior audit closure
- `memory/project_overshoot_reversion_backtest.md` — prior (failed) backtest
- `memory/feedback_scientific_validation.md` — every signal must be properly backtested
- `memory/feedback_alpha_vs_timing_luck.md` — winning ≠ edge
- Task #112, #109, #104 — prerequisites/neighbours
