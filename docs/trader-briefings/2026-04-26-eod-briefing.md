# Trader's Briefing — 2026-04-26 EOD (pre-market 2026-04-27)

> **Purpose:** This is the one document a trader reads at 09:00 IST tomorrow to know:
> what we're trading, why, what's still being validated, and what would change the plan.
> Written in plain trader's language. No model jargon.

---

## Bottom line

**We are NOT putting real capital to work tomorrow.** We are starting a 30-day forward
paper-trade of the rule below, with full instrumentation, while three randomized
backtests run in parallel. If the forward test + at least Tier 1 randomized null both
clear, real capital becomes a discussion at the 30-day mark.

---

## The rule we'll forward-paper-test

**One-liner:** When two correlated stocks (or a stock vs its sector index) drift apart
by 2 standard deviations or more on the day, take a position betting they re-converge.
Hold from 09:30, with a tight ATR-based stop, a trail that arms once we're +0.6% in
profit, and a hard mechanical close at 14:30 IST. Both directions allowed (long the
laggard / short the leader, or vice versa).

**The pieces, in trader terms:**

| Piece | Setting | Why |
|---|---|---|
| Trigger | \|z\| ≥ 2.0 correlation break vs sector index | Filters out daily noise; keeps clear signals |
| Direction | Fade the leg that diverged (LONG laggard / SHORT leader). NOT regime-directional. | Pure mean-reversion. Edge comes from divergence reverting, not from regime side. |
| Universe | F&O 270 (canonical_fno_research_v2: 243 full 5y + 20 short ≥3y) | Backfill complete tonight. 4 truly missing: TATAMOTORS-legacy, TMPV (only 6mo), GMRINFRA, IDFC, PEL — all need Kite-side backfill. |
| **What we DO NOT use** | **PCR / OI / options sentiment** | **Indian options too sparse to extract reliable signal. Old PCR-confirmed slice was the loser (−3.30pp).** |
| **What we DO NOT use** | **Z-cross exit (price returning to mean)** | **Costs more than it saves; TIME_STOP+TRAIL+ATR strictly dominates.** |
| Entry | 09:30 IST market price | First clean print after open; avoid pre-open noise |
| Stop loss | ATR(14) × 2.0 from entry | Proportional to ticker's own volatility, not a fixed % |
| Trail | Arms at +0.6% profit, trails by 1.2% | Locks in winners without choking them |
| Hard exit | 14:30 IST mechanical close | No overnight risk, no afternoon volatility games |

## Why this rule and not the old one

The **old live rule** routed trades through a "PCR-confirmed" filter. Our 60-day
mechanical replay over 154 tickers showed:

| Slice | Hit rate | Average P&L per trade | Total over 60 days |
|---|---|---|---|
| **Old live (PCR-confirmed)** | 50% | **−0.15%** | **−3.30pp** |
| **New rule (PCR stripped)** | 64% | +0.52% | +169.77pp |
| **New rule, ≥2σ slice only** | **92.86%** (39/42) | +1.66% | +69.83pp |

The old rule was routing the losing slice live. The new rule isolates the part that
actually works — high-conviction breaks (≥2σ), no PCR gate, mechanical exits.

## What we don't yet know

We have **60 days** of evidence. Sixty days is a streak, not a system. Four open questions:

1. **War-regime overfit?** Last 60 days were a CAUTION-heavy regime (geopolitical
   stress). Mean reversion has been working precisely because everyone was afraid.
   In RISK-ON or EUPHORIA, the rule may invert — the leader might keep leading. We
   have **no evidence either way** until the forward test or Tier 3 randomized test
   covers other regimes.

2. **Selection-bias luck?** 92.86% on 42 trades is unusual. Could be edge or could
   be lucky which 42 days × tickers we sampled. Tier 1 permutation null answers this:
   if we apply the same exit rules to randomly-chosen entry signals on the same days,
   how often does randomness deliver 92.86%? If less than 1% of the time, we have
   real edge. If 30% of the time, we have a fluke.

3. **Live execution drag?** Replay assumes we get the 09:30 price. Real execution
   has slippage, fills, occasional gaps. The 30-day forward paper test measures
   exactly this: how much of the 60-day replay edge survives real intraday execution.

