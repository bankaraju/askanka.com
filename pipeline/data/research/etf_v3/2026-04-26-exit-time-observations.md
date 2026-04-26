# Exit-Time Observations on H-001 Mechanical Engine (preliminary, not a full sweep)

**Generated:** 2026-04-26 19:35 IST
**Universe:** 478 GATED 4σ correlation breaks over 27 trade-dates (2026-03-12 → 2026-04-23)
**Source:** `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet`
**Origin:** Task #53 — user feedback "most of our gains were on the trails... optimal exit strategy is needed than random 2.30 PM"

## Why this isn't a full sweep yet

The replay parquet records `entry_price` and `exit_price` only — to do a true exit-time sweep across {13:30, 14:00, 14:30, 15:00, 15:25}, we need each trade's minute-bar series replayed at each candidate exit. That requires the Kite minute-bar files for each ticker × date in the cohort. Spot-check: `pipeline/data/research/phase_c/minute_bars/` has only sparse coverage (a few tickers × ~15 dates in April 2026). The replay engine generated this parquet by reading from the broader Kite minute archive that's not on this machine.

What follows is **observational analysis from the existing parquet** showing where P&L accrues by hold-duration and exit-reason. It identifies the optimization target but does not execute the sweep.

## Observation 1: P&L is BIMODAL on hold time

| Hold bucket | n | avg gross bps | comment |
|---|---|---|---|
| 0-30 min | 165 | **+7.7** | Mostly Z_CROSS quick exits |
| 30-60 min | 80 | -24.5 | Loss zone begins |
| 60-90 min | 44 | -40.1 | |
| 90-120 min | 38 | -41.8 | |
| 120-150 min | 20 | -33.0 | |
| 150-180 min | 14 | -63.2 | |
| 180-210 min | 10 | -56.0 | |
| 210-240 min | 18 | -62.0 | |
| 240+ min | 89 | **+92.3** | T1_CLOSE winners |

The P&L curve is U-shaped: WIN at fast exits (≤30 min) and at long holds (≥240 min). The 30-240 min zone is a P&L trough.

## Observation 2: Exit-reason carries the bimodality

| Exit reason | n | avg gross bps | hit rate | avg hold min |
|---|---|---|---|---|
| **Z_CROSS** (mean reversion completed) | 183 | **+44.3** | 85.2% | 39 |
| SECTOR_FLIP | 133 | **-68.5** | 9.0% | 83 |
| **T1_CLOSE** (held to 14:30 / TIME_STOP) | 110 | **+72.9** | 65.5% | 309 |
| STOP | 43 | -129.5 | 0.0% | 100 |
| SKIP_NO_NEXT_DAY | 9 | -56.0 | 22.2% | 179 |

**The two winning exit types are fast Z_CROSS (+44 bps in 39 min) and held-to-close T1_CLOSE (+73 bps in 309 min).** The middle is dominated by SECTOR_FLIP losses (-69 bps).

## What this suggests

The current rule has 5 exit triggers in priority order: Z_CROSS, SECTOR_FLIP, STOP, T1_CLOSE, SKIP. The P&L geometry suggests **SECTOR_FLIP is doing harm** — it forces an exit at the worst time (after a partial pullback that hasn't reverted yet) and prevents the trade from reaching the +73 bps T1_CLOSE outcome.

A candidate rule: **DISABLE SECTOR_FLIP, let trades that don't Z_CROSS quickly run to T1_CLOSE.** Mechanically, this would convert 133 SECTOR_FLIP exits at -69 bps into either (a) Z_CROSS exits later in the day (+44 bps avg) or (b) T1_CLOSE exits (+73 bps). Estimated P&L lift if 50% become Z_CROSS and 50% become T1_CLOSE: ~+125 bps per trade × 133 trades = ~17,000 bps added P&L over the 27-day window.

But this is an estimate — actual outcome depends on what those 133 trades' prices did between SECTOR_FLIP and T+1 close. To compute true counterfactual P&L:

1. For each of the 133 SECTOR_FLIP trades, fetch the minute bars from `entry_time` through 14:30 (T1_CLOSE)
2. Recompute the trade as if SECTOR_FLIP exit was disabled
3. Apply the surviving exit triggers (Z_CROSS, STOP, T1_CLOSE) in order
4. Compute counterfactual gross_pnl_pct

This is a half-day's work once the minute bars are in hand. **Defer until Kite minute backfill** (#28 prereq) is complete or until the v3 cutover question lands.

## What this DOES tell us about 14:30 TIME_STOP

The user said "is 2:30 PM the best trade strategy?" Answer from this data: **YES, FOR THE T1_CLOSE COHORT.** Trades that survive to 14:30 return +73 bps avg with 66% hit rate. Moving the TIME_STOP earlier (e.g., to 13:30 or 14:00) would force-close more trades into the loss zone (60-180 min holds avg -45 bps).

The optimization isn't "different TIME_STOP time"; it's **"keep the 14:30 TIME_STOP, but stop killing winners with SECTOR_FLIP at 60-150 min."**

## Files

- This observation: `pipeline/data/research/etf_v3/2026-04-26-exit-time-observations.md`
- Source: `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet`
- Counterfactual code (TODO): `pipeline/autoresearch/exit_rule_sweep.py` — needs Kite minute backfill

## Open threads

- Run counterfactual SECTOR_FLIP-disabled replay on the 133 affected trades (needs minute bars)
- Investigate whether SECTOR_FLIP threshold (currently triggers when sector residual reverts past zero) could be relaxed without disabling — e.g., trigger only at SECTOR_FLIP × 1.5σ overshoot
- Verify the bimodal hold-time pattern holds out-of-window (need 30+ more trade-dates)
