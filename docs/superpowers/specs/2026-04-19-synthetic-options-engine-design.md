# Synthetic Options Engine — "Station 6.5" Design Spec

**Date:** 2026-04-19
**Status:** Approved
**Scope:** Enrichment layer that evaluates whether high-conviction spread signals would be profitable as long options trades, using synthetic pricing from existing OHLCV data.

---

## 1. Problem Statement

The pipeline generates spread signals with conviction scoring. When conviction is high (65+), the operator wants to know: "Would buying ATM calls on the long leg and ATM puts on the short leg capture more alpha than futures, after accounting for theta decay and transaction costs?"

Today there is no way to answer this. The system has no volatility model, no options pricing, and no framework to compare "drift vs rent."

## 2. Architecture

Station 6.5 sits between signal generation (Station 6) and shadow P&L (Station 7). It reads existing data, computes synthetic options metrics, and enriches the research digest. It does not modify upstream signal logic or downstream P&L tracking.

Three modules in a layered architecture:

```
vol_engine.py  →  options_pricer.py  →  synthetic_options.py
(data + vol)      (pure math)           (orchestrator + matrix)
        ↓                                       ↓
  vol_cache/                          /api/research/digest
                                      /api/research/options-shadow
                                              ↓
                                    Intelligence → Options sub-tab
```

## 3. Vol Engine (`pipeline/vol_engine.py`)

### 3.1 Responsibilities
- Fetch 30 trading days of OHLCV from Kite historical API
- Cache per-ticker in `pipeline/data/vol_cache/{TICKER}.json`
- Compute EWMA volatility (annualised) from log-returns

### 3.2 Functions

**`fetch_and_cache_ohlcv(ticker: str, days: int = 30) → list[dict]`**
- Calls Kite historical candles API for `days` trading days
- Writes to `pipeline/data/vol_cache/{TICKER}.json`
- Cache expires after 1 trading day (checked via `fetched_at` timestamp)
- Returns list of `{date, open, high, low, close, volume}`

**`compute_ewma_vol(closes: list[float], span: int = 30) → float`**
- Computes log-returns: `ln(close[i] / close[i-1])`
- Applies EWMA with decay factor `λ = 2 / (span + 1)`
- Annualises: `σ_annual = σ_daily × √252`
- Returns annualised volatility as a float (e.g., 0.284 = 28.4%)

**`get_stock_vol(ticker: str) → float | None`**
- Orchestrator: checks cache freshness → fetches if stale → computes EWMA
- Returns `None` if Kite is unavailable (caller handles gracefully)

### 3.3 Cache Format

```json
{
  "ticker": "RELIANCE",
  "fetched_at": "2026-04-19T09:25:00+05:30",
  "ewma_vol_annual": 0.284,
  "closes": [2420.5, 2435.1, 2418.3, ...],
  "log_returns": [0.006, -0.007, ...]
}
```

Raw closes are stored alongside computed vol so recomputation with a different span does not require re-fetching.

### 3.4 Data Source

Kite API via `pipeline/kite_helper.py` (already authenticated daily at 09:00 via AnkaRefreshKite). No yfinance fallback — if Kite is down, the leverage matrix shows `grounding_ok: false`.

## 4. Options Pricer (`pipeline/options_pricer.py`)

### 4.1 Responsibilities

Pure Black-Scholes math. No I/O, no side effects. All functions take numbers and return numbers.

### 4.2 Constants

```python
FRICTION_RATE = 0.02    # 2% on premium (pessimistic, covers slippage + STT + brokerage)
RISK_FREE_RATE = 0.0    # negligible for ATM short-horizon contracts
```

### 4.3 Functions

**`bs_call_price(S, K, T, sigma, r=0.0) → float`**
Standard Black-Scholes call price. S=spot, K=strike, T=time in years, sigma=annual vol.

**`bs_put_price(S, K, T, sigma, r=0.0) → float`**
Standard Black-Scholes put price.

**`bs_greeks(S, K, T, sigma, r=0.0) → dict`**
Returns `{delta, gamma, theta_daily, vega}`. `theta_daily = theta_annual / 365`.

**`atm_option_cost(spot, vol, days_to_expiry) → dict`**
Convenience function. Sets K=S (ATM), T=days/365. Returns:
```python
{
    "call_price": float,
    "put_price": float,
    "call_theta_daily": float,
    "put_theta_daily": float,
    "call_delta": float,
    "put_delta": float,
    "combined_daily_theta": float   # call_theta + put_theta
}
```

