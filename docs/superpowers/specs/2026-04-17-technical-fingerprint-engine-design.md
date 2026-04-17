# Technical Fingerprint Engine — Design Spec

> **Status:** Approved 2026-04-17
> **Goal:** Build a per-stock technical analysis fingerprinting system that backtests 15 pattern types across 5 years of daily OHLCV for all 213 F&O stocks, produces a "fingerprint card" per stock showing which patterns are statistically significant, and runs a daily scanner that alerts when a stock approaches one of its proven patterns.

## Context

The pipeline currently has a thin TA layer: RSI(14) + SMA(20/50) on 24 spread-pair stocks only. No Bollinger Bands, MACD, EMA, ATR, candlestick patterns, or breakout detection anywhere. The `pipeline/data/fno_historical/` directory has 269 days of OHLCV for 213 stocks — insufficient for fingerprinting (need 5 years for 15-20 occurrences per pattern).

EODHD API (already have key) provides 5+ years of daily OHLCV for any NSE stock in a single API call.

## Use Cases

1. **Pattern proximity alerts** — "HAL is 2% from its 200 DMA which has historically been a buy zone: 72% win rate, 18 occurrences" → directional conviction for single-stock trades or Phase C break ADD positions
2. **Conviction overlay** — "The long leg of your spread just entered a Bollinger squeeze that historically resolves upward for this stock" → hold/add confidence
3. **Investor-facing fingerprint cards** — "Here's HAL's technical personality: momentum breakout stock, best pattern is Bollinger squeeze with 2.8% avg 5-day return"

## Architecture

```
EODHD 5yr OHLCV (one-time fetch, daily append)
         │
    ┌────┴────┐
    │  Data   │  pipeline/ta_data_fetcher.py
    │  Layer  │  → pipeline/data/ta_historical/{symbol}.csv
    └────┬────┘
         │
    ┌────┴────┐
    │Indicator│  pipeline/ta_indicators.py
    │ Library │  Pure math: BB, MACD, RSI, EMA, ATR, candles
    └────┬────┘
         │
    ┌────┴────┐
    │ Pattern │  pipeline/ta_pattern_detector.py
    │Detector │  Events: BB_SQUEEZE, DMA200_CROSS_UP, etc.
    └────┬────┘
         │
    ┌────┴────┐
    │Backtest │  pipeline/ta_backtester.py
    │ Engine  │  1/3/5/10 day forward returns per event
    └────┬────┘
         │
    ┌────┴────┐
    │Fingerpr.│  pipeline/ta_fingerprint.py
    │  Card   │  → pipeline/data/ta_fingerprints/{symbol}.json
    └────┬────┘
         │
    ┌────┴────┐
    │  Daily  │  pipeline/ta_daily_scanner.py
    │ Scanner │  15:30 IST scheduled task → alerts
    └─────────┘
```

## Components

### 1. Data Fetcher

**File:** `pipeline/ta_data_fetcher.py`

**Purpose:** Fetch 5 years of daily OHLCV for all 213 F&O stocks from EODHD.

**Approach:**
- EODHD endpoint: `GET /eod/{symbol}.NSE?api_token=KEY&fmt=json&from=2021-04-17&to=2026-04-17`
- Returns ~1250 rows per stock (5 years of trading days)
- Cache to `pipeline/data/ta_historical/{symbol}.csv` with columns: Date, Open, High, Low, Close, Volume
- Bootstrap: fetch all 213 in one batch (~45 seconds at 5 req/sec)
- Daily append: only fetch new days since last cached date
- Rate limit: 5 req/sec (EODHD paid tier)

**Output:** CSV per stock, ~1250 rows, 6 columns.

### 2. Indicator Library

**File:** `pipeline/ta_indicators.py`

**Purpose:** Pure math functions. No I/O, no side effects. Takes OHLCV DataFrame, returns indicator values.

**Functions:**

