# Phase C — Strategy Description

## What Phase C is

Phase C is the **intraday correlation-break** layer of the reverse-regime engine. Given:

- **Phase A profile:** for every (symbol, regime) pair, the empirical mean and standard deviation of next-day returns, trained on a rolling 2-year window.
- **Phase B regime:** today's active regime (one of `BROAD_RISK_ON`, `CONTRACTION`, `NEUTRAL`, `DEFENSIVE`, `BROAD_RISK_OFF`), chosen by the ETF-regime engine each morning.
- **Intraday return:** the stock's actual return so far today.

Phase C computes a **z-score of surprise**

    z = (actual_return - expected_return) / std_return

and crosses it with a small grid of derivatives-market agreement signals (PCR direction, open-interest anomaly flag) to classify the stock into one of five labels.

## Canonical logic

The live logic lives in `pipeline/autoresearch/reverse_regime_breaks.py`. This backtest re-implements the same decision matrix in `pipeline/research/phase_c_backtest/classifier.py` to isolate it from upstream live dependencies; `test_classifier.py` pins the matrix against hand-computed cases so drift is caught in CI.

## The five labels

| label | trigger | action |
|---|---|---|
| `OPPORTUNITY` | z-score opposite direction **and** PCR agrees with the reversion bet | enter |
| `POSSIBLE_OPPORTUNITY` | z-score opposite direction, PCR silent or missing | watch / enter degraded |
| `UNCERTAIN` | signals conflict | ignore |
| `WARNING` | z-score lagging (same direction, weaker) **and** OI anomaly | hold / reduce |
| `CONFIRMED_WARNING` | z-score opposite direction **and** OI anomaly against the bet | exit / flip |

The two *OPPORTUNITY* variants are structurally different: the full label requires PCR agreement; the *possible* label tolerates missing PCR data. Because historical PCR/OI snapshots are not archived for this universe, the backtest can only ever produce `POSSIBLE_OPPORTUNITY`, which is definitionally equivalent to the **degraded** ablation variant (`ablation.py::run_all_variants`).

## Trading rule under test

The user's hypothesis is that Phase C signals have their strongest edge as an **intraday-only** trade:

1. **Entry:** at the bar immediately following the signal time (open 09:30 IST in the in-sample EOD surrogate; true signal time in the 1-min intraday forward leg).
2. **Direction:** `LONG` if expected return ≥ 0, `SHORT` otherwise.
3. **Exit:** whichever of these fires first —
   - **Stop:** −2% adverse excursion from entry (fractional).
   - **Target:** +1% favourable excursion from entry (fractional).
   - **Time stop:** 14:30 IST mechanical close (two hours before the session close, leaving a liquidity buffer).
4. **No overnight holds.** Any open position at 14:30 is flattened at that bar's close.

The 2-to-1 stop-to-target asymmetry is intentional: the bet is that reversion moves fast and fails slowly, so wide stops capture slow fails while tight targets lock in the fast moves. This is the same shape the live engine's paper ledger runs.

## Universe

- **Scope:** NSE F&O single-stock underlyings, pulled from the monthly `fo_mktlots.csv` archive (`universe.py`).
- **Point-in-time:** the universe is queried per trade month, not the current snapshot, so stocks that exited F&O mid-window are not back-included.
- **Delisted / merged tickers:** symbols that return zero bars from Kite (e.g. HDFC post-merger) are silently skipped by `profile.train_profile`.

## Costs

- **Slippage:** 5 bps one-way (10 bps round-trip) — retail equity-intraday benchmark.
- **Brokerage:** Zerodha flat ₹20 / order + 0.03% STT + exchange tx — captured in `cost_model.apply_to_pnl`.
- **Notional:** ₹50,000 per trade (single-lot retail ticket), applied uniformly across all backtest variants.

## What is deliberately excluded

- **Options.** Phase C drives cash-equity intraday entries. Options sizing and greeks belong to the downstream synthetic-options engine.
- **Position sizing by Phase B rank.** The backtest caps per-day entries at `top_n=5` ordered by |z-score|, but does not vary notional by Phase B confidence. A follow-up plan can layer this in.
- **Stop tightening around events.** No earnings blackout, no ex-div exclusion. The universe is held constant across event windows to keep the trade count honest.
