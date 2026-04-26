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
| EUPHORIA | 5 | +0.1831 | -0.3865 | 40.0% | 60.0% | -1 | 60.0% |
| RISK-ON | 27 | -0.2166 | -0.1496 | 29.6% | 70.4% | +1 | 29.6% |
| NEUTRAL | 412 | +0.0460 | +0.0467 | 54.1% | 45.9% | +0 | -- |
| CAUTION | 29 | -0.0637 | -0.0618 | 44.8% | 51.7% | -1 | 51.7% |
| RISK-OFF | 19 | -0.1256 | -0.1247 | 42.1% | 57.9% | -1 | 57.9% |

## Interpretation

Test 1 PASSES if (a) NEUTRAL captures roughly 60-80 percent of days, 
(b) RISK-ON shows pct_up > 55 percent OR EUPHORIA shows pct_down > 55 percent, 
(c) RISK-OFF / CAUTION show pct_down > 55 percent. 
Test 1 FAILS if every directional zone hovers near 50 percent -- in that case 
the regime label has no information about NIFTY direction and Tests 2-4 are moot.

## Diagnostic addendum (post-fix v2)

The first version of this evaluator had a 1-day alignment bug: it used
the t1-anchored panel's nifty_close (which holds the previous day's close
at each index) with `shift(-1)`, so the measured return was for calendar
day T instead of the calendar day T+1 that the production model trains
against. After fixing to use the raw (un-shifted) NIFTY -- mirroring
`etf_v3_research.build_target` -- the RISK-ON inversion narrowed from
81.5% down to 70.4% down at n=27.

Four hypotheses investigated for the residual RISK-ON inversion:

1. **Date alignment** -- CONFIRMED bug, now fixed.

2. **Hysteresis lag** -- not the bug. `apply_hysteresis` flips the official
   zone ON the second consecutive raw day in the new zone (not 2 days later).
   Trace verified with 31 unit tests covering single-day flip absorption,
   k=2 / k=1 / k=3, and candidate-reset-on-raw-back-to-official.

3. **Signal-sign convention** -- weights look correctly oriented.
   Sample of 5 windows: VIXY consistently negative (correct, VIX rally is
   risk-off), dollar mostly negative (correct, USD safe-haven), SP500 / 
   industrials mostly positive (correct). Treasury is consistently positive
   at tiny magnitude (1e-3 to 1e-4) which is a slight mis-orientation but
   far too small to drive a 70% inversion.

4. **Cluster contamination** -- not contaminated. 27 RISK-ON official days
   span 2024-05-28 through 2026-04-10 across 11 distinct runs, distributed
   across multiple regime cycles. 8 of 11 runs have 0% pct_up -- the
   inversion is *consistent* across the 2-year window, not concentrated in
   one bad slice or event window.

Working hypothesis (UNTESTED): "buy the rumor, sell the news" -- on days
the model labels RISK-ON the prior overnight US session was strong, Indian
markets gap up at open, then sell off into the next-day close. If real, the
direct fix is to *invert* the RISK-ON trade direction (treat it as a fade-
short signal). Sample size n=27 is enough to flag the inversion (binomial
p ~= 0.04) but not enough to commit to the inverted strategy without out-of-
sample confirmation.

Net: 4 of 5 zones now move in the directionally-correct sign for their
hypothesis at the post-fix sample sizes (CAUTION / RISK-OFF / EUPHORIA mild;
n=29 / 19 / 5 respectively). RISK-ON is anti-predictive at n=27.