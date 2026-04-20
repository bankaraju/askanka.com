# Phase C Validation — Executive Summary

**Date:** 2026-04-20
**Author:** Anka Research
**Branch:** `feat/dashboard-restructure`
**Run:** 14-symbol × 18-month in-sample (2024-10-01 → 2026-03-31, daily); 14-symbol × 20-session forward (2026-04-01 → 2026-04-20, 1-min bars).
**Trade label:** `OPPORTUNITY` (full label; per-symbol PCR backfilled from NSE F&O bhavcopy).

## What this tests

Phase C is the intraday correlation-break layer of Anka's regime-stock engine. Given a per-stock, per-regime expected return trained on two years of rolling history (Phase A), and today's active regime (Phase B), Phase C flags stocks whose actual return on the day is lagging, opposite, or confirming the expected direction — and crosses that signal with PCR and open-interest anomaly data to produce one of five classifications. The canonical live logic lives in `pipeline/autoresearch/reverse_regime_breaks.py`.

The user's hypothesis: Phase C `OPPORTUNITY` signals have their strongest edge as **intraday-only** trades entered at the signal time and closed mechanically at 14:30 IST, sidestepping overnight risk.

## Verdict

**H1 OPPORTUNITY: FAIL** — across 6 of 6 statistical criteria. The full label (PCR agreement required) does outperform the degraded variant on per-trade economics, but it still loses money in-sample and the forward 21-trade sample is too thin to reverse the conclusion at 99% confidence.

Full criteria walk-through in [`07-verdict.md`](07-verdict.md).

## Headline metrics

| Metric | In-sample (18 mo, daily) | Forward (20 sessions, 1-min) |
|---|---:|---:|
| Trades | 630 | 21 |
| Hit rate | 43.5% | 76.2% |
| Total net P&L | **−₹51,327** | **+₹3,853** |
| Avg net P&L / trade | −₹81.5 | +₹183.5 |
| Bootstrap Sharpe (point) | −1.97 | +7.22 |
| Sharpe 99% CI | [−3.59, −0.35] | [−2.02, +41.40] |
| Binomial p (vs 50%) | **0.0012** | 0.0266 |
| Max drawdown | 58.9% of ₹100k seed | 1.4% of ₹100k seed |
| Regimes passed (n ≥ 30) | 0 of 4 | n/a |
| Side mix | 593 SHORT / 37 LONG | (similar bias) |
| Exit reason mix (forward) | — | 14 TARGET / 7 TIME_STOP / 0 STOP |

The 593:37 SHORT skew is structural: most Indian-equity PCR values sit below 1.0 (call OI > put OI), which in the classifier maps to "BEARISH" — so the OPPORTUNITY label fires predominantly when Phase A expects an UP move and the actual return is lagging *and* PCR confirms a bearish bias. The strategy is, in practice, "fade weak rallies on bearish PCR."

## Comparison to the degraded ablation

The previous run with `--trade-label POSSIBLE_OPPORTUNITY` (no PCR filter) traded 1,807 times for −₹237,829 net (39.3% hit rate). Adding the PCR filter cuts trade count by 65%, halves the average loss per trade, and lifts the in-sample hit rate from 39.3% to 43.5%. **The PCR filter is doing real work** — it's just not enough to flip the strategy positive net of costs.

## Forward signal vs in-sample noise

The forward window's 76.2% hit rate is striking, and zero stops triggered across 21 trades over 20 sessions. The point Sharpe of +7.22 is consistent with a low-vol April 2026 tape that favoured the strategy. But:

- The 99% CI lower bound is −2.02, so we cannot reject zero edge at the family-wise corrected α.
- 21 trades is below the ~30-trade threshold for stable per-regime statistics.
- The in-sample binomial p of 0.0012 is decisive evidence of a *negative* edge, which the forward sample is too small to overturn.

## Recommended action

Keep Phase C in the Scanner tab for informational alerts only. Do **not** auto-open as a Trading candidate.

**Two parallel actions to revisit the verdict:**

1. **Live shadow paper-trade ledger** (`live_paper.py`, F3 leg) running from today. Six months of forward live OPPORTUNITY signals (≈ 100–150 trades) will give the binomial test the sample size needed to either confirm the in-sample loss or detect a genuine forward edge. The binomial p threshold for 100 trades at 60% wins is well below 0.01.
2. **Per-(symbol, regime) dynamic stops** (currently flat 2%). The flat stop is a placeholder — `std_return` is already in the profile and could replace the constant. A follow-up plan should sweep stop multipliers `k ∈ {1.0, 1.5, 2.0, 2.5}` of `std_return` and re-run the H1 test.

## Two tickers dropped

`HDFC` (merged into HDFC Bank 2023) and `TATAMOTORS` (DVR/ordinary restructure 2025) returned zero bars from Kite and were silently skipped by `profile.py`'s empty-bars guard. The effective universe is 14, not the requested 15. Future runs should substitute `HDFCBANK` (NSE: HDFCBANK, BOM: 500180) and `TATAMOTORS-EQ`.
