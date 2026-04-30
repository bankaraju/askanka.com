# Reliance vs OMCs in EUPHORIA — design (2026-04-30)

**Status:** PRE_REGISTERED. Spec frozen at this commit.
**Hypothesis ID:** `H-2026-04-30-RELOMC-EUPHORIA`
**Author:** Bharat Ankaraju + Claude
**Predecessor:** `H-2026-04-30-spread-basket-003` (Reliance vs OMCs unconditional, FAILED on Mode B 5y).

## Motivation

The 5y backtest of the 13 INDIA_SPREAD_PAIRS baskets (Task #24, findings 2026-04-30) found exactly **one PASS cell across all 234 regime-conditional cells**: Reliance vs OMCs (#3) in EUPHORIA regime, 5d hold:

| Cell | n | mean post-20bp | t | hit | BH-FDR |
|---|---|---|---|---|---|
| Reliance vs OMCs, EUPHORIA, 5d | 28 | +274.6 bps | 4.38 | 75.0% | survive |

This is regime-conditional alpha: Reliance benefits asymmetrically from EUPHORIA risk-on rallies relative to OMCs (BPCL, IOC). Likely driver: Reliance's tech / consumer-tech / oil-derivative diversification rallies harder than OMC pure-refining margins in broad-risk-on tape.

Outside EUPHORIA the basket is a structural net-loser (-42.9 bps post-20bp at ALL 5d). Single-touch protection is essential.

## What this hypothesis does NOT do

- Does not modify the live `INDIA_SPREAD_PAIRS_DEPRECATED` basket #3 firing path. That basket continues to fire on news triggers in paper trading until the kill-switch deprecates the news mechanism.
- Does not claim unconditional edge — the hypothesis is **regime-conditional EUPHORIA only**.
- Does not run during the in-sample window (already consumed). Only forward EUPHORIA-regime opens count.

## Hypothesis under test

> **H-2026-04-30-RELOMC-EUPHORIA:** When the V3 CURATED-30 daily regime label is EUPHORIA at T-1 close, opening LONG RELIANCE / SHORT (BPCL + IOC, equal-weight) at T-day open and exiting at T+5 close earns positive net P&L after S1 slippage with hit rate ≥ 60% over the forward holdout.

## Pre-locked design

| Lock | Value | Reason |
|---|---|---|
| Long leg | RELIANCE | per Mode B winner cell |
| Short leg | BPCL + IOC, equal-weight | per Mode B winner cell |
| Sizing | equal-notional, dollar-neutral | matches in-sample test |
| Regime gate | V3 CURATED-30 = EUPHORIA at T-1 close | the conditioning is the hypothesis |
| Open time | T-day 09:15 IST | matches Mode B convention |
| Hold | 5 trading days | per the cell that PASSED |
| Exit time | T+5 close | mechanical |
| Stop loss | -3% per basket | matches engine convention |
| Slippage | 20 bps round-trip per basket (S1) | matches Mode B cost discipline |
| Holdout window | 2026-05-01 → 2027-04-30 (12 months) | EUPHORIA was 28 days in 5y → ~5-6 expected per year |
| Min holdout observations | 5 | small per design (EUPHORIA is rare) |
| Auto-extend | until n ≥ 10 | given EUPHORIA scarcity |
| Verdict bar | post-S1 mean > 0 AND hit ≥ 60% AND p < 0.05 | strict, single-tail bar |
| Statistical test | label-permutation null, 10,000 perms | matches SECRSI / PDR convention |
| Anti-data-snooping | (long, short, regime, hold) frozen as Mode B winner | binding |

## Outputs

- `pipeline/data/research/h_2026_04_30_relomc_euphoria/recommendations.csv` — forward ledger
- `pipeline/data/research/h_2026_04_30_relomc_euphoria/findings_<date>.md` — verdict at min_n
- Engine to be built tomorrow on Contabo: `pipeline/research/h_2026_04_30_relomc_euphoria/`

## Schedule (when wired)

- 09:15 IST daily — `AnkaRELOMCEuphoriaCheck` — read regime label; if = EUPHORIA, open basket
- 14:25 IST exit (5 trading days later) — mechanical close at Kite LTP

NOT scheduled at this commit. Engine code + scheduler entries to land in a follow-up commit before 2026-05-04 (next trading day after long weekend).

## Decision tree at end of holdout

| Result | Next step |
|---|---|
| n ≥ 10 AND post-S1 mean > 0 AND p < 0.05 AND hit ≥ 60% | PASS — promote to live with regime-aware sizing |
| n ≥ 10 AND fails any criterion | FAIL — disable; document; in-sample was the false positive |
| n < 10 at 2027-04-30 | EXTEND another 12 months; do not modify parameters |

## Honest expectation

EUPHORIA was 28 days over 5 years (2.3% of trading days). Forward year may have 3-8 EUPHORIA days. Holdout will be slow — by design. The single-touch lock matters precisely because the temptation to add other regime conditions to "speed up" the test is real and corrupting.

In-sample t=4.38 with n=28 is genuinely strong. If the underlying alternative is real, forward power is high (~85% at α=0.05 with n=10).

The MaxDD on the in-sample cell was -608 bps — the path is bumpy. Sizing for tail risk (notional capped by 2× expected volatility) is essential before going live.

## Honest risks

- **Regime label uses today's frozen V3 CURATED-30 weights.** Forward EUPHORIA labels are computed contemporaneously by the production daily-signal job — that's true PIT. The in-sample test had hindsight in label assignment; forward test has none. If forward EUPHORIA is rarer or differently-distributed than in-sample, the verdict may shift.
- **Reliance has had structural changes** (Jio, retail, green energy) over 5y that may not persist. The basket bet implicitly assumes RELIANCE's diversification premium continues.
- **Small-n holdout is fragile.** A single -3% stop-out wipes out multiple positive trades. Sizing matters.