**`five_day_rent(spot, vol, days_to_expiry) → dict`**
The core "Drift vs Rent" calculation. Returns:
```python
{
    "premium_pct": float,           # (call + put) / spot × 100
    "theta_decay_5d_pct": float,    # combined_daily_theta × 5 / spot × 100
    "friction_pct": float,          # premium_pct × FRICTION_RATE
    "total_rent_pct": float         # theta_decay_5d_pct + friction_pct
}
```

### 4.4 Expiry Tiers

| Tier | `days_to_expiry` | Purpose |
|---|---|---|
| 1-Month | 30 | Strategic: captures 5-10 day drift with minimal decay |
| 15-Day | 15 | Tactical: higher gamma, faster decay |
| Same-Day | 1 | Gamma play: expiry/correlation break scenarios |

## 5. Synthetic Options Orchestrator (`pipeline/synthetic_options.py`)

### 5.1 Responsibilities

Wires vol engine + pricer + regime data into the leverage matrix. Produces the data structure consumed by the API and UI.

### 5.2 Functions

**`build_leverage_matrix(signal: dict, regime_profiles: dict) → dict`**
- Input: one signal from `open_signals.json`, regime profiles from `reverse_regime_profile.json`
- For each ticker (long + short legs): fetch vol via `vol_engine.get_stock_vol()`
- If any vol is unavailable: return `{grounding_ok: false, reason: "vol unavailable for {ticker}"}`
- Compute weighted average vol for long side and short side
- Pull expected drift: `regime_profiles[ticker]["summary"]["avg_drift_5d"]`
- For each tier (30d, 15d, 1d): compute rent via `pricer.five_day_rent()`, compare against drift
- Classify each tier and generate caution badges
- Return leverage matrix (schema in §5.4)

**`classify_tier(net_edge: float, tier_name: str) → str`**
- `net_edge > 0` and `tier != "same_day"`: `"HIGH-ALPHA SYNTHETIC"`
- `net_edge > 0` and `tier == "same_day"`: `"EXPERIMENTAL"`
- `net_edge <= 0`: `"NEGATIVE CARRY"`

**`build_caution_badges(matrix: dict, oi_data: dict | None) → list[str]`**
- `"NEGATIVE_CARRY"`: any non-experimental tier has net_edge <= 0
- `"LOW_CONVICTION_GAMMA"`: same-day tier present but no OI/PCR anomaly in `positioning.json`
- `"DRIFT_EXCEEDS_RENT"` (positive): 1-month net_edge > 1.5%

### 5.3 Conviction Gate

All signals with conviction score >= 65 are evaluated. The leverage matrix itself filters via Drift vs Rent — no separate 80+ threshold. This maximises forward-test data while the math prevents bad trades.

### 5.4 Leverage Matrix Schema

Each item in the `leverage_matrices` array (§6.1) uses this schema:

```json
{
    "signal_id": "SIG-2026-04-15-015-Defence_vs_IT",
    "spread_name": "Defence vs IT",
    "conviction_score": 68,
    "grounding_ok": true,
    "tiers": [
      {
        "horizon": "1_month",
        "days_to_expiry": 30,
        "premium_cost_pct": 4.2,
        "five_day_theta_pct": 0.7,
        "friction_pct": 0.084,
        "total_rent_pct": 0.784,
        "expected_drift_pct": 1.39,
        "net_edge_pct": 0.606,
        "classification": "HIGH-ALPHA SYNTHETIC",
        "experimental": false
      },
      {
        "horizon": "15_day",
        "days_to_expiry": 15,
        "premium_cost_pct": 2.9,
        "five_day_theta_pct": 1.4,
        "friction_pct": 0.058,
        "total_rent_pct": 1.458,
        "expected_drift_pct": 1.39,
        "net_edge_pct": -0.068,
        "classification": "NEGATIVE CARRY",
        "experimental": false
      },
      {
        "horizon": "same_day",
        "days_to_expiry": 1,
        "premium_cost_pct": 0.8,
        "five_day_theta_pct": 0.8,
        "friction_pct": 0.016,
        "total_rent_pct": 0.816,
        "expected_drift_pct": 1.39,
        "net_edge_pct": 0.574,
        "classification": "EXPERIMENTAL",
        "experimental": true
      }
    ],
    "caution_badges": ["LOW_CONVICTION_GAMMA"],
    "long_side_vol": 0.312,
    "short_side_vol": 0.228
}
```

