# Expiry-week IV + pinning data collection — design (2026-04-30)

**Status:** PRE_REGISTERED design. Implementation pending.
**Author:** Bharat Ankaraju + Claude
**Predecessor:** none — new study, prompted by user observation 2026-04-30 ("we have to watch out what happen in the expiry week and on the expiry day").

## Motivation

Indian F&O contracts have weekly + monthly expiries that distort intraday option pricing in well-known ways:

- **Pinning:** the most-active option strike acts as a magnet for the underlying spot in the final 60-90 minutes before expiry. The "max-pain" strike often becomes the close.
- **IV crush:** option implied volatility collapses through the morning of expiry day as theta accelerates. Long-option strategies bleed; short-option strategies (writers) earn.
- **Liquidity hourglass:** order books narrow at the open of expiry day and widen back into close. Mid-day spreads in OTM strikes can be 5-10% of premium.
- **Roll-over flow:** the rollover from front to next month creates predictable order-flow distortions on the Tuesday/Wednesday before monthly expiry.

The Phase C options paired-shadow ledger (`pipeline/data/research/phase_c/live_paper_options_ledger.json`) already records ATM premium movements but does NOT tag expiry-day vs non-expiry-day separately. Without that tag, every paired-shadow conclusion conflates structural option behavior with expiry-day mechanics.

Per user directive: forward-only data collection study, separate from any trade signal.

## What this study does NOT do

- Does not modify Phase C options paired ledger or any other live ledger.
- Does not generate trade signals — pure observational data layer.
- Does not require new Kite API calls — re-uses the existing 1-min cache + ATM strike lookups already running.

## What it DOES produce

A daily JSON record per F&O underlying recording, for the 5 trading days leading into each weekly expiry (Thursday) and monthly expiry (last Thursday of month):

```json
{
  "underlying": "NIFTY",
  "date": "2026-05-08",
  "expiry_date": "2026-05-08",
  "is_expiry_day": true,
  "is_weekly_expiry": true,
  "is_monthly_expiry": false,
  "days_to_expiry": 0,
  "atm_strike_at_open": 24500,
  "atm_strike_at_1500": 24450,
  "max_pain_strike_at_open": 24500,
  "max_pain_strike_at_1500": 24450,
  "spot_at_open": 24508.30,
  "spot_at_close": 24452.10,
  "spot_at_1500": 24455.50,
  "atm_call_iv_at_open": 18.4,
  "atm_call_iv_at_1500": 12.1,
  "atm_call_iv_at_close": 11.8,
  "atm_put_iv_at_open": 17.9,
  "atm_put_iv_at_1500": 11.7,
  "atm_put_iv_at_close": 11.5,
  "atm_call_premium_at_open": 145.50,
  "atm_call_premium_at_close": 18.20,
  "atm_put_premium_at_open": 132.40,
  "atm_put_premium_at_close": 22.10,
  "spot_drift_to_max_pain_pct": -0.21,
  "iv_crush_call_pct": -35.9,
  "iv_crush_put_pct": -35.8,
  "near_chain_total_OI": 12450000,
  "next_chain_rollover_pct": 35.4
}
```

## Pre-locked design

| Lock | Value | Reason |
|---|---|---|
| Universe | NIFTY, BANKNIFTY, FINNIFTY (indices) + top 30 F&O stocks by ATM OI | covers all material expiry-flow names |
| Frequency | daily snapshot at 09:15 / 11:00 / 13:00 / 14:30 / 15:25 IST | 5 timestamps per underlying per day |
| Window | T-5 to T0 trading days for every weekly + monthly expiry | rolling, forward-only |
| Storage | `pipeline/data/research/expiry_iv_pinning/<underlying>/<expiry_date>.parquet` | one parquet per underlying-expiry |
| Source | Kite API 1-min cache + Kite option-chain endpoint (already polled by oi_scanner) | no new API calls |
| Retention | 3 years rolling | analysis window |
| Schedule | piggyback on `oi_scanner` (already runs every intraday cycle) | re-use existing infrastructure |
| Provenance | every record carries fetched_at + Kite cache file ref | per data validation policy §11 |

## Outputs (after 3 months of collection)

- `pipeline/data/research/expiry_iv_pinning/<underlying>/<expiry_date>.parquet` — raw observations
- `pipeline/data/research/expiry_iv_pinning/findings_<date>.md` — descriptive readout per underlying:
  - Mean IV crush trajectory (open → close on expiry day)
  - Distribution of spot-to-max-pain drift
  - Pinning frequency (% of expiries where spot closes within 0.25% of nearest strike)
  - Liquidity hourglass profile (ATM bid-ask spread by hour)

## What this enables (after data accumulates)

1. **Data discipline for Phase C options paired ledger:** every options trade gets tagged `is_expiry_day`, `days_to_expiry`. Expiry-day trades can be excluded from forensic-only conclusions or analyzed separately.
2. **Hypothesis seed for short-vol writer overlay:** if IV crush profile is stable, a 14:30-IST-open ATM-straddle-write in the final 30 min of expiry day has theoretical positive expectancy. Becomes a formal hypothesis (`H-YYYY-MM-DD-EXPIRY-WRITER`) AFTER data shows the crush is consistent.
3. **Pinning-aware exit timing:** if max-pain magnetism is real, mechanical TIME_STOPs on expiry day might miss the final 30 min reversion. Adjustable per-cell.

## Decision tree at end of 3-month collection window

| State | Action |
|---|---|
| Collection successful, IV crush profile stable | Promote to spec for short-vol writer overlay hypothesis |
| Collection successful, no stable pattern | Mark as null result, keep collecting at lower frequency |
| Collection broken (Kite cache gaps) | Fix cache layer first; do not promote |

## Honest expectation

3 months yields ~12 weekly expiries × 32 underlyings × 5 timestamps × 5 days = 9,600 daily records. Enough for descriptive but not for any per-strike inference. Real pattern discovery needs 12+ months of data.

## Honest risks

- **Kite cache outages.** The 1-min cache has gaps; option chain has occasional 401s. Without a watchdog audit, gaps go unnoticed.
- **OI snapshot timing variance.** Kite returns OI at the time of poll, not at clean clock boundaries. Comparable cells across days require interpolation, not raw values.
- **No theoretical Greek model fit.** This study collects observed IV; it does NOT fit a stochastic vol model. Inference is purely descriptive.
