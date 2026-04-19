# Synthetic Options Validation Pipeline — Design Spec

**Date:** 2026-04-19
**Status:** Approved
**Scope:** Retrospective vol model validation using 60-day OHLCV history + live ATM premium capture for ongoing comparison + research paper generation.

---

## 1. Problem Statement

Station 6.5 (Synthetic Options Engine) prices ATM straddles using EWMA volatility as an IV proxy. Before trusting its "HIGH-ALPHA SYNTHETIC" verdicts, we need evidence that:

1. The EWMA vol accurately predicts the magnitude of actual stock moves (retrospective validation)
2. The BS-priced synthetic premiums match real market premiums (live validation)

Without this proof, the Leverage Matrix is a calculator, not a validated trading tool.

## 2. Architecture

Three independent modules, each with a single responsibility:

```
vol_backtest.py          atm_premium_capture.py       generate_validation_report.py
(run once, retrospective)   (twice daily, live)           (run after backtest or on demand)
        ↓                           ↓                              ↓
vol_backtest_results.json    atm_snapshots/*.json         articles/ + docs/
        ↓                                                        
synthetic_options.py                                      
(reads vol_scalar)                                        
```

## 3. Vol Backtest Engine (`pipeline/vol_backtest.py`)

### 3.1 Purpose

Run once. Load 58 stocks of OHLCV from `pipeline/data/alpha_test_cache/`, compute rolling EWMA vol at each date, predict the expected 1-day move, compare against the actual next-day move. No lookahead bias.

### 3.2 Algorithm

```
For each stock CSV in alpha_test_cache/:
  Load OHLCV, sort by date ascending
  For each trading day t (from day 31 to day N-1):
    1. closes_window = closes[t-30 : t]  (30 trading days ending at t, exclusive of t+1)
    2. ewma_vol = compute_ewma_vol(closes_window, span=30)
    3. straddle = bs_call_price(S=close[t], K=close[t], T=1/365, sigma=ewma_vol)
              + bs_put_price(S=close[t], K=close[t], T=1/365, sigma=ewma_vol)
    4. expected_move_pct = straddle / close[t] × 100
    5. actual_move_pct = abs(close[t+1] - close[t]) / close[t] × 100
    6. Record observation
```

### 3.3 Metrics

**MAPE (Mean Absolute Percentage Error):**
`avg(|expected_move_pct - actual_move_pct| / actual_move_pct × 100)` across all observations.

**σ-band hit rate (percentile calibration):**
Daily 1σ implied move = ewma_vol / √252 × 100. Count what fraction of actual daily moves fall within ±1σ. A perfectly calibrated model yields ~68.2%.

**Vol scalar:**
OLS regression: `actual_daily_vol = α + β × ewma_daily_vol`. The scalar = β. If EWMA overestimates by 12%, β ≈ 0.88. This correction factor feeds back into Station 6.5.

**Per-stock breakdown:**
MAPE, hit rate, and vol scalar for each of the 58 stocks individually.

### 3.4 Output

`pipeline/data/vol_backtest_results.json`:

```json
{
  "run_date": "2026-04-19",
  "total_observations": 3427,
  "stocks_tested": 58,
  "data_provenance": "pipeline/data/alpha_test_cache/*.csv",
  "aggregate": {
    "mape_pct": 14.2,
    "sigma_band_hit_rate": 0.71,
    "vol_scalar": 0.88,
    "median_expected_move_pct": 1.34,
    "median_actual_move_pct": 1.18
  },
  "per_stock": [
    {
      "ticker": "HAL",
      "observations": 62,
      "mape_pct": 11.3,
      "hit_rate": 0.73,
      "vol_scalar": 0.91
    }
  ],
  "daily_samples": [
    {
      "date": "2026-02-15",
      "ticker": "HAL",
      "ewma_vol": 0.312,
      "expected_move_pct": 1.42,
      "actual_move_pct": 1.28
    }
  ]
}
```

### 3.5 Dependencies

- `pipeline.vol_engine.compute_ewma_vol` (existing)
- `pipeline.options_pricer.bs_call_price`, `bs_put_price` (existing)
- OHLCV CSVs in `pipeline/data/alpha_test_cache/` (existing, 58 stocks)

## 4. Live ATM Premium Capture (`pipeline/atm_premium_capture.py`)

### 4.1 Purpose

Run twice daily at 09:25 and 15:30 IST. Snapshot real ATM option premiums for all 213 F&O stocks via `kite.quote()`, alongside synthetic BS prices. Produces side-by-side comparison.