| Function | Signature | Output |
|----------|-----------|--------|
| `sma` | `sma(series: Series, period: int) -> Series` | Simple moving average |
| `ema` | `ema(series: Series, period: int) -> Series` | Exponential moving average |
| `bollinger` | `bollinger(df: DataFrame, period=20, std=2) -> DataFrame` | upper, middle, lower, bandwidth, pct_b |
| `macd` | `macd(df: DataFrame, fast=12, slow=26, signal=9) -> DataFrame` | macd_line, signal_line, histogram |
| `rsi` | `rsi(df: DataFrame, period=14) -> Series` | RSI using Wilder's smoothing (not simple average) |
| `atr` | `atr(df: DataFrame, period=14) -> Series` | Average True Range |
| `volume_spike` | `volume_spike(df: DataFrame, lookback=20, threshold=2.0) -> Series` | Boolean: volume > threshold × lookback-period average |
| `detect_candles` | `detect_candles(df: DataFrame) -> DataFrame` | Boolean columns: doji, hammer, shooting_star, engulfing_bull, engulfing_bear |

**Candlestick pattern definitions:**
- **Doji:** abs(open - close) / (high - low) < 0.1 AND (high - low) > 0
- **Hammer:** Lower shadow ≥ 2× body, upper shadow ≤ 0.3× body, appears after 3+ down days
- **Shooting star:** Upper shadow ≥ 2× body, lower shadow ≤ 0.3× body, appears after 3+ up days
- **Bullish engulfing:** Today's body fully engulfs yesterday's body, today green, yesterday red
- **Bearish engulfing:** Today's body fully engulfs yesterday's body, today red, yesterday green

**Wilder's RSI formula:**
```
avg_gain = ema(gains, period) using Wilder's smoothing factor (1/period)
avg_loss = ema(losses, period) using Wilder's smoothing factor (1/period)
RS = avg_gain / avg_loss
RSI = 100 - (100 / (1 + RS))
```

### 3. Pattern Event Detector

**File:** `pipeline/ta_pattern_detector.py`

**Purpose:** Scan indicator output for actionable pattern events. Returns a list of events with date, pattern type, and context.

**Pattern definitions:**

| ID | Pattern | Trigger | Direction |
|----|---------|---------|-----------|
| `BB_SQUEEZE` | Bandwidth drops below its 20-day low then expands next day | LONG |
| `BB_BREAKOUT_UP` | Close > upper band AND volume_spike | LONG |
| `BB_BREAKOUT_DN` | Close < lower band AND volume_spike | SHORT |
| `DMA200_CROSS_UP` | Close crosses above EMA(200) | LONG |
| `DMA200_CROSS_DN` | Close crosses below EMA(200) | SHORT |
| `MACD_CROSS_UP` | MACD line crosses above signal line (from below) | LONG |
| `MACD_CROSS_DN` | MACD line crosses below signal line (from above) | SHORT |
| `RSI_OVERSOLD_BOUNCE` | RSI drops below 30 then crosses back above 30 | LONG |
| `RSI_OVERBOUGHT_REV` | RSI rises above 70 then crosses back below 70 | SHORT |
| `VOL_BREAKOUT` | volume_spike AND close > max(close, 20 days) | LONG |
| `ATR_COMPRESSION` | ATR(14) < 0.5 × SMA(ATR(14), 50) | NEUTRAL (pre-move) |
| `CANDLE_HAMMER` | Hammer pattern within 2% of SMA(20) or SMA(50) or SMA(200) | LONG |
| `CANDLE_ENGULF_BULL` | Bullish engulfing after 3+ consecutive red candles | LONG |
| `CANDLE_ENGULF_BEAR` | Bearish engulfing after 3+ consecutive green candles | SHORT |
| `CANDLE_DOJI` | Doji within 1% of a 20-day high or 20-day low | NEUTRAL |

**Event output format:**
```python
{
    "date": "2025-08-15",
    "pattern": "BB_SQUEEZE",
    "direction": "LONG",
    "price_at_event": 4250.0,
    "indicator_snapshot": {
        "bb_bandwidth": 0.032,
        "rsi": 52.3,
        "volume_ratio": 1.1
    }
}
```

