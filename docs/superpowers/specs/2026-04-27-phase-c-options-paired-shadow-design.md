# Phase C Options Paired Shadow Ledger — Design

**Date:** 2026-04-27
**Status:** Design (pre-implementation-plan)
**Substrate:** Phase C live correlation-break shadow (futures-side, already operational)
**Type:** Forward-only OOS descriptive forensic — **no edge claim**, no hypothesis-registry entry, no kill-switch trigger.

---

## 1. Motivation

The Phase C live shadow ledger (`pipeline/phase_c_shadow.py`, scheduled `AnkaPhaseCShadowOpen` 09:25 IST / `AnkaPhaseCShadowClose` 14:30 IST) records paper trades on `OPPORTUNITY_LAG`-classified correlation breaks at Kite LTP, computes futures-equivalent P&L, and is awaiting N≥20 closed trades for a kill/promote decision (per `project_phase_c_kill_criteria.md`, D9 kill-line: edge < 100 bps OR win < 55% → archive Phase C).

The recent mechanical 60-day replay (`project_mechanical_60day_replay`) showed `POSSIBLE_OPPORTUNITY +41.67pp/328` BEATS `OPPORTUNITY_LAG −3.30pp/60` — the linear-payoff slice we trade live is the worst-performing one. Two interpretations are open:

1. **Edge is genuinely absent** — Phase C is noise, archive at D9.
2. **Edge exists but is trapped in linear payoff** — slow continuations get eaten by mean-reversion in futures, but a non-linear payoff (long-vol options) might still capture the fat-right-tail breaks.

We can answer (2) descriptively only by collecting paired (futures, ATM-options) realized P&L on the same signals, forward-only, OOS. There is no clean way to backtest Indian stock options at this resolution — strike-by-strike historical option chain data is incomplete and theta/IV behavior is path-dependent in a way that synthetic Black-Scholes pricing does not faithfully reproduce.

Separately, the existing **drift-vs-rent classifier** (`pipeline/synthetic_options.py:build_leverage_matrix`, `classify_tier`) produces a per-signal tier verdict (`HIGH-ALPHA SYNTHETIC` / `EXPERIMENTAL` / `NEGATIVE CARRY`) and writes `data/signals/synthetic_options_shadow.json`. The Options terminal tab (`pages/options.js`) already consumes it. The classifier has no validation pipeline — its tier verdicts are unconfirmed against realized P&L. The paired ledger gives drift-vs-rent its first ground-truth job.

## 2. Goal

Capture, forward-only OOS, paired (futures-side, ATM-options-side) realized P&L for every `OPPORTUNITY_LAG` Phase C signal, so that after N≥30 trades (descriptive readout, ~6–8 weeks) and N≥100 (statistical readout, ~5 months) we can answer:

- Did the options-side P&L diverge from the futures-side? Sign and magnitude.
- Stratified by `is_expiry_day`: do expiry-day signals behave differently?
- Stratified by `drift_vs_rent_tier`: did the classifier predict realized options edge?
- Stratified by entry-IV bucket and DTE bucket: where does options space rescue vs cost?

**Not in goal:** propose a tradeable strategy, fire any kill switch, append to `hypothesis-registry.jsonl`. This is a measurement layer.

## 3. Scope

### In scope

- A sidecar module hooked into the existing Phase C shadow engine that, on every futures-side leg open/close, also opens/closes a paired ATM options leg and records it to a separate ledger artifact.
- Live Kite quote-based entry/exit (mid-of-bid-ask, with liquidity floor) — no synthetic pricing for the realized side.
- Snapshot of the drift-vs-rent tier verdict at entry, frozen with the row.
- Greeks logged at **entry only** (back-solved IV → BS-derived delta/theta/vega) — for downstream regression of P&L against entry-IV / entry-delta. Not used by verdict logic. Exit Greeks are YAGNI in v1.
- Per-trade cost model (Zerodha retail option intraday: 15 bps slippage + STT + stamp), already implemented in `research/phase_c_v5/cost_model.py`.
- A new reporting module that writes a Markdown one-pager after every close cycle, stratified tables, no edge claim.
- A new `/api/research/phase-c-options-shadow` endpoint and an Options tab card surfacing live OPEN pairs + cumulative tier breakdown.

### Out of scope (deferred to v2 or beyond)