### 4.2 Algorithm

```
1. Load instruments_nfo.csv → filter to nearest monthly expiry for each stock
2. For each of 213 F&O stocks:
   a. Fetch spot price via kite.ltp("NSE:{ticker}")
   b. Find nearest ATM strike from available strikes
   c. Record instrument tokens for ATM call (CE) and ATM put (PE)
3. Batch kite.quote() for all ~426 instruments (≤1 API call)
4. For each stock:
   a. real_call = quote[CE].last_price
   b. real_put = quote[PE].last_price
   c. real_straddle = real_call + real_put
   d. ewma_vol = vol_engine.get_stock_vol(ticker)
   e. days_to_expiry = (expiry_date - today).days
   f. synthetic_call = bs_call_price(spot, atm_strike, days_to_expiry/365, ewma_vol)
   g. synthetic_put = bs_put_price(spot, atm_strike, days_to_expiry/365, ewma_vol)
   h. synthetic_straddle = synthetic_call + synthetic_put
   i. error_pct = (synthetic_straddle - real_straddle) / real_straddle × 100
5. Write snapshot JSON
```

### 4.3 ATM Strike Resolution

NSE stock options use standard strike intervals. For a stock at ₹4,285 with ₹50 intervals, the nearest ATM strike is ₹4,300. The resolution logic:

1. Filter `instruments_nfo.csv` for the stock's name and nearest monthly expiry
2. Extract all available strikes
3. Pick the strike closest to spot price

### 4.4 Output

`pipeline/data/atm_snapshots/YYYY-MM-DD-HHMM.json`:

```json
{
  "timestamp": "2026-04-21T09:25:00+05:30",
  "expiry": "2026-04-24",
  "days_to_expiry": 3,
  "vol_scalar_applied": 0.88,
  "stocks": [
    {
      "ticker": "HAL",
      "spot": 4285.0,
      "atm_strike": 4300,
      "real_call": 89.5,
      "real_put": 104.2,
      "real_straddle": 193.7,
      "ewma_vol": 0.312,
      "adjusted_vol": 0.274,
      "synthetic_call": 85.3,
      "synthetic_put": 100.1,
      "synthetic_straddle": 185.4,
      "error_pct": -4.3
    }
  ],
  "summary": {
    "stocks_captured": 213,
    "median_error_pct": -3.2,
    "mean_abs_error_pct": 5.1,
    "stocks_within_5pct": 178,
    "stocks_within_10pct": 201
  }
}
```

### 4.5 Scheduling

Piggybacks on existing scheduled tasks — not a new task:
- **09:25:** Called from the `AnkaOpenCapture` .bat script by appending a `python pipeline/atm_premium_capture.py` line
- **15:35:** Called from the `AnkaCloseCapture` .bat script by appending a `python pipeline/atm_premium_capture.py` line

If Kite session is stale or `kite.quote()` fails, the capture writes a partial snapshot with `"error"` entries for failed stocks rather than crashing. Stocks with missing data are excluded from the summary stats.

### 4.6 Dependencies

- `pipeline.kite_client.get_kite`, `kite.ltp()`, `kite.quote()` (existing)
- `pipeline/data/kite_cache/instruments_nfo.csv` (existing, refreshed daily)
- `pipeline.vol_engine.get_stock_vol` (existing)
- `pipeline.options_pricer.bs_call_price`, `bs_put_price` (existing)

## 5. Validation Report Generator (`pipeline/generate_validation_report.py`)

### 5.1 Purpose

Read backtest results and (optionally) live snapshots. Generate two deterministic outputs: a layman article and a technical report. No LLM calls — pure template + data.

### 5.2 Inputs

- `pipeline/data/vol_backtest_results.json` (required)
- `pipeline/data/atm_snapshots/*.json` (optional, enhances report when available)

### 5.3 Layman Article

Output: `articles/synthetic-options-validation.md`

Structure:
- **Headline:** "We Tested Our Options Model Against {N}+ Real Market Moves — Here's What We Found"
- **The Question:** Can we predict how much a stock will move using only its past prices?
- **The Method:** Plain-English explanation of vol → expected move (no formulas, no jargon)
- **The Results:** "Our model predicted daily moves within {MAPE}% accuracy across {N_stocks} stocks over {N_days} trading days"
- **What This Means:** "When the terminal shows HIGH-ALPHA SYNTHETIC, it's backed by {N_obs} data points"
- **Calibration:** Best/worst calibrated stocks, what the vol scalar correction does
- **Live Validation** (if ATM snapshots exist): "We then compared our prices against real market premiums — median error was {X}%"

