# Correlation Break Detector (Phase C) — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Depends on:** Phase A (reverse_regime_profile.json), Phase B (reverse_regime_ranker.py), OI Scanner (oi_scanner.py)

## What This Does

Detects stocks deviating from their expected regime behavior intraday, cross-references with options data (PCR + OI anomalies), classifies the break as opportunity or warning, and outputs an action recommendation. Runs every 15 minutes during market hours.

Operates independently from Phase B but cross-references active Phase B recommendations when a break is detected on a recommended stock.

## When It Fires

- **Schedule:** Every 15 min, 09:30-15:30 IST (market hours)
- **Condition:** Only checks stocks that have tradeable signals in Phase A profile for the CURRENT regime
- **Alert threshold:** Actual return deviates > 1.5σ from expected
- **Quiet when no breaks** — most runs produce no output

## Detection Logic

```
For each stock with a Phase A signal for current regime:
  expected_return = drift_1d_mean (from profile)
  expected_std = drift_5d_std / sqrt(5)  (approximate daily σ)
  actual_return = (current_price / today_open - 1) * 100

  deviation = actual_return - expected_return
  z_score = deviation / expected_std

  if abs(z_score) > 1.5:
    → CORRELATION BREAK detected
```

## OI Cross-Reference

On break detection, read the latest OI data for that stock:

- `classify_pcr(pcr)` → BULLISH / MILD_BULL / NEUTRAL / MILD_BEAR / BEARISH
- `detect_oi_anomaly(oi_change, avg)` → True/False
- If OI anomaly, classify as PUT_SURGE or CALL_SURGE based on which side changed

## Break Classification + Action

| Price vs Expected | PCR Direction | OI Anomaly | Classification | Action |
|-------------------|--------------|------------|----------------|--------|
| Lagging (near zero, expected significant) | Agrees with expected | No anomaly | OPPORTUNITY | ADD — standalone directional trade |
| Lagging | Neutral | No anomaly | POSSIBLE_OPPORTUNITY | HOLD — no OI confirmation |
| Lagging | Disagrees with expected | Any anomaly | WARNING | REDUCE existing exposure |
| Moving opposite | Agrees with BREAK direction | Anomaly confirms | CONFIRMED_WARNING | EXIT if in Phase B position |
| Moving opposite | Disagrees with break | No anomaly | UNCERTAIN | HOLD — conflicting signals |

## Action: ADD as Standalone Directional Trade

When classification is OPPORTUNITY and action is ADD:
- This is NOT an addition to an existing spread leg
- It is an independent directional trade with its own risk parameters
- Entry: current market price
- Stop: 1.5x the expected daily σ (tighter than spread stops)
- Target: drift_5d_mean from Phase A profile
- Hold: 3 trading days (shorter than spread's 5 days — it's a catch-up trade)
- Size: Rs 50K (half of standard spread leg)

## Output Format

### Telegram Alert (per break)

```
⚠️ CORRELATION BREAK: {symbol}
Regime: {current_regime} (day {n})
Expected: {expected:+.1f}% | Actual: {actual:+.1f}% | Z-score: {z:.1f}σ
Classification: {OPPORTUNITY|WARNING|CONFIRMED_WARNING|UNCERTAIN}

Options context:
  PCR: {pcr:.2f} ({pcr_class}) | OI: {anomaly_desc}
  Reading: {one_line_interpretation}

Action: {ADD|HOLD|REDUCE|EXIT}
{if ADD: "→ Standalone LONG/SHORT {symbol} @ market, stop {stop}, target {target}, 3d hold"}
{if Phase B active: "Phase B: {direction} {symbol}, entry {date}, expires {expiry}"}
```

### Terminal Dashboard

- Live indicator next to each stock showing break status
- Color coding: green (OPPORTUNITY), yellow (UNCERTAIN/HOLD), red (WARNING/EXIT)

## Data Flow

```
Every 15 min:
  1. Read current regime from ranker state (regime_ranker_state.json)
  2. Load Phase A profile (reverse_regime_profile.json)
  3. Filter stocks with signals for current regime
  4. Fetch current prices (EODHD realtime or Kite)
  5. Compute deviation for each stock
  6. For breaks (|z| > 1.5):
     a. Read latest OI data (positioning.json from oi_scanner)
     b. Classify break + determine action
     c. Check Phase B active recommendations
     d. Send Telegram alert
     e. Log to history
```

## State + History

- `data/correlation_breaks.json` — current session's breaks (overwritten each day)
- `data/correlation_break_history.json` — append-only log for track record
- Each entry: date, time, symbol, regime, expected, actual, z_score, classification, action, pcr, oi_anomaly

## Integration Points

- **OI Scanner** (`oi_scanner.py`): reads `data/positioning.json` for latest PCR and OI anomaly flags
- **Phase B Ranker** (`reverse_regime_ranker.py`): reads `data/regime_ranker_state.json` for current regime and active recommendations
- **Phase A Profile** (`reverse_regime_profile.json`): expected returns per stock per regime
- **Telegram** (`telegram_bot.py`): `send_message()` for alerts
- **EODHD** (`eodhd_client.py`): `fetch_realtime()` for current prices

## File Structure

```
pipeline/
  autoresearch/
    reverse_regime_breaks.py       # This module
    reverse_regime_profile.json    # Phase A (read-only)
    reverse_regime_ranker.py       # Phase B (read state)
    reverse_regime_analysis.py     # Phase A (read-only)
    tests/
      test_reverse_breaks.py       # Tests
  oi_scanner.py                    # OI data (read positioning.json)
  data/
    positioning.json               # Latest OI scan output
    regime_ranker_state.json       # Current regime + active recs
    correlation_breaks.json        # Today's breaks
    correlation_break_history.json # All-time break log
```

## What This Does NOT Do

- Does NOT modify spread positions (spreads stay balanced)
- Does NOT auto-execute trades (recommendation only)
- Does NOT replace Phase B (runs alongside, cross-references)
- Does NOT run outside market hours
- Does NOT compute its own regime (reads from Phase B state)
- Does NOT run its own OI scan (reads from existing oi_scanner output)

## Testing

- Unit test: deviation calculation with known expected/actual
- Unit test: classification matrix (all 5 scenarios from table above)
- Unit test: action determination
- Unit test: Phase B cross-reference (active rec found vs not found)
- Unit test: output formatting
- All tests use mock data — no live API calls

## Success Criteria

- At least 3 correlation breaks detected per month
- ADD recommendations that outperform random entry by 1%+ over 3-day hold
- Zero false actions on WARNING/EXIT (verified by next-day price movement)
