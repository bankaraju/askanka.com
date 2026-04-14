# Daily Regime-Stock Ranker (Phase B) — Design Spec

**Date:** 2026-04-14
**Status:** Draft
**Depends on:** Phase A reverse_regime_profile.json (PASSED, 205 signals)

## What This Does

On regime transition days, reads the Phase A historical profile, ranks stocks by tradeable drift, computes current z-scores, and outputs a morning recommendation to Telegram + terminal. Fires on ANY transition — including back to NEUTRAL.

## When It Fires

- **Trigger:** Regime transition detected (today's zone != yesterday's zone)
- **Most days (77% NEUTRAL):** No signal, no output — stays quiet
- **On transition days:** Fires ranked recommendation
- **Recommendation stays active for 5 trading days**, then expires automatically

## Data Flow

```
1. Morning run (09:25 IST, alongside existing morning brief):
   - Read today's regime from ETF engine (existing regime_scanner.py or equivalent)
   - Read yesterday's regime from stored state
   - If no transition → exit silently

2. On transition detected:
   - Load reverse_regime_profile.json (Phase A output)
   - Look up transition type (e.g., "NEUTRAL→RISK-OFF")
   - Filter for tradeable signals for this transition
   - Rank by abs(drift_5d_mean) descending
   - Separate into longs (positive drift) and shorts (negative drift)

3. Current z-score (optional, if market is open):
   - For top 5 stocks, fetch current price from EODHD
   - Compare to 20-day mean: z = (price - mean_20d) / std_20d
   - Favorable entry: z < -0.5 for longs, z > 0.5 for shorts

4. Output:
   - Telegram message to @ANKASIGNALS
   - JSON for terminal dashboard
   - Log to data/regime_ranker_history.json (track record)
```

## Output Format

```
REGIME TRANSITION: {from} → {to} (detected {date})

TOP LONGS (historical drift > gap, persistent):
  1. {symbol}  {drift_5d}% drift 5d, {hit_rate}% hit, {episodes} episodes
  2. ...

TOP SHORTS:
  1. {symbol}  {drift_5d}% drift 5d, {hit_rate}% hit, {episodes} episodes
  2. ...

SPREAD: Long {best_long} / Short {best_short} = {spread}% expected, {min_hit}% min hit
Current z-score: {z}σ ({favorable/unfavorable} entry)

Confidence: {HIGH/MEDIUM/LOW} ({episodes} episodes, {regime} lasts ~{avg_duration} day avg)
Hold period: 5 trading days | Stop: 2x gap | Expires: {date+5}
```

**Confidence levels:**
- HIGH: >= 20 episodes, hit rate >= 65%
- MEDIUM: >= 10 episodes, hit rate >= 55%
- LOW: < 10 episodes or hit rate < 55%

## State Management

- `data/regime_ranker_state.json` — stores:
  - `last_zone`: yesterday's regime zone
  - `last_transition_date`: when the last transition was detected
  - `active_recommendations`: list of active recs with expiry dates
  - Updated every morning run, read on next run

## Integration Points

- **Morning brief** (`morning_brief.py`): Add regime ranker section if transition detected
- **Telegram** (`telegram_bot.py`): Send regime transition alert
- **Terminal** (`localhost:8888`): Display active recommendations in dashboard
- **Spread Intelligence Engine**: Feed as a modifier signal (not a gate)
- **EOD report**: Track whether recommendation hit target by expiry

## File Structure

```
pipeline/
  autoresearch/
    reverse_regime_ranker.py     # The daily ranker (this spec)
    reverse_regime_profile.json  # Phase A output (read-only)
    reverse_regime_analysis.py   # Phase A script (read-only)
  data/
    regime_ranker_state.json     # Persistent state
    regime_ranker_history.json   # Track record of recommendations
```

## What This Does NOT Do

- Does NOT replace the ETF regime engine (that detects the regime)
- Does NOT replace the Spread Intelligence Engine (that manages existing spreads)
- Does NOT auto-execute trades (recommendation only)
- Does NOT fire on every run — only on transition days
- Does NOT compute its own regime — reads from existing infrastructure

## Testing

- Unit test: mock transition detection with known state
- Unit test: ranking logic with sample profile data
- Unit test: z-score computation
- Unit test: output format
- Integration test: full run with real profile.json, simulated transition
- No live EODHD calls in tests (mock prices)

## Success Criteria

- Recommendation matches or outperforms static spread playbook over 2-week paper trade
- At least 1 transition detected per week (historically ~5 transitions/week from 266 in 717 days)
- Track record JSON accumulates data for later Phase C analysis