### 5.4 Technical Report

Output: `docs/synthetic-options-technical-validation.md`

Structure:
- **Abstract:** One paragraph with methodology, sample size, key findings
- **1. Data Provenance:** Source = `pipeline/data/alpha_test_cache/*.csv`, {N} stocks, {date_range}, total {N_obs} observations. No survivorship bias (stocks present in cache are tested regardless of current F&O status).
- **2. Methodology:** EWMA(λ=2/31), BS(r=0, K=S, T=1/365). Rolling window, no lookahead. T+1 prediction only.
- **3. Results — Move Magnitude:**
  - Aggregate MAPE
  - σ-band calibration (expected 68.2% vs observed)
  - Distribution of errors (what fraction of days had <5%, <10%, <20% error)
- **4. Results — Per-Stock Calibration:**
  - Top 10 best-calibrated stocks (lowest MAPE)
  - Bottom 10 worst-calibrated (highest MAPE)
  - Sector patterns (if defence stocks calibrate differently than IT)
- **5. Vol Scalar Derivation:**
  - OLS regression: actual ~ β × predicted
  - Scalar value and confidence interval
  - Impact: how MAPE changes when scalar is applied (re-run with adjustment)
- **6. Live Premium Validation** (populated after 15 days of ATM snapshots):
  - Synthetic vs real premium error distribution
  - Does vol-scalar improve premium accuracy?
  - Implied vol vs EWMA vol comparison
- **7. Implications for Station 6.5:**
  - Which Leverage Matrix verdicts are trustworthy
  - Recommended confidence thresholds for NET EDGE based on model error

### 5.5 Implementation

Deterministic string templating. The generator reads the JSON, formats numbers, and writes markdown. No Gemini/Haiku calls. The article and report are reproducible — re-running with the same JSON produces identical output.

## 6. Vol Scalar Feedback Loop

### 6.1 Storage

The vol scalar lives in `vol_backtest_results.json` under `aggregate.vol_scalar`.

### 6.2 Consumption

`synthetic_options.build_leverage_matrix()` reads the scalar on each call:

```python
backtest_path = Path("pipeline/data/vol_backtest_results.json")
vol_scalar = 1.0  # default if no backtest exists
if backtest_path.exists():
    results = json.loads(backtest_path.read_text())
    vol_scalar = results.get("aggregate", {}).get("vol_scalar", 1.0)

# Apply when fetching vol for each leg:
raw_vol = vol_engine.get_stock_vol(ticker)
adjusted_vol = raw_vol * vol_scalar
```

### 6.3 UI Indication

The leverage matrix response gains a `vol_scalar_applied` field:
- `1.0` → "Vol uncalibrated" (amber badge in UI)
- `!= 1.0` → "Vol calibrated: {scalar}" (green badge)

### 6.4 Refresh Cadence

The backtest runs manually today. Can be wired into the Sunday night batch (alongside AnkaUnifiedBacktest) for weekly refresh. Not automated in this build — future enhancement.

## 7. Testing Strategy

### 7.1 Vol Backtest
- Known input: 10 synthetic price series with known volatility → verify MAPE and hit rate match expected values
- Edge cases: stock with zero variance, stock with single large gap
- Lookahead check: verify observation at date T only uses closes ≤ T

### 7.2 ATM Premium Capture
- Mock `kite.quote()` with known premiums → verify error_pct computation
- ATM strike resolution: spot=4285, strikes=[4200, 4250, 4300, 4350] → should pick 4300
- Missing data: stock with no options in instruments_nfo → skip gracefully

### 7.3 Report Generator
- Feed known backtest JSON → verify article contains correct numbers
- Empty ATM snapshots → verify "Live Validation" section says "pending"
- Verify no LLM calls, no external API calls

## 8. What This Does NOT Do

- Does not modify the existing Station 6.5 code (options_pricer, synthetic_options)
- Does not add new scheduled tasks (piggybacks on existing capture tasks)
- Does not require real options historical data (backtest uses equity OHLCV)
- Does not use LLM for report generation (deterministic templates)
- Does not execute any trades

## 9. Scheduling Impact

No new scheduled tasks. Two integration points:

| Existing Task | Integration |
|---|---|
| `AnkaOpenCapture` (09:16) | Add `atm_premium_capture.run()` as post-step |
| `AnkaCloseCapture` (15:35) | Add `atm_premium_capture.run()` as post-step |

The vol backtest and report generator are run manually or via one-off commands.
