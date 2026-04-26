# Test 1 + NEUTRAL-day sector decomposition

NEUTRAL days from `pipeline\data\research\etf_v3_evaluation\phase_2_backtest\runs_smoke\wf_lb756_u126_seed0\test_1_raw_zones.csv`: **413**
Sectoral indices source: `pipeline\data\sectoral_indices`  (10 indices)
Missing proxies vs catalog: INFRA

## Per-sector NIFTY-style next-day return on NEUTRAL days

Columns: `mean_pp` = mean next-day percent return when held LONG; 
`fade_short_pp` = profit from a fade-short (covers at next close), equals `-mean_pp`. 
`IR_per_day` = mean / std.

| Sector | n | mean (pp) | median (pp) | std | pct up | pct down | IR/day | fade short pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BANKNIFTY | 413 | +0.0687 | +0.1050 | 1.0411 | 55.2% | 44.8% | +0.0660 | -0.0687 |
| NIFTYAUTO | 409 | +0.0283 | +0.0062 | 1.2615 | 50.1% | 49.9% | +0.0224 | -0.0283 |
| NIFTYENERGY | 409 | +0.0326 | +0.0749 | 1.3470 | 54.5% | 45.5% | +0.0242 | -0.0326 |
| NIFTYFMCG | 409 | +0.0189 | +0.0006 | 0.8643 | 50.1% | 49.9% | +0.0219 | -0.0189 |
| NIFTYIT | 413 | +0.0141 | +0.0136 | 1.3748 | 51.1% | 48.9% | +0.0103 | -0.0141 |
| NIFTYMEDIA | 409 | -0.0699 | -0.0456 | 1.5417 | 48.9% | 51.1% | -0.0453 | +0.0699 |
| NIFTYMETAL | 409 | +0.1177 | +0.1849 | 1.6101 | 55.8% | 44.2% | +0.0731 | -0.1177 |
| NIFTYPHARMA | 411 | +0.0671 | +0.0758 | 0.9896 | 54.5% | 45.5% | +0.0678 | -0.0671 |
| NIFTYPSUBANK | 409 | +0.0906 | +0.0180 | 1.7000 | 50.4% | 49.6% | +0.0533 | -0.0906 |
| NIFTYREALTY | 409 | -0.0043 | +0.0596 | 1.7777 | 51.1% | 48.7% | -0.0024 | +0.0043 |

## Catalog hypothesis: NEUTRAL-day fade-shorts

Catalog: PSU BANK / ENERGY / INFRA short-fades **worked**; 
AUTO / IT / FMCG short-fades **lost**. 
Bucket mean is the equal-weighted average of the per-sector mean returns. 
`fade_short_pp` is the profit from fading SHORT (= -mean_pp). 
Hypothesis confirmed if `fade_works` bucket has fade_short_pp > 0 
AND `fade_loses` bucket has fade_short_pp <= 0.

| Bucket | n sectors | sectors | mean (pp) | fade short pp | avg pct up |
|---|---:|---|---:|---:|---:|
| fade_works | 2 | NIFTYPSUBANK,NIFTYENERGY | +0.0616 | -0.0616 | 52.5% |
| fade_loses | 3 | NIFTYAUTO,NIFTYIT,NIFTYFMCG | +0.0204 | -0.0204 | 50.4% |
| neutral_set | 5 | BANKNIFTY,NIFTYMETAL,NIFTYPHARMA,NIFTYMEDIA,NIFTYREALTY | +0.0359 | -0.0359 | 53.1% |

## Verdict logic

If `fade_works.fade_short_pp` > 0 AND `fade_loses.fade_short_pp` < 0 
AND the spread is at least 0.05pp/day (~12.5pp/yr), the catalog claim holds 
on the smoke window and Test 2 should proceed to a full P&L backtest with 
the ZCROSS / sector_overlay / coef_delta_marker stack restricted to the 
fade_works sectors. Otherwise, the catalog claim is unsupported on this 
sample and Tests 2-4 need a different cut.