- Pairing on Phase C classifications other than `OPPORTUNITY_LAG`.
- Pairing on Phase B picks, news-event spread trades, SECRSI legs, or H-001 forward paper.
- Multi-leg options structures (straddles, verticals). v1 is single-leg ATM only.
- Weekly options. v1 is nearest-monthly only — Indian stock weekly options are too thin on most F&O names.
- Position sizing beyond 1 lot per signal.
- Any production trading hook. Paper ledger only.
- Backfilling historical Phase C signals — strictly forward-only from the deploy date.

## 4. Decisions locked during brainstorming

| # | Decision | Value |
|---|---|---|
| Q1 | Strike + expiry rule | **Nearest-monthly ATM**, strike picked as `argmin(|listed_strike − spot|)` over the actual NFO strike list at entry. |
| Q2 | Entry/exit pricing + liquidity gate | **Mid of Kite bid/ask** for both entry and exit; **skip if `(ask − bid) / mid > 5%`**, log `status=SKIPPED_LIQUIDITY`. |
| - | Trigger population | **Only `OPPORTUNITY_LAG` Phase C signals** (mirrors live futures shadow). |
| - | Position sizing | **1 lot per signal**, log `lot_size` and `notional_at_entry`. Verdict uses `pnl_pct` so size is a record, not a metric driver. |
| - | Greeks logging | **Entry only** (back-solved IV → BS delta/theta/vega). Record-only field; does not gate any logic. |
| - | Drift-vs-rent integration | **Tier verdict snapshotted at entry**, joinable post-hoc to realized P&L. Classifier code path unchanged. |
| - | Verdict cadence | **Descriptive at N=30**, bootstrap-inference at N=100. Ledger only. |
| - | Architecture | **Approach A: sidecar module + paired ledger**. |
| - | Expiry-day handling | **Trade them, do not skip them, log `is_expiry_day` and `seconds_to_expiry_at_close`, stratify every output by `is_expiry_day`.** |

## 5. Architecture

```
Phase C engine (existing, unchanged contract)            Sidecar (new)
─────────────────────────────────────────                ────────────────────────
phase_c_shadow.py                                        phase_c_options_shadow.py
  cmd_open(date)                                           open_options_pair(signal_row)
    [appends futures row to live_paper_ledger.json]          ├─ resolve_atm_strike(spot, ticker)
    │                                                         ├─ resolve_nearest_monthly_expiry(today)
    └── try/except wrapper ──────────────────────────►       ├─ compose_tradingsymbol(...)
                                                              ├─ kite.quote(instrument_token)
                                                              ├─ liquidity gate (spread_pct ≤ 5%)
                                                              ├─ backsolve_iv() + compute_greeks()
                                                              ├─ snapshot drift_vs_rent tier
                                                              └─ append → live_paper_options_ledger.json
  cmd_close(date)                                          close_options_pair(signal_id)
    [closes futures row, computes P&L]                       ├─ kite.quote() at 14:30
    │                                                         ├─ cost_model.apply_to_pnl(option)
    └── try/except wrapper ──────────────────────────►       └─ update row → CLOSED
```

**Decoupling guarantees:**
- Sidecar exceptions are caught at the Phase C call site. Futures shadow proceeds unaffected.
- Sidecar writes to a **separate artifact file**. The futures ledger schema is untouched.
- Sidecar reads the futures ledger at close time to find rows to pair against — single direction of read coupling, no write coupling.
- One scheduled task pair (existing). No new `.bat` files, no time offset, perfect entry-time alignment.

## 6. Components & contracts

### 6.1 `pipeline/phase_c_options_shadow.py`

```python
def open_options_pair(signal_row: dict) -> dict:
    """
    Called from phase_c_shadow.cmd_open after a futures row is appended.
    signal_row: the futures-side row just written. Provides date, symbol,
                side, signal_time, signal_id.
    Returns: the options-ledger row written (status one of
             OPEN | SKIPPED_LIQUIDITY | ERROR).
    Idempotent on signal_id — no duplicate rows.
    """

def close_options_pair(signal_id: str) -> dict:
    """
    Called from phase_c_shadow.cmd_close after the futures row is updated.
    signal_id: PK joining to the open row.
    Returns: the options-ledger row updated (status CLOSED or
             TIME_STOP_FAIL_FETCH).
    No-op if no matching OPEN row.
    """
```

### 6.2 `pipeline/options_atm_helpers.py`

