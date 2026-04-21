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

- **v51** — ⏸ PENDING — requires Kite 1-minute bars which are unavailable outside scheduled market hours. Ledger is empty. Re-run during 09:16–14:30 IST to populate.

## 6. Results — V5.2 stock vs sector index

- **v52** — ⏸ PENDING — requires NIFTY/BANKNIFTY/NIFTYIT/FINNIFTY daily bars from Kite, which are unavailable outside scheduled hours (Kite session not active). Re-run after `AnkaRefreshKite` (09:00 IST) to populate.

## 7. Results — V5.3 NIFTY overlay

- **v53** — ⏸ PENDING — same Kite index bar dependency as V5.2.

## 8. Results — V5.4 BANKNIFTY dispersion

- **v54** — ⏸ PENDING — same Kite index bar dependency as V5.2.

## 9. Results — V5.5 leader routing

- **v55** — ⏸ PENDING — same Kite index bar dependency as V5.2.

## 10. Results — V5.6 horizon sweep

- **v56** — ✅ PASS · n=3150 · hit=65.3% · Sharpe CI [3.95, 5.40] · p=0.0000 (α=0.0008)
  - mean net P&L per trade: ₹369.16

## 11. Results — V5.7 options overlay

- **v57** — ✅ PASS · n=630 · hit=68.1% · Sharpe CI [5.51, 8.19] · p=0.0000 (α=0.0008)
  - mean net P&L per trade: ₹9270.79

## 12. Verdict + production recommendation

**4 of 12 variants pass Bonferroni-corrected gate (α=0.0008):** v50_a, v50_b, v56, v57.

- **V5.0 is the MOAT.** Sub-variants a and b both clear the bar with Sharpe CIs well above zero. Sub-variant c (EUPHORIA-only, n=107) and d (5-day hold, n=258) lack statistical power at this sample size.
- **V5.6 (horizon sweep, n=3150)** passes strongly — the signal is robust across hold horizons.
- **V5.7 (synthetic options overlay, n=630)** passes with the highest point Sharpe (6.86) — but mean ₹9,271/trade reflects leverage, not raw edge. Treat as an enhancement layer, not independent alpha.
- **V5.1 (sector pair)** — **PENDING: requires Kite 1-minute bars during market hours.** Ledger empty. Re-run `python -m pipeline.research.phase_c_v5.run_v5 --force` from 09:20–14:00 IST to populate.
- **V5.2–V5.5** — **PENDING: require Kite index daily bars (NIFTY/BANKNIFTY/NIFTYIT/FINNIFTY).** These are unavailable outside the scheduled session. Run after `AnkaRefreshKite` (09:00 IST).

**Production recommendation: advance v50_a, v50_b, v56, v57 to paper-forward validation.** V5.1–V5.5 are not retired — they are infrastructure-blocked pending Kite sessions. Re-run during market hours for a conclusive result.
