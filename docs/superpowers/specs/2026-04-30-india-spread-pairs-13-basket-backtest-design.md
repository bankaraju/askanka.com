# 5y backtest of 13 INDIA_SPREAD_PAIRS baskets — design (2026-04-30)

**Status:** PRE_REGISTERED design. Not yet executed. Spec frozen at this commit.
**Hypothesis IDs:** one per basket — `H-2026-04-30-spread-basket-001` through `H-2026-04-30-spread-basket-013`.
**Author:** Bharat Ankaraju + Claude
**Predecessor:** `pipeline/autoresearch/unified_backtest.py` (3y, 6 baskets, no costs — to be deprecated by this study).

## Motivation

The 13 spread baskets in `INDIA_SPREAD_PAIRS_DEPRECATED` (`pipeline/config.py:119-202`) fire live in paper trading on news-keyword triggers and have **no formal backtest**. The most consistent paper earner ("Commodity-Credit Divergence" = PSU Commodity vs Banks, basket #6) is in this list. Per user directive 2026-04-30: *"making money out of god knows what news"* — ungrounded P&L is not the same as edge.

The existing `AnkaUnifiedBacktest` covers only 6 of the 13 (and reports an unrealistic Sharpe of 13.72 because no costs are deducted). This study replaces it with a hypothesis-grade 5y test of all 13 baskets.

## What this study does NOT do

- **Does not** trade live capital.
- **Does not** generate any new trade signal — pure historical replay.
- **Does not** modify the live news-trigger firing of the 13 baskets — they continue paper-trading until this study's verdict reaches them.

## Hypothesis under test (per basket)

> **H_basket:** When the news-event trigger keywords for basket B fire on day d, the basket return over hold period h ∈ {1d, 3d, 5d}, conditioned on the regime label, has positive post-cost expectation, hit rate ≥ 55%, regime-conditional Sharpe ≥ 0.5, and survives bootstrap stability ≥ 70% across random 1y windows.

For each basket × regime × hold period: report mean post-cost return, hit rate, Sharpe, max drawdown, t-stat, two-sided p-value with multiple-comparison correction.

## Pre-locked design

| Lock | Value | Reason |
|---|---|---|
| Universe | 13 baskets in `INDIA_SPREAD_PAIRS_DEPRECATED` | full — not a 6-of-13 subset |
| Window | 5 calendar years (2021-04-23 → 2026-04-22) | matches canonical sector_panel + F&O CSV history |
| Source data — equities | `pipeline/data/fno_historical/<TICKER>.csv` | canonical, audit-passed |
| Source data — regime tape | reconstructed daily regime label for the 5y window | uses V3 CURATED-30 weights, point-in-time |
| News trigger replay | reconstruct from `pipeline/data/news_events_history.json` if available; else simulate via keyword extraction over historical headlines (with provenance recorded) | data-validation gate per Anka policy §11 |
| Hold periods | 1d, 3d, 5d | matches existing engine grid |
| Sizing | equal-notional per leg, dollar-neutral within basket | matches live engine |
| Slippage / cost | **5 bps per leg per turn = 20 bps round-trip on a 4-leg basket** | conservative, matches SSF reality |
| Stops | mechanical max-loss -3% per basket | matches live engine |
| Time stop | exit at end of hold period regardless of P&L | mechanical |
| Multiple-comparison correction | Benjamini-Hochberg FDR @ 10% across 13 baskets × 3 hold periods × 5 regimes = 195 cells | per autoresearch v2 standard |
| Bootstrap | 200 random 252-day windows per (basket, hold, regime) | per backtesting-specs §11 |
| Verdict bar | post-cost mean > 0 AND t-stat > 2 AND BH-FDR survive AND bootstrap stability ≥ 60% AND hit rate ≥ 55% | strict |
| Anti-data-snooping | the 13 basket definitions and their trigger keyword lists are FROZEN AS-IS from the live config; no post-look refinement | binding |

## Outputs

- `pipeline/data/research/india_spread_pairs_backtest/per_basket_<date>.csv` — event-level table
- `pipeline/data/research/india_spread_pairs_backtest/summary_<date>.csv` — (basket × regime × hold) aggregates
- `pipeline/data/research/india_spread_pairs_backtest/findings_<date>.md` — per-basket plain-English verdict
- `pipeline/data/research/india_spread_pairs_backtest/registry_proposals.jsonl` — one PRE_REGISTERED entry per basket that passes; each becomes its own single-touch holdout going forward

## Decision tree at the end

| Result | Next step |
|---|---|
| Basket passes full bar in ≥ 1 regime × hold combo | Register as `H-2026-04-30-spread-basket-NNN` (NNN = basket number). Re-architect as data-primary + news-confirmation per Task #23. Single-touch holdout 60 trading days. |
| Basket marginal (passes mean and hit rate but fails t or stability) | Mark as MARGINAL. Re-test in 6 months as out-of-sample. Continue paper-trading; do not retire. |
| Basket fails | Document as FAIL. Stop paper-trading on this basket once V1 kill-switch fires (or sooner if P&L erodes). |

## Why "Commodity-Credit Divergence" first

Basket #6 (PSU Commodity vs Banks) is the highest-stakes registration since it's the most-consistent paper earner. It runs first in the per-basket loop so its verdict is available earliest.

## Honest expectation

Some baskets will pass, some won't. Defence-vs-IT and Coal-vs-OMCs have visible macro logic and will likely show edge; EV-vs-ICE-Auto and Infra-Capex-Beneficiaries are looser thematic plays with thinner trigger histories and may fail on n.

The unified_backtest's claim that "Defence vs IT: 85% win rate" is suspect because that test had no costs — expect post-cost hit rate to land 60-65% if real.

## Cost discipline

The 5 bps per leg per turn assumption may be optimistic for thinly-traded names. To be honest:
- Liquid (RELIANCE, HDFC, ICICI, TCS, INFY): 3-5 bps achievable
- Mid-liquid (ONGC, COAL, BPCL, SUNPHARMA, HAL): 5-8 bps
- Thinly-traded (BEL, HUDCO, NHPC, AMBUJACEM): 8-15 bps

Sensitivity analysis: re-run with 30 bps round-trip cost to see which baskets still pass. If a basket only passes at 20 bps but fails at 30 bps, mark it MARGINAL not PASS.

## Output for each basket — minimum required fields

| Field | Required |
|---|---|
| basket_id | yes |
| regime | yes (per-regime broken out) |
| hold_period_days | yes |
| n_events | yes |
| mean_pnl_pre_cost_bps | yes |
| mean_pnl_post_cost_bps | yes (20bps) |
| mean_pnl_post_cost_bps_30bp | yes (sensitivity) |
| hit_rate_post | yes |
| sharpe | yes |
| max_drawdown | yes |
| t_stat | yes |
| p_value | yes |
| bh_fdr_pass | yes |
| bootstrap_stability_post | yes |
| verdict | PASS / MARGINAL / FAIL_POSTCOST / FAIL_TSTAT / FAIL_STABILITY / INSUFFICIENT_N |

## Pass criteria (all must hold)

- post-cost mean > 0 at 20 bps cost AND > 0 at 30 bps cost (sensitivity)
- t-stat > 2.0
- BH-FDR survive (10% q-value across 195 cells)
- bootstrap stability ≥ 60%
- hit rate ≥ 55%
- max drawdown ≤ 25%
- n_events ≥ 10 per (basket, regime, hold) cell

## What this enables

- Each passing basket becomes a properly-registered hypothesis with a holdout — *not* a kill-switched zombie.
- The news-driven framework can be deprecated by H-2026-04-29 V1 WITHOUT silently losing paying paper books — the passing baskets stay alive under their own registration.
- The "making money out of god knows what news" gap closes.