4. **NEUTRAL-regime sample is critically thin (THE big question).** Long-run market
   regime mix is ~85% NEUTRAL. Our 60-day window was war-skewed: only 6 of 30 trading
   days were NEUTRAL. The breakdown of the 42 ≥2σ trades by regime:

   | Regime | Days | ≥2σ trades | Trades/day | Hit | Mean P&L |
   |---|---|---|---|---|---|
   | CAUTION | 7 | 12 | 1.71 | **100%** | +2.60% |
   | EUPHORIA | 5 | 16 | 3.20 | 93.8% | +1.30% |
   | RISK-ON | 6 | 7 | 1.17 | 85.7% | +1.43% |
   | **NEUTRAL** | **6** | **5** | **0.83** | **80%** | **+0.96%** |
   | RISK-OFF | 6 | 2 | 0.33 | 100% | +1.46% |

   In NEUTRAL, trade volume **halves** vs CAUTION and edge per trade **drops ~63%**.
   The 80% hit rate on n=5 means nothing statistically. The 92.86% headline number is
   overwhelmingly powered by stress regimes (CAUTION+EUPHORIA = 28 of 42 trades, 67%).

   **Hard rule for real-capital decision:** Forward test must accumulate ≥30
   NEUTRAL-regime trade-days before we deploy capital, regardless of how the headline
   30-day numbers look. NEUTRAL is the steady state — that's what we have to validate,
   not the war stress.

## What runs tomorrow morning

| Time IST | Process | Output |
|---|---|---|
| 04:30 | overnight data refresh (existing) | regime label, ETF panel for 2026-04-27 |
| 09:25 | morning_scan (existing) | correlation_breaks.json with all detected breaks |
| **09:30** | **NEW: paper-trade writer** | Append rows to `recommendations.csv` for every \|z\|≥2.0 signal — no real capital, just record |
| 09:30–14:30 | LIVE monitor display (NEW, lower priority) | Terminal screen with current LTP, P&L, stop status |
| **14:30** | **NEW: mechanical closer** | Snap LTP, write exit_reason, P&L per row |
| 14:35 | EOD ledger close + audit | Telegram wrap with day's outcome |

The `recommendations.csv` is forward-only, append-once. Every row has its cohort tag
(σ-bucket, regime, classification, side) so we can pivot the data later.

## What runs in parallel this week

| Workstream | Day | What it answers |
|---|---|---|
| **F&O backfill 62 tickers → 5y daily** | Tonight (running) | Universe expands 154 → ~195 |
| **Sector indices 5y verification** | Tonight (✅ done — all 10 verified) | Foundational |
| **Tier 1 — Permutation null** on 60-day replay | Tonight + Mon | Is the 92.86% real or selection bias? |
| **Tier 2 — Block-bootstrap of minute paths within regime** | Tue–Thu | Does it hold across realistic resampled paths? |
| **Tier 3 — Synthetic minute paths from 5y daily history** | Next week | Does it hold across regimes we haven't yet seen on minute data? |
| **30-day forward paper test** (starts tomorrow) | Now → 2026-05-26 | Live execution validation |

## Decision matrix at the 30-day mark

| Forward test | Tier 1 null | Tier 2 bootstrap | Tier 3 synthetic | Decision |
|---|---|---|---|---|
| ✅ holds (>70% hit, >+0.5% mean) | p < 0.01 | passes | passes | Real capital, small size, 90-day live track |
| ✅ holds | p < 0.01 | passes | fails (regime-specific) | Real capital but only in CAUTION regime |
| ✅ holds | p < 0.01 | fails | — | Investigate; do NOT deploy |
| ✅ holds | p > 0.01 | — | — | The 92.86% was selection bias. Kill. |
| Forward test fails | — | — | — | Kill. |

## Weekly Sunday process (designed but not yet built)

Every Sunday 22:00 IST, an automated job will:
1. **Re-fit the regime engine** on the latest 5y daily window (rolling)
2. **Re-run the mechanical replay** on the trailing 60 days
3. **Compute regime-stratified P&L** from the past week's `recommendations.csv` rows
4. **Compare** this week's hit/Sharpe to the rolling 90-day baseline
5. **Flag drift**: if hit% drops more than 10pp vs baseline, or per-regime cell flips
   sign, alert via Telegram and pause new entries until reviewed
6. **Write to `docs/weekly-recalibration/YYYY-WW-recalibration.md`** with the diff

This is the feedback loop that turns 60-day evidence into a continuously-validated
production rule.

## Hypothesis registration status

`H-2026-04-26-001` — **DRAFT** (not yet committed to registry).
- Spec: `docs/superpowers/specs/2026-04-26-sigma-break-mechanical-v1.md` (TODO tonight)
- In-sample: `docs/research/mechanical_replay/2026-04-25-replay-60day-v2.md` (existing)
- Single-touch holdout: 30-day forward paper test (2026-04-27 → 2026-05-26)
- Will be registered with terminal_state=PRE_REGISTERED before tomorrow's 09:30 paper trade

## What the website says now

We removed: shadow trade table, "Built by a practitioner" bio, "Want the full terminal"
CTA, all author bylines. Replaced with neutral copy noting methodology is under
re-validation. The overnight cron is patched so it physically cannot re-publish trade
JSONs to master. Articles unchanged.

---

**Status of this briefing:** template seeded 2026-04-26 ~02:30 IST.
Will be filled in with actual numbers (n_tickers post-backfill, Tier 1 results, final
rule) and re-issued by 06:00 IST before market open.