## 6. API Integration

### 6.1 Modified Endpoint

**`GET /api/research/digest`** — existing response gains one additive key:

```json
{
  "regime_thesis": { ... },
  "spread_theses": [ ... ],
  "correlation_breaks": [ ... ],
  "backtest_validation": [ ... ],
  "leverage_matrices": [ ... ]
}
```

Logic: after building the existing digest, loop through `spread_theses` where `score >= 65`. For each, call `build_leverage_matrix()`. If vol cache is stale or Kite is down, the matrix entry has `grounding_ok: false`.

No changes to the existing response keys. Additive only — existing consumers unaffected.

### 6.2 New Endpoint

**`GET /api/research/options-shadow`** — returns contents of `synthetic_options_shadow.json`.

Read-only, same pattern as `/api/signals`. Returns `[]` if the file doesn't exist yet.

## 7. Forward Test Recording

### 7.1 File

`pipeline/data/signals/synthetic_options_shadow.json`

### 7.2 When Recorded

Every time `run_signals.py` emits a signal with conviction >= 65, the orchestrator computes the leverage matrix. If any non-experimental tier shows positive net edge, a shadow entry is written.

### 7.3 Schema

```json
{
  "shadow_id": "OPT-2026-04-19-001-Defence_vs_IT",
  "signal_id": "SIG-2026-04-19-015-Defence_vs_IT",
  "entry_timestamp": "2026-04-19T09:25:00+05:30",
  "spread_name": "Defence vs IT",
  "regime_at_entry": "EUPHORIA",
  "conviction_score": 68,
  "entry_spot_long": 4284.8,
  "entry_spot_short": 2572.0,
  "long_side_vol": 0.312,
  "short_side_vol": 0.228,
  "tiers_at_entry": [
    {
      "horizon": "1_month",
      "premium_cost_pct": 4.2,
      "total_rent_pct": 0.784,
      "expected_drift_pct": 1.39,
      "net_edge_pct": 0.606
    },
    {
      "horizon": "15_day",
      "premium_cost_pct": 2.9,
      "total_rent_pct": 1.458,
      "expected_drift_pct": 1.39,
      "net_edge_pct": -0.068
    }
  ],
  "daily_marks": [
    {
      "date": "2026-04-19",
      "day": 0,
      "long_price": 4284.8,
      "short_price": 2572.0,
      "spread_move_pct": 0.0,
      "repriced_1m_pnl_pct": 0.0,
      "repriced_15d_pnl_pct": 0.0,
      "cumulative_theta_1m": 0.0,
      "cumulative_theta_15d": 0.0
    }
  ],
  "status": "OPEN",
  "exit_reason": null,
  "final_pnl_futures_pct": null,
  "final_pnl_1m_options_pct": null,
  "final_pnl_15d_options_pct": null
}
```

### 7.4 Daily Mark-to-Market

During each intraday scan, the system BS-reprices the synthetic options using current spot price and remaining days to expiry. `repriced_1m_pnl_pct` = (new option value − entry premium) / spot − friction. Friction is applied twice: 2% on entry premium (recorded at open) and 2% on current repriced value (estimated exit cost). This ensures the forward test reflects realistic round-trip costs.

### 7.5 Exit

When the linked signal closes (stop/target/expiry in main shadow P&L), the synthetic shadow entry closes too. Final P&L is recorded for both futures and options tracks, enabling direct comparison.

### 7.6 Same-Day Tier

Not tracked in forward test (experimental display-only per design decision). Only 1-month and 15-day tiers are shadow-tracked.

## 8. Terminal UI

### 8.1 Placement

New sub-tab **"Options"** under the existing **Intelligence** tab. Follows the sub-tab pattern from `pages/trading.js` (Signals / Scanner sub-tabs).

### 8.2 Layout

**Header Row:**
- Title: "Synthetic Options — Drift vs Rent"
- Staleness badge: amber if vol cache > 1 day old (same pattern as regime banner)

**Leverage Matrix Cards** (one per qualifying spread):
- Card header: spread name + conviction score badge (reuses existing `signal_badges.py` styling)
- 3-row grid inside card:

