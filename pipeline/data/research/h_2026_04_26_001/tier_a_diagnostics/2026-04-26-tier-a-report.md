# Tier A negative-control diagnostics — H-2026-04-26-001

- **Generated:** 2026-04-26T05:02:32Z
- **Input:** `pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv`
- **Sigma threshold:** 2.0
- **Observed trades (sigma slice):** 42 of 388 candidate-pool rows
- **Seed:** 20260426
- **Compute time:** 0.028s

**Overall Tier A verdict: PASS**

---

## Tier A.1 — Trend-follow opposite (direction integrity) — PASS

Spec gate: §8 direction integrity. The flipped book must lose money,
with `|mean P&L| >= 0.30%` per
trade. If trend-follow opposite is positive or break-even, our edge isn't
mean-reversion — KILL.

| Side | n | Hit rate | Mean P&L | Sum P&L |
|---|---:|---:|---:|---:|
| Observed (FADE) | 42 | 92.8571% | +1.6626% | +69.8283% |
| Flipped (TREND-FOLLOW) | 42 | 7.1429% | -1.6626% | -69.8283% |

- Direction-integrity threshold: |mean P&L| >= 0.30% AND mean P&L < 0
- Flipped mean P&L: -1.6626%
- Verdict: **PASS**

---

## Tier A.2 — Random direction (coin flip) — PASS

For each of the 42 trades draw LONG/SHORT 50/50 and recompute
hit rate. 10,000 permutations, seeded.

- **Observed hit rate:** 92.8571%
- **Random-direction distribution (hit %):**
  - min: 21.43, p01: 33.33, p05: 38.10, p50: 50.00, mean: 50.10, p95: 61.90, p99: 69.05, max: 85.71
- **p-value (P(random >= observed)):** 0.000000
- Direction-alpha threshold: p < 0.01
- Verdict: **PASS**

---

## Tier A.3 — Per-week stationarity — PASS

ISO-week stratification within the in-sample window. Pass requires
>= 4 positive weeks AND no single week
carrying > 50% of total P&L.

- **n weeks:** 7
- **n weeks with positive mean P&L:** 7
- **Max single-week P&L share:** +36.65%
- **Total sigma-slice P&L:** +69.8283%
- Verdict: **PASS**

| Week | Start | n | Hits | Hit % | Mean P&L | Sum P&L | Share |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-W11 | 2026-03-09 | 2 | 1 | 50.00% | +1.6395% | +3.2789% | +4.70% |
| 2026-W12 | 2026-03-16 | 1 | 1 | 100.00% | +1.2103% | +1.2103% | +1.73% |
| 2026-W13 | 2026-03-23 | 4 | 4 | 100.00% | +1.8703% | +7.4813% | +10.71% |
| 2026-W14 | 2026-03-30 | 3 | 3 | 100.00% | +0.6128% | +1.8384% | +2.63% |
| 2026-W15 | 2026-04-06 | 18 | 17 | 94.44% | +1.4042% | +25.2755% | +36.20% |
| 2026-W16 | 2026-04-13 | 3 | 3 | 100.00% | +1.7165% | +5.1495% | +7.37% |
| 2026-W17 | 2026-04-20 | 11 | 10 | 90.91% | +2.3268% | +25.5944% | +36.65% |

---

## Bottom-line verdict

Tier A diagnostics PASS overall: trend-follow opposite loses -1.6626% per trade (kills the trend-follow alternative), random-direction p-value is 0.0000 (direction choice IS the alpha), and 7 of 7 weeks individually contribute positive mean P&L with no single week dominating (max share +36.65%). Edge is at least temporally consistent within the 60-day window.
