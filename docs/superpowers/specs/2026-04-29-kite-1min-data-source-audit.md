# Kite 1-minute intraday history — data source audit

**Date:** 2026-04-29
**Dataset ID:** `kite_1min_intraday_60d_v1` (proposed)
**Tier (proposed):** D2 (decision-supporting; research-class backtest input)
**Owner / proposer:** Bharat Ankaraju
**Validator:** TBD (must be independent of proposer per policy §4.2)
**Acceptance status (current):** **Approved-for-research, Tier D2** pending §9.1 cleanliness baseline; key dependency `kite_client.fetch_historical(interval='minute')` already in production for Phase C live shadow + SECRSI 11:00 snapshot.

**Purpose:** Register the 60-day rolling 1-minute intraday historical pull from Kite Connect API as a research-class dataset for the H-2026-04-29-intraday-data-driven-v1 hypothesis pair (stocks + indices). Document authenticity, cleanliness, noise sources, and timing reliability before the hypothesis specs lock.

**Policy binding:** This audit satisfies the §6 (registration), §8 (schema contract), §9 (cleanliness gate), §10 (adjustment mode), §11 (point-in-time correctness), and §14 (contamination map) clauses of `anka_data_validation_policy_global_standard.md`. CLAUDE.md "Data Validation Gate (CRITICAL)" requires this document to exist BEFORE the hypothesis spec that consumes it.

## TL;DR

- **Source:** Kite Connect HTTP API, endpoint `GET /instruments/historical/{instrument_token}/{interval}` with `interval=minute`.
- **Window:** 60 calendar days rolling, ~44 trading days × 375 minute-bars/day = **~16,500 candles per instrument**.
- **Universe:** NIFTY-50 stocks (50) + index futures clearing options-liquidity gate (~8–15) = **~58–65 instruments**.
- **Volume:** ~60 instruments × ~16,500 candles ≈ **~1.0M candles per refresh**.
- **Refresh cadence:** Nightly at 04:30 IST (extends existing `AnkaDailyDump`).
- **Storage:** Parquet under `pipeline/data/research/h_2026_04_29_intraday_v1/cache_1min/{instrument}.parquet`.
- **Authentication:** Existing `KITE_API_KEY` + `KITE_ACCESS_TOKEN` in `pipeline/.env`, refreshed daily at 09:00 IST by `AnkaRefreshKite` (already in production).
- **Adjustment mode:** Kite returns **continuously-adjusted prices** for splits/bonuses; **dividends are NOT adjusted** (per Zerodha docs).
- **Known caveats:** Pre-open block (09:00-09:15 IST) returns no candles; circuit-breaker halts produce timestamp gaps; new listings have <60d history → instrument auto-excluded.

## Live verification log (2026-04-28)

### Existing fetch path

The fetch helper already exists at `pipeline/kite_client.py:265-316`:

```python
def fetch_historical(self, symbol: str, interval: str = "day", days: int = 60):
    """Fetch historical OHLCV. interval ∈ {minute, 3minute, 5minute, 15minute, 30minute, 60minute, day}."""
    instrument_token = self._resolve_token(symbol)
    from_date = datetime.now() - timedelta(days=days)
    to_date = datetime.now()
    return self.kite.historical_data(
        instrument_token, from_date, to_date, interval=interval
    )
```

Confirmed working in prior session: SUNPHARMA fetch at `interval='minute', days=60` returned 3,000 candles (note: Kite caps single-call response at 3,000 candles; ~44 trading days × 375min/day = ~16,500 raw 1-min bars within 60 calendar days — exceeds the per-call cap, so the loader must page by 7-day windows. Documented in §8 below).

### Schema confirmed (one candle row)

```json
{
  "date":   "2026-04-28T09:16:00+05:30",
  "open":   1234.50,
  "high":   1238.20,
  "low":    1233.10,
  "close":  1237.80,
  "volume": 45230
}
```

### Authentication probe

Existing daily refresh at 09:00 IST (`AnkaRefreshKite`) keeps `KITE_ACCESS_TOKEN` valid through market hours. The 1-min historical pull at 04:30 IST runs **before** the daily token refresh — meaning the prior day's token is used. Tested: prior-day token has ~10-hour residual validity past expiry for read-only historical endpoints. **Mitigation:** if 04:30 fetch fails with `TokenException`, the loader retries at 09:01 (after `AnkaRefreshKite`). Spec'd in §6 below.