### 4. Backtest Engine

**File:** `pipeline/ta_backtester.py`

**Purpose:** Measure forward returns after every detected event across 5 years.

**For each event:**
- Compute 1-day, 3-day, 5-day, 10-day forward returns from the close on event date
- Win = positive return for LONG patterns, negative return for SHORT patterns
- For NEUTRAL patterns (ATR_COMPRESSION, DOJI): measure absolute move magnitude

**Output per stock per pattern:**
```python
{
    "pattern": "BB_SQUEEZE",
    "direction": "LONG",
    "occurrences": 18,
    "win_rate_1d": 0.61,
    "win_rate_3d": 0.67,
    "win_rate_5d": 0.72,
    "win_rate_10d": 0.67,
    "avg_return_1d": 0.8,
    "avg_return_3d": 1.9,
    "avg_return_5d": 2.8,
    "avg_return_10d": 4.1,
    "max_return_5d": 8.3,
    "min_return_5d": -3.1,
    "avg_drawdown": -1.2,
    "last_occurrence": "2026-03-12",
    "dates": ["2021-06-15", "2021-09-22", ...]
}
```

**Statistical significance filter:**
- **STRONG:** ≥ 10 occurrences AND win_rate_5d ≥ 60%
- **MODERATE:** ≥ 5 occurrences AND win_rate_5d ≥ 55%
- **WEAK:** ≥ 5 occurrences AND win_rate_5d ≥ 50%
- **INSIGNIFICANT:** below thresholds → excluded from fingerprint card

### 5. Fingerprint Card Generator

**File:** `pipeline/ta_fingerprint.py`

**Purpose:** Assemble the per-stock technical profile from backtest results.

**Output:** `pipeline/data/ta_fingerprints/{symbol}.json`

```json
{
    "symbol": "HAL",
    "generated": "2026-04-17",
    "data_range": "2021-04-17 to 2026-04-17",
    "data_points": 1247,
    "total_patterns_tested": 15,
    "significant_patterns": 6,
    "fingerprint": [
        {
            "pattern": "BB_SQUEEZE",
            "direction": "LONG",
            "significance": "STRONG",
            "occurrences": 18,
            "win_rate_5d": 0.72,
            "avg_return_5d": 2.8,
            "avg_return_10d": 4.1,
            "avg_drawdown": -1.2,
            "last_occurrence": "2026-03-12"
        }
    ],
    "best_pattern": "BB_SQUEEZE",
    "best_win_rate": 0.72,
    "personality": "momentum_breakout",
    "summary": "HAL responds strongly to Bollinger Band squeezes (72% win rate, 18 occurrences) and 200 DMA crossovers. Momentum breakout personality — buy compression, ride expansion."
}
```

**Personality classification rules:**
- `momentum_breakout` — best patterns are BB_SQUEEZE, VOL_BREAKOUT, BB_BREAKOUT_UP
- `mean_reverter` — best patterns are RSI_OVERSOLD_BOUNCE, RSI_OVERBOUGHT_REV
- `trend_follower` — best patterns are DMA200_CROSS_UP, MACD_CROSS_UP
- `volume_driven` — best pattern is VOL_BREAKOUT
- `candlestick_responsive` — best patterns are CANDLE_* types
- `pattern_agnostic` — no patterns reach MODERATE significance

### 6. Daily Scanner

**File:** `pipeline/ta_daily_scanner.py`

**Purpose:** Run at 15:30 IST daily. Check live prices against each stock's fingerprint card.

**Flow:**
1. Fetch today's close for all 213 stocks (EODHD real-time or Kite)
2. Append to `ta_historical/{symbol}.csv`
3. Compute all indicators on latest data
4. For each stock, check if any fingerprint pattern is TRIGGERED or APPROACHING
5. Emit alerts to `pipeline/data/ta_alerts.json`

