# Banks × NBFC Pair-Divergence-Reversion (PDR) — design (2026-04-30)

**Status:** PRE_REGISTERED. Spec frozen at this commit.
**Hypothesis ID:** `H-2026-04-30-PDR-BNK-NBFC` (sister to SECRSI `H-2026-04-27-003`).
**Author:** Bharat Ankaraju + Claude
**Predecessor:** PDR-001 (daily, FAILED 2026-04-30 — continuation hides) and PDR-002 (intraday discovery, 2026-04-30 — directionally validated, underpowered).

## Motivation

PDR-002 intraday scan (60-day Kite 1-min cache, 38 trading days, 10 sector pairs × 3 T-points × 3 k-thresholds) found the Banks × NBFC pair at T=11:00 IST, k=1.0σ shows the expected mean-reversion signature:

| Cell | n | mean post-cost | win % | t | verdict |
|---|---|---|---|---|---|
| Banks × NBFC, t=11:00, k=1.0 | 9 | **+11.0 bps** | **78%** | +1.32 | FAIL_TSTAT (underpowered) |
| Banks × NBFC, t=11:00, k=1.5 | 6 | +11.5 bps | 83% | +0.96 | FAIL_TSTAT |
| Banks × NBFC, t=12:00, k=1.0 | 9 | +10.0 bps | 67% | +1.42 | FAIL_TSTAT |
| Banks × NBFC, t=12:00, k=1.5 | 6 | +9.2 bps | 67% | +1.11 | FAIL_TSTAT |

Three nearby cells consistently positive 9-12 bps post-cost with 67-83% hit rate. n is small but the cross-cell consistency is the read. Per backtesting-specs.txt §10.4 the in-sample window is now consumed; the only honest test is forward-only.

This is also the architectural twin to SECRSI: SECRSI is a **trend continuation** intraday pair (long the leader, short the laggard within a sector); PDR is a **mean-reversion** intraday pair across two highly-correlated sectors (long the laggard, short the leader). Running them in parallel diversifies regime exposure — when one wins the other typically loses.

## What this hypothesis does NOT do

- Does not modify SECRSI plumbing.
- Does not back-fit any new threshold from the in-sample data — the cell `t=11:00, k=1.0σ` is the locked specification AS-IS.
- Does not claim edge — the in-sample evidence is **underpowered, not significant**. This is a forward-only single-touch holdout to settle the question.
- Does not retrofit historical days — only forward observations 2026-05-01 onwards count toward verdict.

## Hypothesis under test

> **H-2026-04-30-PDR-BNK-NBFC:** When the Banks-sector daily-mean and NBFC_HFC-sector daily-mean returns from 09:15 IST OPEN to 11:00 IST diverge by more than k=1.0σ (σ measured over the prior 60 trading days), opening a market-neutral basket at 11:00 IST that LONGs the laggard sector (top-2 stocks by liquidity) and SHORTs the leader sector (top-2 stocks by liquidity), then closing at 14:25 IST (mechanical TIME_STOP), earns positive net P&L after S1 slippage, with hit rate ≥ 55% and Sharpe ≥ 0.8 across the forward holdout.

## Pre-locked design

| Lock | Value | Reason |
|---|---|---|
| Pair | (Banks, NBFC_HFC) | only cell that passed t > 1.0 in PDR-002 with n ≥ 6 across multiple nearby cells |
| Divergence threshold k | 1.0σ | best n/edge tradeoff in PDR-002 (k=1.5 thinner, k=2.0 too thin) |
| σ rolling window | 60 trading days | matches Kite 1-min cache depth |
| Signal time | 11:00 IST | best PDR-002 cell |
| Exit time | 14:25 IST | mechanical TIME_STOP, last fully-tradeable bar before 14:30 cutoff |
| Direction | LONG laggard, SHORT leader (mean-reversion) | by design |
| Universe | F&O subset of Banks + NBFC_HFC sectors per `canonical_fno_research_v3.json` | already audited |
| Sector mapping | `pipeline.scorecard_v2.sector_mapper.SectorMapper` | canonical |
| Stock selection | top-2 by 60-day mean traded value per sector | reproducible |
| Sizing | equal-notional 4 legs, dollar-neutral | matches SECRSI |
| Per-leg stop | ATR(14) × 2.0 | matches SECRSI |
| Slippage | S1 (5 bps per leg per turn = 20 bps round-trip on 4 legs) | conservative |
| In-sample window | 2026-02-19 → 2026-04-30 (the 38 PDR-002 days, last day = today) | already exhausted |
| Holdout window | 2026-05-01 → 2026-08-31 (auto-extend if n < 40) | per backtesting-specs §10.4 |
| Min holdout observations | 40 | matches SECRSI |
| Statistical test | label-permutation null, 10,000 perms | matches SECRSI |
| Verdict bar | post-S1 mean > 0 AND p < 0.05 AND hit ≥ 55% AND Sharpe ≥ 0.8 | strict |
| Anti-data-snooping | the (pair, k, T_sig) triple is FROZEN AS-IS from PDR-002 | binding |

## Outputs

- `pipeline/data/research/h_2026_04_30_pdr_bnk_nbfc/recommendations.csv` — forward-only ledger
- `pipeline/data/research/h_2026_04_30_pdr_bnk_nbfc/findings_<date>.md` — verdict at min_n
- `pipeline/data/research/h_2026_04_30_pdr_bnk_nbfc/diagnostics.csv` — daily σ, divergence Z, no-trigger explanations

## Schedule (when wired)

- 11:00 IST daily — `AnkaPDRBNKNBFCOpen` — sector snapshot + divergence Z; if |Z| > 1.0 fire 4-leg basket open
- 14:25 IST daily — `AnkaPDRBNKNBFCClose` — mechanical TIME_STOP at Kite LTP

NOT scheduled at this commit — hypothesis pre-registered, engine skeleton only. Schedule in the same commit as the engine code goes live.

## Decision tree at end of holdout

| Result | Next step |
|---|---|
| n ≥ 40 AND post-S1 mean > 0 AND p < 0.05 AND hit ≥ 55% AND Sharpe ≥ 0.8 | PASS — promote to live (small notional, regime-aware sizing) |
| n ≥ 40 AND fails any of {p, hit, Sharpe} | FAIL — disable; document; do not re-run with adjusted params (single-touch consumed) |
| n < 40 at 2026-08-31 | EXTEND holdout to 2026-12-31, no parameter change |

## Honest expectation

PDR-002 in-sample t = 1.32 implies the alternative hypothesis (true edge) is plausible but not established. Forward expectation under H1 (assuming the in-sample mean is the truth): n=40 forward observations × t per obs ≈ 1.32 × √(40/9) = 2.78 → p ≈ 0.005. So if the in-sample is real, the forward test has ~80% power to detect it at α = 0.05.

If the underlying is null, the forward test will land at hit ≈ 50%, mean ≈ 0, and we move on.

## Honest risks

- **n=9 in-sample is small.** The 11.0 bps mean could easily be 0 in expectation under sampling variance.
- **Pair tightness drift.** Banks-NBFC correlation can break in regime shifts (e.g., bank-specific stress doesn't propagate to NBFCs). The σ rolling window adapts but with lag.
- **Liquidity asymmetry.** Some NBFC names are thinner — slippage may exceed 5 bps. If post-cost mean turns negative under realistic slippage, the trade dies.
- **Regime contamination.** PDR-002 covered a 38-day NEUTRAL stretch. Forward holdout may straddle a regime shift; verdict is unconditional but per-regime breakout is reported in findings.