```python
def resolve_nearest_monthly_expiry(today: date,
                                   ticker: str,
                                   nfo_master_df: DataFrame) -> date:
    """
    Reads the NFO instrument master, filters to ticker's option contracts,
    selects the smallest expiry ≥ today. Handles holiday-shifted expiries
    by virtue of reading the actual NFO master (not by computing
    last-Thursday rules).
    """

def resolve_atm_strike(spot: float, ticker: str, expiry: date,
                       nfo_master_df: DataFrame) -> int:
    """
    Reads strike list for (ticker, expiry) from NFO master, picks
    argmin(|strike - spot|). No hardcoded step ladder.
    """

def compose_tradingsymbol(ticker: str, expiry: date, strike: int,
                          option_type: Literal["CE", "PE"]) -> str:
    """
    NSE format: e.g., RELIANCE25APR2400CE.
    """
```

### 6.3 `pipeline/options_quote.py`

```python
@dataclass
class OptionsQuote:
    instrument_token: int
    bid: float
    ask: float
    mid: float
    spread_pct: float
    last_price: float
    timestamp: datetime
    liquidity_passed: bool   # spread_pct <= 0.05
    skip_reason: str | None  # "WIDE_SPREAD" / "NO_BID" / "NO_ASK" / None

def fetch_mid_with_liquidity_check(
        kite_client, instrument_token: int) -> OptionsQuote:
    """
    One Kite quote() call, returns OptionsQuote with liquidity_passed
    set per the 5% rule. Does NOT raise on wide spread — caller decides.
    Raises only on Kite session/API errors.
    """
```

### 6.4 `pipeline/options_greeks.py`

```python
def backsolve_iv(spot: float, strike: float, dte_days: int,
                 mid_premium: float, option_type: Literal["CE", "PE"],
                 r: float = 0.065) -> float:
    """
    Newton-Raphson IV back-solve from BS. Bounded [0.05, 2.00],
    raises on non-convergence.
    """

def compute_greeks(spot: float, strike: float, dte_days: int,
                   iv: float, option_type: Literal["CE", "PE"],
                   r: float = 0.065) -> dict:
    """
    Returns dict: {delta, theta, vega}. Pure BS, no path dependence.
    """
```

### 6.5 Reused infrastructure (no new code)

| Module | Reuse |
|---|---|
| `pipeline/research/phase_c_v5/cost_model.py` | Options dispatch (15 bps slippage + STT_sell 0.0625% + stamp_buy 0.003%) — already implemented and tested. |
| `pipeline/synthetic_options.py:classify_tier` | Called once per open to snapshot tier. Classifier is unchanged. |
| `pipeline/kite_client.py` | Existing `quote()` wrapper; we call it with options instrument tokens just like `oi_scanner` does. |
| `pipeline/data/kite_cache/instruments_nfo.csv` | Existing daily-refreshed NFO master. Sidecar reads the same artifact. |

## 7. Schema — `live_paper_options_ledger.json`

JSON array, one row per paired trade. Mirrors the style of `live_paper_ledger.json` but with options-specific columns.

```jsonc
{
  // PK + join keys
  "signal_id": "2026-04-29_RELIANCE_0935",   // {date}_{symbol}_{HHMM}
  "date": "2026-04-29",
  "symbol": "RELIANCE",
  "side": "LONG",                            // from Phase C engine
  "option_type": "CE",                       // LONG → CE, SHORT → PE

  // Contract identity
  "expiry_date": "2026-05-29",
  "days_to_expiry": 30,
  "is_expiry_day": false,
  "strike": 2400,
  "tradingsymbol": "RELIANCE25MAY2400CE",
  "instrument_token": 12345678,

  // Sizing
  "lot_size": 250,
  "lots": 1,
  "notional_at_entry": 30187.5,              // entry_mid * lot_size * lots = 120.75 * 250 * 1

  // Entry market state
  "entry_time": "2026-04-29T09:35:12+05:30",
  "entry_bid": 119.5,
  "entry_ask": 122.0,
  "entry_mid": 120.75,
  "spread_pct_at_entry": 0.0207,
  "entry_iv": 0.276,
  "entry_delta": 0.51,
  "entry_theta": -3.4,
  "entry_vega": 4.1,

  // Drift-vs-rent snapshot (frozen at entry)
  "drift_vs_rent_tier": "EXPERIMENTAL",
  "drift_vs_rent_matrix": {
    "1m":     { "drift_pct": 1.8, "rent_pct": 2.4, "net_edge_pct": -0.6 },
    "15d":    { "drift_pct": 1.2, "rent_pct": 1.4, "net_edge_pct": -0.2 },
    "same_day": { "drift_pct": 0.4, "rent_pct": 0.3, "net_edge_pct": 0.1 }
  },

  // Status
  "status": "OPEN",                          // OPEN | CLOSED | SKIPPED_LIQUIDITY | ERROR | TIME_STOP_FAIL_FETCH
  "skip_reason": null,                       // populated for skips/errors

  // Filled at 14:30 close
  "exit_time": null,
  "exit_bid": null,
  "exit_ask": null,
  "exit_mid": null,
  "seconds_to_expiry_at_close": null,
  "pnl_gross_pct": null,
  "pnl_net_pct": null,                       // after cost model
  "pnl_gross_inr": null,
  "pnl_net_inr": null
}
```