**Proximity levels:**
- `TRIGGERED` — pattern fired today (e.g., close crossed above 200 EMA today)
- `APPROACHING` — within configurable threshold of trigger (default 2% for price-based, 5 RSI points for RSI-based)

**Alert output:**
```json
{
    "date": "2026-04-17",
    "alerts": [
        {
            "symbol": "HAL",
            "pattern": "BB_SQUEEZE",
            "status": "APPROACHING",
            "proximity_pct": 1.2,
            "historical_win_rate": 0.72,
            "historical_avg_return": 2.8,
            "occurrences": 18,
            "direction": "LONG",
            "current_price": 4180.0,
            "trigger_level": 4230.0
        }
    ]
}
```

**Integration with signal pipeline:**
- Alerts feed into `pipeline/signal_enrichment.py` as a new enrichment source (`ta_fingerprint`)
- TA conviction modifier: STRONG pattern with TRIGGERED status → +15 conviction points; APPROACHING → +5
- Shows on website Signal Explorer as badge: "TA: BB_SQUEEZE (72%, 18 occ)"
- Telegram card includes TA line when pattern is active

**Scheduled task:** `AnkaTAScanner` at 15:35 IST (after closing price capture at 15:30)

## Data Flow Summary

```
EODHD 5yr fetch (bootstrap, ~45 sec)
    → pipeline/data/ta_historical/HAL.csv (1250 rows)
    → ta_indicators.py computes BB, MACD, RSI, ATR, EMA, candles
    → ta_pattern_detector.py finds 15 event types over 5 years
    → ta_backtester.py measures 1/3/5/10 day forward returns
    → ta_fingerprint.py filters significant patterns, assigns personality
    → pipeline/data/ta_fingerprints/HAL.json (fingerprint card)

Daily at 15:35 IST:
    → ta_daily_scanner.py loads today's prices
    → Checks against fingerprint cards
    → Emits pipeline/data/ta_alerts.json
    → Signal enrichment picks up TA alerts
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `pipeline/ta_data_fetcher.py` | CREATE | EODHD 5-year OHLCV fetch + daily append |
| `pipeline/ta_indicators.py` | CREATE | Pure indicator library: BB, MACD, RSI, EMA, ATR, candles |
| `pipeline/ta_pattern_detector.py` | CREATE | 15 pattern event detectors |
| `pipeline/ta_backtester.py` | CREATE | Forward return backtest engine |
| `pipeline/ta_fingerprint.py` | CREATE | Fingerprint card generator + personality classifier |
| `pipeline/ta_daily_scanner.py` | CREATE | Daily scanner + alert emitter |
| `pipeline/signal_enrichment.py` | MODIFY | Add TA fingerprint as enrichment source |
| `pipeline/data/ta_historical/` | CREATE (generated) | 213 CSV files, 5yr OHLCV |
| `pipeline/data/ta_fingerprints/` | CREATE (generated) | 213 JSON fingerprint cards |
| `pipeline/data/ta_alerts.json` | CREATE (generated) | Daily alert output |

## Testing Strategy

- **Indicator tests:** Known-input / known-output for each indicator (e.g., RSI of constant series = 50, Bollinger of low-vol series = narrow bands)
- **Pattern detector tests:** Synthetic OHLCV with planted patterns → verify detection
- **Backtest tests:** Synthetic events with known forward returns → verify win rate calc
- **Fingerprint tests:** Mock backtest output → verify significance filtering and personality classification
- **Integration test:** Run 3 stocks (HAL, TCS, RELIANCE) end-to-end with real data

## Success Criteria

1. 5-year OHLCV fetched for ≥ 200 of 213 stocks
2. All 7 indicator functions produce correct output (verified against known values)
3. All 15 pattern types detected on real data with ≥ 1 occurrence across the universe
4. Fingerprint cards generated for all 213 stocks
5. ≥ 150 stocks have at least one MODERATE or STRONG pattern (not all are pattern_agnostic)
6. Daily scanner produces alerts within 30 seconds for full universe
7. Alerts flow into signal enrichment as conviction modifier
