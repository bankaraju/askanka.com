# Regime transition matrix + overnight NIFTY by today's regime

_generated_: 2026-04-26T07:07:23+00:00

## Why this exists

Settles the recurring trader question: "if today is EUPHORIA and I take an overnight position, how likely am I to lose money?"

## Data

- Regime history: **1256 trading days** (2021-04-23 → 2026-04-23)
- NIFTY close → next-day open from `pipeline/data/india_historical/indices/NIFTY_daily.csv`
- Five-zone taxonomy: RISK-OFF / CAUTION / NEUTRAL / RISK-ON / EUPHORIA

## 1. Transition matrix — P(tomorrow's zone | today's zone), %

| today \ tomorrow | RISK-OFF | CAUTION | NEUTRAL | RISK-ON | EUPHORIA |
|---|---:|---:|---:|---:|---:|
| **RISK-OFF** | 16.6 | 18.4 | 22.1 | 18.9 | 24.0 |
| **CAUTION** | 19.6 | 18.9 | 23.2 | 22.1 | 16.1 |
| **NEUTRAL** | 16.2 | 27.4 | 20.6 | 21.6 | 14.2 |
| **RISK-ON** | 19.8 | 21.5 | 27.3 | 12.8 | 18.6 |
| **EUPHORIA** | 13.6 | 24.6 | 25.9 | 19.6 | 16.4 |

**Reading:** the regime *label* is **barely persistent at all**. Same-zone-tomorrow probabilities range 13-21%, indistinguishable from the uniform baseline of 20% (one zone of five). In other words, the 5-zone label by itself has essentially no power to predict tomorrow's label.

### Same-zone persistence (diagonal of matrix)

| Today's zone | P(same zone tomorrow) | Most likely next zone | Probability |
|---|---:|---|---:|
| RISK-OFF | 16.6% | EUPHORIA | 24.0% |
| CAUTION | 18.9% | NEUTRAL | 23.2% |
| NEUTRAL | 20.6% | CAUTION | 27.4% |
| RISK-ON | 12.8% | NEUTRAL | 27.3% |
| EUPHORIA | 16.4% | NEUTRAL | 25.9% |

**Reading:** the most likely next-zone for any today is essentially random — 20-27% probabilities across the most likely target. There is no Markov stickiness in the daily label.

## 2. Overnight NIFTY return (close → next-open) by today's zone

| Today's zone | n | mean % | median % | worst % | best % | % days negative | % days loss > 1% | % days loss > 2% | overnight Sharpe (ann) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **RISK-OFF** | 209 | -0.178 | -0.054 | -5.00 | +1.65 | 55.02 | 9.09 | 3.35 | -3.951 |
| **CAUTION** | 262 | +0.060 | +0.063 | -3.01 | +3.58 | 40.84 | 2.67 | 0.38 | 1.571 |
| **NEUTRAL** | 276 | +0.079 | +0.104 | -2.48 | +1.81 | 35.51 | 2.9 | 0.72 | 2.696 |
| **RISK-ON** | 233 | +0.201 | +0.170 | -1.31 | +2.36 | 27.9 | 0.86 | 0.0 | 6.751 |
| **EUPHORIA** | 210 | +0.268 | +0.244 | -1.92 | +4.86 | 21.9 | 2.38 | 0.0 | 6.853 |

## Bottom line — three trader-actionable findings

1. **The 5-zone label is NOT next-day Markov-persistent.** Tomorrow's label is roughly uniform regardless of today's. So the *label* itself has no overnight stickiness — every zone has ~80% probability of being a different zone tomorrow.

2. **However, today's zone DOES predict overnight NIFTY direction.** The overnight gap is monotone in the zone ordering:

   - RISK-OFF → mean overnight -0.178% (worst -5.00%, 3.35% of nights lose >2%)
   - CAUTION  → mean overnight +0.060%
   - NEUTRAL  → mean overnight +0.079%
   - RISK-ON  → mean overnight +0.201%
   - EUPHORIA → mean overnight +0.268% (worst -1.92%, 0.0% of nights lose >2%)

3. **EUPHORIA-day overnight is the SAFEST and HIGHEST-EXPECTED-RETURN zone, not the most dangerous.** The intuition that 'EUPHORIA is fragile so I'll lose overnight' is **inverted** by the data. The dangerous overnight zone is RISK-OFF, where mean is negative and worst-case losses are -5%. EUPHORIA worst overnight in 5 years is -1.92% on n=210 nights.

## Caveats

1. Sample period 2021-04-23 → 2026-04-23 includes a massive bull run + the 2026 war stress; the conditional means could shift in a different macro regime.
2. Zone label is a daily quantity; intraday flips are not measured here (no minute-bar regime exists).
3. Overnight return = close-to-next-open NIFTY level only. Stock-specific overnight gaps can dwarf the index gap; this measurement does NOT cover idiosyncratic overnight risk on a single F&O name.
4. The result speaks to *unconditional* expected overnight return given the zone. It does not say anything about whether a *specific* signal (e.g. a closed σ-break) is safer to hold overnight.

## How this fits with the existing engine

The ETF regime model already includes Indian inputs (India VIX, FII net, DII net, NIFTY close, BankNIFTY close, PCR, RSI, sector breadth) alongside the 31 global ETFs (`pipeline/autoresearch/etf_reoptimize.py:308-315`). The 62.3% next-day NIFTY directional accuracy is the merged-model accuracy. The Karpathy-style 2000-iteration random search at `etf_reoptimize.py:149` is what produces those weights. The MSI scalar (MACRO_STRESS / NEUTRAL / EASY) is a downstream display computed from a subset of the same inputs; its raw components are already in the optimizer's feature pool, so feeding the MSI scalar separately is unlikely to add much marginal information.