**Joinability:** `signal_id` is the foreign key to the futures-side `live_paper_ledger.json`. The reporting layer joins on this to produce paired `(futures_pnl_pct, options_pnl_pct, options_minus_futures)` rows.

## 8. Data flow

### 8.1 OPEN path (09:25 IST)

1. Phase C engine generates breaks → filters to `OPPORTUNITY_LAG` → opens futures shadow leg → appends row to `live_paper_ledger.json` with `signal_id`.
2. **Sidecar `open_options_pair(signal_row)`** is called inside try/except:
   1. `resolve_nearest_monthly_expiry(today, ticker)` → `expiry_date`.
   2. Compute `days_to_expiry`, `is_expiry_day`.
   3. Fetch live spot (the futures row already has `entry_px`; reuse it).
   4. `resolve_atm_strike(spot, ticker, expiry)` → `strike`.
   5. `compose_tradingsymbol(...)` → `tradingsymbol`. Look up `instrument_token` from NFO master.
   6. `fetch_mid_with_liquidity_check(kite, instrument_token)` → `OptionsQuote`.
   7. **Liquidity gate:** if `not quote.liquidity_passed`: append row with `status=SKIPPED_LIQUIDITY`, `skip_reason=quote.skip_reason`. Done.
   8. `backsolve_iv(...)` → `entry_iv`. `compute_greeks(...)` → delta/theta/vega.
   9. `synthetic_options.classify_tier(signal)` → `drift_vs_rent_tier` + matrix.
   10. Append row with `status=OPEN`, all fields populated.
3. Any exception: append row with `status=ERROR`, `skip_reason=str(exc)[:200]`. Log full trace to `pipeline/logs/phase_c_options_shadow.log`. Futures shadow continues.

### 8.2 CLOSE path (14:30 IST)

