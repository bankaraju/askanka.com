# Phase C V5 — Basket, Index Hedge & Options Validation


## 1. Executive summary

- **v50_a** — ✅ PASS · n=772 · hit=58.5% · Sharpe CI [1.55, 4.56] · p=0.0000 (α=0.0008)
- **v50_b** — ✅ PASS · n=772 · hit=57.3% · Sharpe CI [0.80, 3.79] · p=0.0001 (α=0.0008)
- **v50_c** — ❌ FAIL · n=107 · hit=53.3% · Sharpe CI [-3.75, 4.32] · p=0.5621 (α=0.0008)
- **v50_d** — ❌ FAIL · n=258 · hit=59.3% · Sharpe CI [0.27, 5.43] · p=0.0034 (α=0.0008)
- **v51** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)
- **v52** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)
- **v53** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)
- **v54** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)
- **v55** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)
- **v56** — ✅ PASS · n=3150 · hit=65.3% · Sharpe CI [3.95, 5.40] · p=0.0000 (α=0.0008)
- **v57** — ✅ PASS · n=630 · hit=68.1% · Sharpe CI [5.51, 8.19] · p=0.0000 (α=0.0008)

## 2. Strategy description (basket framing + MOAT rationale)

V5 tests 8 framings of the Phase C OPPORTUNITY signal plus the regime-ranker pair engine (V5.0, the MOAT). V5.0 derives trades from ETF-regime-conditional leader/laggard ranks; V5.1-V5.7 wrap single-stock Phase C signals in baskets, index hedges, and options structures. Bonferroni-corrected at α=0.01 / 12 tests.

## 3. Methodology

- 4-year daily in-sample + 60-day 1-min forward window
- Cost model: Zerodha intraday rates + per-instrument slippage
  (stock 5 bps, NIFTY 2 bps, sectoral 8 bps, options 15 bps)
- Sharpe CI: 10,000 IID bootstrap, seed=7, α=0.01
- Hit rate: two-sided binomial vs 50% null
- Pass gate: Sharpe CI lower bound > 0 AND p < α/12

## 4. Results — V5.0 regime-ranker pair (the MOAT)

- **v50_a** — ✅ PASS · n=772 · hit=58.5% · Sharpe CI [1.55, 4.56] · p=0.0000 (α=0.0008)
  - mean net P&L per trade: ₹367.31
- **v50_b** — ✅ PASS · n=772 · hit=57.3% · Sharpe CI [0.80, 3.79] · p=0.0001 (α=0.0008)
  - mean net P&L per trade: ₹221.26
- **v50_c** — ❌ FAIL · n=107 · hit=53.3% · Sharpe CI [-3.75, 4.32] · p=0.5621 (α=0.0008)
  - mean net P&L per trade: ₹18.57
- **v50_d** — ❌ FAIL · n=258 · hit=59.3% · Sharpe CI [0.27, 5.43] · p=0.0034 (α=0.0008)
  - mean net P&L per trade: ₹365.24

## 5. Results — V5.1 sector pair

- **v51** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)

## 6. Results — V5.2 stock vs sector index

- **v52** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)

## 7. Results — V5.3 NIFTY overlay

- **v53** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)

## 8. Results — V5.4 BANKNIFTY dispersion

- **v54** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)

## 9. Results — V5.5 leader routing

- **v55** — ❌ FAIL · n=0 · hit=nan% · Sharpe CI [nan, nan] · p=nan (α=nan)

## 10. Results — V5.6 horizon sweep

- **v56** — ✅ PASS · n=3150 · hit=65.3% · Sharpe CI [3.95, 5.40] · p=0.0000 (α=0.0008)
  - mean net P&L per trade: ₹369.16

## 11. Results — V5.7 options overlay

- **v57** — ✅ PASS · n=630 · hit=68.1% · Sharpe CI [5.51, 8.19] · p=0.0000 (α=0.0008)
  - mean net P&L per trade: ₹9270.79

## 12. Verdict + production recommendation

**Production recommendation: advance v50_a, v50_b, v56, v57 to paper-forward validation.** Other variants should be retired.