| Tier | Premium | 5d Rent | Expected Drift | Net Edge | Verdict |
|---|---|---|---|---|---|
| 1-Month | 4.2% | 0.78% | 1.39% | +0.61% | `HIGH-ALPHA` (green) |
| 15-Day | 2.9% | 1.46% | 1.39% | -0.07% | `NEG CARRY` (red) |
| Same-Day | 0.8% | 0.82% | 1.39% | +0.57% | `EXPERIMENTAL` (amber) |

- Caution badges below the grid using existing badge CSS (`--accent-amber`, `--accent-red`)

**Forward Test Strip** (below the matrix cards):
- Table of open synthetic shadow trades
- Columns: spread, entry date, days held, futures P&L, 1M-options P&L, 15D-options P&L
- Green/red colouring on P&L cells
- Source: `/api/research/options-shadow`
- Each ticker in the strip is clickable (see §8.3)

### 8.3 Contextual Right Panel Wiring

Each ticker in the forward test strip (long and short legs) uses the same `data-ticker` attribute and `setActiveTicker(ticker)` function from the shared ticker state architecture (built for Scanner).

Clicking a ticker opens the existing right panel showing:
- Trust score card (grade, thesis, opus side)
- Latest TA pattern badges
- OI/PCR positioning
- News intelligence hits
- Chart (Lightweight Charts widget)

**One addition to the panel for Options context:** A "Synthetic Vol" block below existing sections:
- EWMA 30d vol (annualised %)
- Current ATR (14-period)
- Vol vs drift ratio (is vol expanding or compressing relative to expected drift?)

No new panel code beyond the vol block — the Options sub-tab participates in the existing `activeTicker` event bus.

### 8.4 New Files

- `pipeline/terminal/static/js/components/leverage-matrix.js` — matrix card component
- Modified: `pipeline/terminal/static/js/pages/intelligence.js` — sub-tab routing

### 8.5 Styling

No new CSS file. Reuses existing design system variables: `--accent-green`, `--accent-amber`, `--accent-red`, `--bg-card`, existing grid patterns.

## 9. Testing Strategy

### 9.1 Vol Engine
- EWMA computation against known values (compare with pandas ewm)
- Cache freshness logic (stale vs fresh)
- Kite failure returns None gracefully

### 9.2 Options Pricer
- BS prices against known analytical values (e.g., S=100, K=100, T=30/365, σ=0.30 → known call price)
- Greeks sign checks (call delta > 0, put delta < 0, theta < 0)
- `five_day_rent` returns all components summing correctly
- Edge cases: T near zero, very low/high vol

### 9.3 Orchestrator
- Matrix built correctly from mock signal + profiles
- Classification logic (positive edge → HIGH-ALPHA, negative → NEGATIVE CARRY, same-day → EXPERIMENTAL)
- Caution badge generation
- `grounding_ok: false` when vol unavailable

### 9.4 API
- `/api/research/digest` returns `leverage_matrices` for 65+ signals only
- Existing digest fields unchanged (regression check)
- `/api/research/options-shadow` returns empty list when no file exists

### 9.5 Forward Test
- Shadow entry created when positive net edge exists
- Shadow entry NOT created when all tiers are negative carry
- Exit syncs with main signal closure
- Daily marks update correctly

## 10. What This Does NOT Do

- Does not execute live options trades
- Does not modify signal generation or conviction scoring
- Does not change the existing shadow P&L format
- Does not require a live options data feed
- Does not track same-day tier in forward test
- Does not add new scheduled tasks (runs inline with existing signal pipeline)

## 11. Dependencies

- `pipeline/kite_helper.py` — Kite historical candles API (existing)
- `pipeline/autoresearch/reverse_regime_profile.json` — expected drift data (existing)
- `pipeline/data/signals/open_signals.json` — active signals (existing)
- `pipeline/terminal/api/research.py` — research digest endpoint (modified)
- `pipeline/terminal/static/js/pages/intelligence.js` — Intelligence page (modified)
- Shared ticker state / right panel (existing from Scanner build)

## 12. Operational Notes

- No new scheduled tasks. The engine runs inline when `run_signals.py` fires (every 15 min during market hours)
- Vol cache is lightweight (~2KB per ticker). For 213 stocks: ~426KB total
- BS computation is sub-millisecond per ticker. No performance concern
- If Kite session is stale, the leverage matrix gracefully degrades to `grounding_ok: false` rather than blocking signals