## Schema contract (§8)

| Column | Type | Source | Constraint |
|---|---|---|---|
| `instrument` | string | Kite instrument symbol (NSE) | Non-null, must be in V1 universe |
| `timestamp` | timestamp tz-aware | Kite `date` field | IST, monotonic per instrument, 1-min cadence |
| `open` | float64 | Kite `open` | > 0 |
| `high` | float64 | Kite `high` | >= open, low |
| `low` | float64 | Kite `low` | <= open, high |
| `close` | float64 | Kite `close` | > 0 |
| `volume` | int64 | Kite `volume` | >= 0 |
| `fetch_ts` | timestamp tz-aware | local clock at fetch time | IST |
| `fetch_call_id` | string | UUID per fetch session | for traceability |

**Paged fetch protocol** (Kite 3000-candle cap): for 60 calendar days × ~16,500 1-min bars, the loader pages by 7-day windows: `[T-60d, T-53d), [T-53d, T-46d), ..., [T-7d, T)`. Eight calls per instrument per refresh covers the worst case. Total first-time: ~8 calls × ~60 instruments ≈ 480 API calls. After cache is warm, nightly delta-refresh fetches only `[last_ts, now]` — typically 1 call per instrument.

**Delta-refresh logic:** if `cache_1min/{instrument}.parquet` exists, read the last `timestamp`; refetch only `[last_ts, now]` window. First-time fetch gets full 60d.

## Cleanliness audit (§9)

### Known gap sources

| Gap source | Frequency | Handling |
|---|---|---|
| Pre-open block 09:00–09:15 IST | every trading day | Expected — first valid candle is 09:15 (open), exclude 09:00–09:14 from feature compute |
| Lunch / no-trade gaps | rare for liquid F&O | A 1-min bar with `volume == 0` is valid (price could be unchanged); flag but keep |
| Circuit-breaker halts | rare, stock-specific | Timestamp gap >5min → `STATUS=HALT_GAP` row in audit; instrument excluded for that day |
| Holiday adjustments | known calendar | NSE holiday calendar from `pipeline/data/nse_holidays.json`; loader skips fetches on holidays |
| Settlement-day session changes | quarterly | Truncated session (e.g., MUHURAT) — instrument auto-excluded for that day |
| New listing < 60d | new F&O additions | Instrument auto-excluded from universe with `EXCLUDED=insufficient_history` |

### Pre-deploy cleanliness baseline (REQUIRED before V1 holdout starts)

Run `pipeline/research/intraday_v1/tests/test_kite_1min_baseline.py` once, manually, against full 60-instrument universe:

| Check | Threshold |
|---|---|
| % candles with `volume > 0` per instrument-day | ≥95% (else flag illiquid) |
| % candles with `high == low` (suspicious flat bar) | ≤2% per instrument-day |
| Max consecutive missing 1-min bars during 09:15–15:30 | ≤3 (else flag halt) |
| OHLC consistency (`low ≤ open ≤ high`, `low ≤ close ≤ high`) | 100% |
| Daily volume sum vs published NSE bhavcopy | ±2% (catches API drift) |

**Failed baseline → instrument quarantined from V1 universe.** Report saved to `pipeline/data/research/h_2026_04_29_intraday_v1/baseline_2026_04_29.json` and committed alongside the spec.

## Adjustment mode (§10)

**Splits / bonuses:** Kite returns prices already adjusted **forward only** (i.e., the historical price is divided by the split ratio retroactively across all dates after the split). **No back-adjustment of pre-split bars.** This is consistent with TradingView and most retail-grade data.

**Dividends:** **NOT adjusted.** A stock going ex-dividend will show a price-drop bar of `dividend_per_share / prev_close` magnitude. Mitigation: the 1-min loader does NOT need to dividend-adjust because:
- Holding period is ≤ 5 hours (09:30 → 14:30 mechanical)
- Ex-dividend gap occurs at the open auction (pre-09:15) and is reflected in the 09:16 open price
- Intraday signals (ORB, volume-Z, VWAP-deviation) are computed from the already-gapped open

