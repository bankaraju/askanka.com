# Test 1 -- Daily regime classification accuracy

Source: `pipeline\data\research\etf_v3_evaluation\phase_2_backtest\runs_smoke\wf_lb756_u126_seed0\rolling_refit.json`
OOS days: **493**  |  unique zones seen: **5 / 5**  |  hysteresis k=2  |  lookback=756d

## Zone distribution (official, post-hysteresis)

| Zone | n | pct |
|---|---:|---:|
| EUPHORIA | 5 | 1.0% |
| RISK-ON | 27 | 5.5% |
| NEUTRAL | 413 | 83.8% |
| CAUTION | 29 | 5.9% |
| RISK-OFF | 19 | 3.9% |

## Per-zone NIFTY next-day outcome

Hypothesis direction: +1 expect up, -1 expect down, 0 = no directional view.
Hypothesis accuracy = pct_up if +1, pct_down if -1, NaN if 0.

| Zone | n | mean ret pp | median ret pp | pct up | pct down | hyp dir | hyp acc % |
|---|---:|---:|---:|---:|---:|---:|---:|
| EUPHORIA | 5 | +0.3465 | +0.1883 | 60.0% | 40.0% | -1 | 40.0% |
| RISK-ON | 27 | -0.2646 | -0.1932 | 18.5% | 81.5% | +1 | 18.5% |
| NEUTRAL | 412 | +0.0291 | +0.0477 | 54.1% | 45.9% | +0 | -- |
| CAUTION | 29 | +0.1884 | +0.0421 | 51.7% | 44.8% | -1 | 44.8% |
| RISK-OFF | 19 | -0.0604 | -0.0540 | 47.4% | 52.6% | -1 | 52.6% |

## Interpretation

Test 1 PASSES if (a) NEUTRAL captures roughly 60-80 percent of days, 
(b) RISK-ON shows pct_up > 55 percent OR EUPHORIA shows pct_down > 55 percent, 
(c) RISK-OFF / CAUTION show pct_down > 55 percent. 
Test 1 FAILS if every directional zone hovers near 50 percent -- in that case 
the regime label has no information about NIFTY direction and Tests 2-4 are moot.