1. Phase C engine closes futures rows in `live_paper_ledger.json`.
2. **Sidecar `close_options_pair(signal_id)`** is called inside try/except for each closed futures row:
   1. Locate matching OPEN row in options ledger by `signal_id`. If absent, skip silently.
   2. Fetch quote at 14:30: `fetch_mid_with_liquidity_check(...)`. (Liquidity gate at close is **not** a skip — we always close what we opened. Wide spread at close is logged but doesn't change the action.)
   3. Compute `pnl_gross_pct = (exit_mid - entry_mid) / entry_mid`.
   4. `cost_model.apply_to_pnl(pnl_gross_pct, instrument='option', notional=notional_at_entry)` → `pnl_net_pct`.
   5. Compute INR variants by multiplying through `notional_at_entry`.
   6. If `is_expiry_day`: compute `seconds_to_expiry_at_close = (15:30 IST today) − exit_time`.
   7. Update row: `status=CLOSED`, exit fields populated.
3. Any exception during fetch: update row to `status=TIME_STOP_FAIL_FETCH`, leave exit fields null. Log trace. The next morning's reconciliation can backfill from EOD bhavcopy if available; do NOT synthesize a guess.

## 9. Error handling

| Failure | Effect | Recovery |
|---|---|---|
| Liquidity floor at OPEN | Row written `SKIPPED_LIQUIDITY`. Counts toward dataset N for skip-rate analysis but not P&L. | None needed. |
| Kite quote fails at OPEN | Row written `ERROR`. Futures shadow unaffected. | Manual: investigate Kite session. No auto-retry. |
| Kite quote fails at CLOSE | Row stays `OPEN` with `status=TIME_STOP_FAIL_FETCH`. Exit fields null. | Manual EOD-bhavcopy backfill, or row drops out of N. |
| NFO master cache stale (>24h) | First call refreshes via existing `kite_client` path. If still stale → `ERROR`. | Same recovery path as `oi_scanner`. |
| Phase C signal opens after 14:30 IST | **Cannot happen** — the 14:30 cutoff in `pipeline/run_signals.py` and `break_signal_generator.py` blocks all new live OPENs. Defensive assertion in sidecar logs and skips. | None; cutoff guarantees this. |
| Backsolve IV non-convergence | Log row with `entry_iv=null` and best-effort Greeks (`null`). Trade still proceeds — IV is metadata, not blocking. | None needed. |
| Sidecar writes the same `signal_id` twice (idempotency violation) | Second call is a no-op. Existing row wins. | None needed. |

All sidecar errors written to `pipeline/logs/phase_c_options_shadow.log` with: timestamp, signal_id, ticker, strike, expiry, exception class, traceback.

## 10. Testing strategy

**TDD, red-green-commit per component.**

### Unit tests

- `test_options_atm_helpers.py`:
  - `resolve_nearest_monthly_expiry` — normal-Thursday case; holiday-shifted expiry (use a fixture NFO master); month-rollover edge (last-day-of-month signal); ticker without monthly contracts → raises.
  - `resolve_atm_strike` — spot exactly between two strikes; spot equal to a listed strike; spot outside listed range → picks nearest endpoint; empty strike list → raises.
  - `compose_tradingsymbol` — formatting matches NSE convention for {2-digit-year}{3-letter-month}{strike}{CE|PE}.

- `test_options_quote.py`:
  - Liquidity-passed case (spread 2% of mid).
  - Wide-spread case (spread 8% of mid) → `liquidity_passed=False`, `skip_reason="WIDE_SPREAD"`.
  - Zero bid → `liquidity_passed=False`, `skip_reason="NO_BID"`.
  - Mock Kite client raises → propagates.

- `test_options_greeks.py`:
  - Back-solve IV on a synthetic-priced premium round-trips to within 0.5%.
  - Non-convergence (impossible mid premium) → raises.
  - Greeks at ATM: delta near 0.5 for CE, near -0.5 for PE.

### Integration tests

- `test_phase_c_options_shadow.py`:
  - Mock futures row + mock Kite quote → `open_options_pair` writes `status=OPEN` row with all fields populated.
  - Wide spread mock → `status=SKIPPED_LIQUIDITY` row, no Greeks computed.
  - Kite raises during open → `status=ERROR`, futures ledger untouched (we don't write to futures ledger here, but verify side-effect isolation).
  - `close_options_pair` with mock 14:30 quote → row updates to `CLOSED` with computed P&L (assert sign + magnitude on a constructed scenario).
  - `close_options_pair` with no matching OPEN row → silent no-op.
  - Idempotency: calling `open_options_pair` twice for same signal_id → only one row.

### Smoke test

Pre-merge dry-run on the live system:
1. Stage the sidecar in dry-run mode (writes to a `*_dryrun.json` artifact, doesn't touch real ledger).
2. Run for 2 trading days. Verify:
   - ATM strikes resolve to plausible values for the tickers in the live ledger.
   - Nearest-monthly expiry resolution matches NSE calendar.
   - At least 1 row passes liquidity floor and 1 row gets skipped (sanity on the gate firing).
   - Greeks computed and look sensible.
3. Diff the dry-run ledger against the futures ledger to confirm `signal_id` join works.

## 11. Reporting & verdict

### 11.1 Output

`pipeline/phase_c_options_report.py` runs after each close cycle (called from `cmd_close` post-write), produces `pipeline/data/research/phase_c/options_paired_report.md`. Tables stratified by `is_expiry_day` (always two rows per metric: expiry-day, non-expiry-day):

- **Table A — Headline paired diff**: mean(`options_pnl_pct − futures_pnl_pct`), bootstrap 95% CI, N.
- **Table B — Win rate by drift_vs_rent_tier**: rows = {HIGH-ALPHA, EXPERIMENTAL, NEGATIVE CARRY}; cols = win-rate, mean P&L, N.
- **Table C — P&L by entry_iv bucket**: low (<P33), mid (P33–P66), high (>P66).
- **Table D — P&L by DTE bucket**: 0d (expiry day), 1–5d, 6–15d, 16–30d, 31+d.
- **Table E — Skip rate**: SKIPPED_LIQUIDITY / total signals, by ticker.

### 11.2 Verdict cadence

- **N ≥ 30**: descriptive readout — sign and magnitude of paired diff, no statistical claim.
- **N ≥ 100**: bootstrap-inference cut — does paired diff differ from zero at α=0.05? Stratified separately for expiry-day vs non-expiry-day.
- **No kill-switch trigger.** No hypothesis-registry append. The classifier (drift-vs-rent) is what gets tested via Table B; Phase C edge claim is unaffected by this work.

### 11.3 UI surface

- New endpoint `GET /api/research/phase-c-options-shadow` returns: `{open_pairs: [...], cumulative: {N, by_tier: {...}, by_expiry_day: {...}}}`.
- Options tab gets a new card "Phase C Paired Shadow" showing live OPEN pairs (futures P&L | options P&L | tier badge) and cumulative tier breakdown. Mirrors the actionable-row design rule (no static rows that don't change).

## 12. Documentation sync (mandatory at merge)

Per CLAUDE.md "Documentation Sync Rule":

- `docs/SYSTEM_OPERATIONS_MANUAL.md` — add the sidecar to the 09:25 / 14:30 task descriptions; add the new artifact to the data-flow section.
- `pipeline/config/anka_inventory.json` — no new task entry (sidecar piggybacks on existing tasks), but add the new artifact path to the existing `AnkaPhaseCShadowOpen` / `AnkaPhaseCShadowClose` `expected_outputs`.
- `CLAUDE.md` — note the paired-options ledger under the F3 Phase C live shadow paragraph.
- New memory: `memory/project_phase_c_options_paired.md` — purpose, schema location, verdict cadence, why no edge claim.
- `memory/MEMORY.md` — pointer line.

## 13. Risks & open questions

1. **NFO master refresh timing.** `instruments_nfo.csv` refreshes daily. If the morning refresh fails and the cache is stale, expiry resolution may pick a no-longer-listed expiry. Mitigated by reusing `oi_scanner`'s existing refresh-or-error path.
2. **Stock-options weekly availability.** A small subset of names have weeklies; we ignore them by design (monthly-only). If a Phase C ticker has *no* monthly contracts (rare for the F&O universe but possible during product changes), the resolver raises — caught as `ERROR` row.
3. **IV back-solve cost.** Newton-Raphson on every open call. For ~5 trades/day this is negligible, but if v2 expands to hundreds we'd cache.
4. **Drift-vs-rent classifier inputs.** `synthetic_options.build_leverage_matrix` requires a "signal" payload — exact input shape needs verification at implementation time. If the classifier expects fields the futures-row doesn't carry, the implementation plan task should add an adapter.
5. **Time alignment.** Sidecar fires inside the same Python process as the futures engine; entry quotes for futures and options are typically <500ms apart. If Kite rate-limits and adds seconds of latency, the "co-timed" claim weakens. Acceptable for a measurement layer; flag in the report.
6. **Reconciliation gap.** `TIME_STOP_FAIL_FETCH` rows have null exits. After ~6 weeks if more than ~5% of rows hit this status, we need an EOD-bhavcopy backfill path. v1 does not implement that — flag for v2.

## 14. Implementation sequencing (preview)

The implementation plan (next document) will sequence as TDD red-green-commit tasks:

1. T1: `options_atm_helpers.py` (TDD).
2. T2: `options_quote.py` (TDD).
3. T3: `options_greeks.py` (TDD).
4. T4: `phase_c_options_shadow.py` open path (TDD with mocks).
5. T5: Wire sidecar into `phase_c_shadow.py` cmd_open with try/except.
6. T6: `phase_c_options_shadow.py` close path (TDD with mocks).
7. T7: Wire sidecar into `phase_c_shadow.py` cmd_close with try/except.
8. T8: `phase_c_options_report.py` (TDD).
9. T9: API endpoint + Options tab card.
10. T10: Smoke run on live for 2 trading days (dry-run artifact).
11. T11: Docs + memory sync per §12; commit and merge.

No backtest task. No hypothesis-registry append.

---

**End of design.**