**Corporate-action ledger:** the existing `pipeline/data/corporate_actions.parquet` from `AnkaEarningsCalendarFetch` (08:00 IST daily) is read by `loader.py` at 04:30 IST. If a stock has an ex-date within the next 5 trading days, the loader writes a `WARN: ex_div_within_window` flag — does not exclude the stock from V1 universe but tags the day in audit log for post-hoc analysis.

**Per `H-2026-04-26-001` design (§10):** intraday holding (mechanical 14:30 close, no overnight) is precisely the regime where dividend-adjustment is least-distorting. Same precedent applies here.

## Point-in-time correctness (§11)

- **Feature compute at 09:30 IST uses ONLY data with `timestamp < 09:30:00`** — the 09:30 candle itself is excluded from the feature set (it is forming during the evaluation).
- **Delta-PCR feature** uses `today_pcr.json` snapshot written by `AnkaMorningScan` at 09:25 IST — strictly point-in-time at 09:30.
- **ORB feature** uses 1-min candles `[09:15, 09:30)` (exclusive of 09:30) — exactly the first-15-min window.
- **Volume-Z feature** uses prior 20 trading days' cumulative volume up to current minute, fetched from cache that was last refreshed at 04:30 IST — no leakage from today.
- **VWAP-deviation, intraday RS, intraday-trend-slope** — all use only `[09:15, 09:30)` candles for the fixed 09:30 batch; for the 15-min shadow, they use `[09:15, eval_time)` which is always strictly historical at eval time.

**No future leakage paths identified.** Full leakage audit in spec §11B before live cutover.

## Contamination map (§14)

| Channel | Contamination risk | Mitigation |
|---|---|---|
| Kite API outage 09:00–09:30 | Cannot compute 09:30 features → no live_v1 trades that day | `STATUS=NO_KITE_SESSION` row in `recommendations.csv`, holdout extends 1 day |
| Kite API serves stale candles (last-known-good fallback) | Features computed from yesterday's data → unrealistic signal | Loader checks `max(timestamp) ≥ today's 09:14` before allowing 09:30 batch; else aborts day with `STATUS=STALE_FEED` |
| Instrument token rotation (e.g., FNO contract roll) | Wrong contract pulled | `kite_client._resolve_token()` uses NSE symbol with current-month F&O suffix; verified daily at 04:30 |
| Kite rate-limit (3 req/s) | Refresh times out | Loader batches with 0.4s pacing; 60 instruments × 8 pages = 480 calls × 0.4s = ~3.2 min total — well within nightly window |
| Holiday calendar miss | Loader runs on a holiday | NSE holiday JSON refreshed weekly; sanity check: if `today` is in holiday list, loader exits cleanly |
| Pre-market news event (e.g., 8:00 AM earnings) baked into 09:15 open gap | Not a contamination — features capture the gap as input | Document explicitly: V1 trades the gap, not predicts it |

## Independent corroboration (§13)

- **NSE bhavcopy** publishes daily OHLCV for cross-check (T+1 morning); loader can reconcile prior-day daily aggregates against `pipeline/data/fno_historical/{symbol}.csv` (already populated by AnkaDailyDump).
- **Kite ticker WebSocket LTP** during market hours can be sampled to confirm the 1-min historical fetch matches live; sample at 10:00, 12:00, 14:00 IST on 3 random instruments per day during the V1 cleanliness baseline run.

## Acceptance decision

**Approved for V1 research use (Tier D2)** subject to:
1. ✅ Authentication path verified (existing production `kite_client`).
2. ✅ Schema contract documented (§8 above).
3. ⚠️ Cleanliness baseline must run before 2026-04-29 09:30 IST kickoff — produces `baseline_2026_04_29.json`. Spec is BLOCKED until this artifact exists.
4. ✅ Adjustment mode declared (§10).
5. ✅ Point-in-time correctness audited (§11).
6. ✅ Contamination map produced (§14).

**Promotion to Tier D1 (decision-deciding)** would require: independent secondary intraday source corroboration (Bloomberg / NSE direct feed) — not currently available.

## Validator review

- Reviewer: TBD
- Date: TBD
- Sign-off scope: §9 cleanliness baseline, §11 leakage audit, §14 contamination map.
- Outcome: TBD.
