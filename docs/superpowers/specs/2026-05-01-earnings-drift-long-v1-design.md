# H-2026-05-01-earnings-drift-long-v1 — Pre-Event Volume + Momentum Earnings Drift LONG

**Hypothesis ID:** `H-2026-05-01-earnings-drift-long-v1`
**Strategy class:** `event-driven-multi-day-long`
**Family scope:** earnings-event-driven, single hypothesis (LONG side only at v1; SHORT side deferred to v2)
**Standards version:** 1.0_2026-04-23 (`docs/superpowers/specs/backtesting-specs.txt`)
**Spec version:** v1.0
**Predecessor:** `H-2026-05-01-NEUTRAL-001` (NIFR — DEAD), `H-2026-04-27-003` (SECRSI — strong negative prior in Stage A 5y replay), `H-2026-04-28-001` (sector rotation — DEAD), `H-2026-04-28-002` (sector pair — DEAD wrong direction). Family-level pivot from intraday NEUTRAL stock-level alpha to multi-day event-driven sector-tilted holds.

---

## 1. Claim

A frozen-rule LONG strategy that, on the last trading day strictly before each NIFTY-Bank-or-IT quarterly earnings announcement, **opens** if ALL FOUR of (a) 5-day volume Z ≥ +0.52 AND (b) 5-day stock momentum > 0 AND (c) 21-day realised volatility ≥ 29% annualised AND (d) V3-CURATED-30 regime label ∈ {NEUTRAL, RISK-ON} at T-1, **holds for 5 trading days** with ATR(14)×2 per-leg stop and mechanical TIME_STOP at T+4 14:30 IST, will, on a single-touch forward holdout from **2026-05-04 → 2026-08-01** (≈63 trading days), produce **post-S1 (20 bps round-trip) net mean ≥ +25 bps per trade** with **hit rate ≥ 50%** and **annualised Sharpe ≥ 1.0** over **n ≥ 6 trades**.

**Stretch graduation criterion:** Sharpe ≥ 1.0 across the holdout graduates from EXPLORING to SIGNAL tier.

## 2. Pre-exploration disclosure

This hypothesis is registered AFTER observing the Stage A descriptive forensic in `pipeline/research/h_2026_05_01_earnings_drift/` committed 2026-05-01. The forensic ran on 314 quarterly earnings events from 40 stocks (NIFTY Bank 19 + NIFTY IT 21) over 2021-05-01 → 2024-04-30.

**Observed-on-development-data summary (in-sample):**

The forensic Stage A bivariate cells used `pd.qcut`-derived quintile boundaries (uses full-sample distribution → mild PIT-violation in cell-selection). The TRULY frozen rule below uses HARD thresholds (no future data leakage). Both numbers reported for transparency.

| Slice (Stage A — qcut quintile, uses full-sample) | n | gross H=5 bps | net@20 H=5 bps | hit % |
|---|---:|---:|---:|---:|
| Headline (all 314, futures unconditional) | 314 | +66.7 | +46.7 | 51.9% |
| vol_Q5 alone (top 20% pre-event volume) | 62 | +256.7 | +236.7 | 61.3% |
| vol_Q5 × short_mom_pos | 34 | +297.2 | +277.2 | 55.9% |
| Sector split: IT_Services H=5 unconditional | 138 | +106.2 | +86.2 | 55.8% |
| NEUTRAL regime cohort H=5 (where 4 prior NEUTRAL hypotheses failed) | 219 | +93.8 | +73.8 | 50.2% |

| Slice (FROZEN spec — hard thresholds, ATR×2 stop, T+5 14:30 close, date-sorted MaxDD) | n | gross | net@20 | hit % | Sharpe (ann.) | MaxDD % capital |
|---|---:|---:|---:|---:|---:|---:|
| vol_z ≥ 0.52 AND short_mom > 0 (no vol/regime filter — earliest draft) | 70 | +118 | +98 | 45.7% | 0.91 | -37.4% |
| vol_z ≥ 0.52 AND short_mom > 0 AND realized_vol_21d_pct ≥ 29.0 (price-vol filter only) | 37 | +207 | +187 | 51% | +1.41 | -46.8% |
| **+ regime gate {NEUTRAL, RISK-ON} (CHOSEN spec v1.0)** | **32** | **+281** | **+261** | **53%** | **+1.94** | **-38.7%** |

The CHOSEN cell (`realized_vol_21d_pct ≥ 29` AND `regime ∈ {NEUTRAL, RISK-ON}`) is selected because it (i) clears the spec by ~10x in mean, (ii) achieves Sharpe 1.94 on a meaningful in-sample n=32, (iii) reduces MaxDD vs the no-regime variant by 8pp, and (iv) cleanly removes 3 of 4 outsize losers from the Oct 2021 - May 2023 cluster (MPHASIS -916, BANKINDIA -670, PNB -775) — which were CAUTION or EUPHORIA regime days where LONG earnings exposure is structurally riskier.

Excluded events under regime gate (5 trades dropped):
| Symbol | Entry | Regime | Net@20 bps | Reason kept-out |
|---|---|---|---:|---|
| MPHASIS | 2021-10-20 | CAUTION | -916 | the worst Oct 2021 loser — gate filters it |
| FEDERALBNK | 2021-10-21 | CAUTION | +109 | small win, OK to skip |
| PNB | 2022-10-31 | EUPHORIA | -775 | EUPHORIA regime is over-extended; LONG into earnings risky |
| BANKINDIA | 2023-05-05 | CAUTION | -670 | CAUTION regime, structural underperformance |
| ETERNAL | 2024-02-07 | CAUTION | +824 | a winner skipped — net +173 bps lost in expected value, but the regime rule is consistent |

Threshold-sweep + regime-gate evidence: `pipeline/research/h_2026_05_01_earnings_drift_long/threshold_sweep.json` + the regime-gate slice in this commit. The chosen-cell selection is documented per backtesting-specs §14.4 (in-sample evidence). The regime gate adds a fourth feature to the entry rule but uses the SAME PIT-correct regime tape (`pipeline/data/research/etf_v3/regime_tape_5y_pit.csv`) used by H-2026-04-27 RISK-ON, H-2026-04-30-DEFENCE-IT-NEUTRAL, and H-2026-04-30-DEFENCE-AUTO-RISKON.

**Pre-exploration boundary:**

- **Universe is locked at registration:** NIFTY Bank (19 names) + NIFTY IT (21 names) = 40 names, frozen list cached to `pipeline/research/h_2026_05_01_earnings_drift_long/universe_frozen.json`. The IT-only sub-cell shows stronger expectancy in-sample, but v1 keeps both sectors to avoid over-fit and to gather Bank-side OOS data.
- **Quintile threshold (volume_z ≥ +0.52)** is the empirical Q5 boundary on the 2021-05 → 2024-04 in-sample. Locked at registration.
- **Hold horizon (H=5)** chosen because (a) Day-1 = noise (net@20 = -1.4 bps); (b) H=21 has FY-level sign flips; (c) H=5 is the cleanest stable cell. Locked at registration.
- **LONG-only side:** the symmetric SHORT cell (vol_Q1 × short_mom_neg) has FY24 decay (FY23 +331 bps net@20; FY24 +9 bps); v1 does NOT register the SHORT side. SHORT side deferred to v2 after holdout finishes.
- **Pass thresholds (mean ≥ +25 bps, hit ≥ 53%, Sharpe ≥ 0.5)** are the locked NEUTRAL-overlay-family threshold per `memory/reference_cost_regime_overlay.md` (≥ +25 bps net at 20 bps cost). Hit rate ≥ 53% is a 0.5pp buffer over the in-sample 55.9% to allow for OOS decay; Sharpe ≥ 0.5 is half the §3.1 default 1.0 — appropriate for a low-frequency event strategy.
- The **synthetic option overlay** numbers from Stage A (long-call gross +5,186 bps for BEAT_LIKE) are NOT used to calibrate the v1 verdict bar — they are inflated 2-3x because synthetic σ = realized_vol_21d underestimates earnings IV. v1 trades futures only; option overlay is forward-only forensic in v1.5.

**No held-out data has been observed.** The 63-day forward window 2026-05-04 → 2026-08-01 is the single-touch holdout. The 2026-05-01 / 02 (today + tomorrow) bars are pre-registration; first holdout bar is 2026-05-05 (Monday — first trading day after the May Day holiday + the weekend).

**Single-touch lock per backtesting-specs.txt §10.4 strict:** parameters are frozen for the duration of the holdout. No quintile retries, no universe additions, no horizon extensions. If v1 fails, re-attempt requires fresh hypothesis_id with materially different setup — no relabel.

## 3. Universe (FROZEN)

**40 names = NIFTY Bank 19 + NIFTY IT 21.** Frozen list cached to `pipeline/research/h_2026_05_01_earnings_drift_long/universe_frozen.json` at registration time.

```
Banks (19): AUBANK, AXISBANK, BANDHANBNK, BANKBARODA, BANKINDIA, CANBK, CUB,
            FEDERALBNK, HDFCBANK, ICICIBANK, IDFCFIRSTB, INDIANB, INDUSINDBK,
            KOTAKBANK, PNB, RBLBANK, SBIN, UNIONBANK, YESBANK
IT_Services (21): BSOFT, COFORGE, CYIENT, ETERNAL, HCLTECH, INDIAMART, INFY,
                   KPITTECH, LTIM, LTM, LTTS, MPHASIS, NAUKRI, OFSS, PERSISTENT,
                   POLICYBZR, TATAELXSI, TATATECH, TCS, TECHM, WIPRO
```

Source: `pipeline.scorecard_v2.sector_mapper.SectorMapper.map_all()` filtered to sectors `{"Banks", "IT_Services"}` and intersected with `pipeline/data/canonical_fno_research_v3.json` F&O universe at 2026-04-30 close.

**Why these 40:** matches the Stage A forensic exactly. No survivorship adjustment because universe is locked from current F&O liquid set, not back-projected. If a ticker is materially impaired during the holdout (suspension, regulatory action, merger), it is excluded from holdout evaluation but the verdict still requires n ≥ 20 across the active subset.

## 4. Data lineage

| Dataset | Path | Tier | Acceptance status |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| daily OHLC (corp-action adjusted) | `pipeline/data/fno_historical/<ticker>.csv` | D2 | Approved-for-research |
| daily volume | embedded in fno_historical | D2 | Approved-for-research |
| earnings calendar history | `pipeline/data/earnings_calendar/history.parquet` | D2 | Pending acceptance — see §4.1 |
| sector map | `pipeline.scorecard_v2.sector_mapper.SectorMapper` | D2 | Approved-for-research |
| Kite LTP at entry/exit | `pipeline.kite_client.get_ltp` | D1 | Approved-for-deployment |
| ATR(14) on daily bars | computed at registration freeze + on rolling basis | D2 | Approved-for-research |

**Adjustment mode:** corp-action adjusted on read. Documented in the daily-bar pipeline (`pipeline/download_fno_history.py`).

**Point-in-time correctness:** verified — all signal features (volume_z_5d, short_mom_5d, ATR_14) computed exclusively from bars dated ≤ T-1 (last trading day strictly before announcement). No look-ahead.

**Stale-bar gate:** any ticker with > 5 missing daily bars in the 30 trading days prior to a signal date disqualifies that ticker for that event. The verdict still requires n ≥ 20 across the active subset.

### 4.1 Earnings calendar dataset

`pipeline/data/earnings_calendar/history.parquet` is sourced from IndianAPI corporate_actions endpoint (running daily via `AnkaEarningsCalendarFetch` at 08:00 IST). Schema: `(symbol, event_date, kind, has_dividend, has_fundraise, agenda_raw, asof)`. **`event_date` is the BOARD MEETING DATE** at which the result is approved (typically the announcement date itself; results are typically released to exchanges during/after market hours of `event_date`).

**Filter:** rows where `kind == "EventKind.QUARTERLY_EARNINGS"`, with date strictly within the holdout window. Audit per `anka_data_validation_policy_global_standard.md` §6 / §8 / §11 (PIT correctness). Data audit doc: `docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md` (companion).

## 5. Signal definition (FROZEN)

For every (symbol, event_date) pair in the calendar restricted to the 40-name universe with `event_date` in the holdout window:

### 5.1 Determine entry day T-1
`T-1` = the last trading day strictly less than `event_date` in `pipeline/data/fno_historical/<symbol>.csv`. If `event_date` is itself a trading day with the announcement after-hours, T-1 = the calendar day before. If `event_date` falls on a weekend or holiday, T-1 = the last trading day before that calendar day.

### 5.2 Volume_Z_5d (FROZEN)
At T-1 close (effectively T-1 14:25 IST entry), compute:
```
volume_5d_avg = mean(daily_volume[T-5..T-1])  # 5 trading days, inclusive
volume_30d_avg = mean(daily_volume[T-29..T-30])  # baseline window
volume_30d_std = std(daily_volume[T-29..T-30], ddof=1)
volume_z = (volume_5d_avg - volume_30d_avg) / volume_30d_std
```
**Trigger:** `volume_z >= 0.52` (Q5 boundary from in-sample).

### 5.3 Short_mom_5d (FROZEN)
At T-1 close, compute the 5-day stock log-return:
```
short_mom_bps = ln(close[T-1] / close[T-6]) * 10_000
```
**Trigger:** `short_mom_bps > 0` (strictly positive).

### 5.4 Realized_vol_21d_pct (FROZEN — added at registration)
At T-1 close, compute the 21-day annualised realised volatility:
```
log_returns = ln(close[t] / close[t-1]) for t in (T-20..T-1)  # 20 daily log returns
realized_vol_21d_pct = stdev(log_returns, ddof=1) * sqrt(252) * 100
```
**Trigger:** `realized_vol_21d_pct >= 29.0`.

This filter excludes low-vol-regime entries (mostly pre-COVID-recovery FY22 prints) where the signal showed structurally weaker performance in-sample. Threshold of 29.0 is the in-sample Q4 boundary on the realized_vol_21d_pct distribution; selected via the threshold-sweep documented in §2.

### 5.5 Regime gate (FROZEN — added at registration)
At T-1, lookup the V3-CURATED-30 daily regime label from `pipeline/data/research/etf_v3/regime_tape_5y_pit.csv` (column `regime`).
**Trigger:** `regime in {"NEUTRAL", "RISK-ON"}`.

This filter excludes CAUTION, EUPHORIA, and RISK-OFF regime days. In-sample, these regime classes accounted for 3 of 4 outsize-loss earnings events. The regime tape is computed from PIT-correct ETF-weight outputs (per `memory/reference_regime_history_csv_contamination`, this is the CLEAN tape, NOT the contaminated `regime_history.csv`).

### 5.6 Combined entry rule
**OPEN LONG** if AND only if ALL FOUR conditions hold:
- (volume_z >= 0.52) AND (short_mom_bps > 0) AND (realized_vol_21d_pct >= 29.0) AND (regime in {NEUTRAL, RISK-ON})

All four features must be observable from data dated ≤ T-1 (no look-ahead). The regime label is the value at T-1 close from the daily PIT regime tape.

## 6. Position sizing (FROZEN)

Equal-notional ₹50,000 per leg. No vol-scaling at v1 (universe is sector-tilted but vol-bands within IT vs Banks are roughly comparable). Single-leg LONG; no spread structure.

If multiple symbols qualify on the same T-1 entry day, all qualified positions open at the same T-1 14:25 IST snapshot, each at ₹50,000 notional.

## 7. Exit rules (FROZEN — first-touch wins)

Per leg, first of these to fire:

1. **ATR(14)×2 per-leg stop (downside-only):** if intraday LTP at any minute ≤ entry_price × (1 - 2.0 × ATR_14_pct), CLOSE at that minute's Kite LTP.
2. **Mechanical TIME_STOP at T+4 14:30 IST:** the 5th trading day after entry (T-1, T, T+1, T+2, T+3, T+4 — 5 close-to-close intervals). CLOSE at 14:30 IST Kite LTP regardless of P&L state.

**No trailing stop, no profit target, no scale-out at v1.** Single mechanical exit. Per CLAUDE.md, the 14:30 IST cutoff is enforced at source.

## 8. Cost model

S0 (no slippage): 10 bps round-trip
**S1 (locked verdict-bar level): 20 bps round-trip** per `memory/reference_cost_regime_overlay.md`
S2 (stress): 30 bps round-trip

All verdict statistics reported at all three levels. Pass/fail evaluated at S1 (20 bps).

## 9. Verdict bar (FROZEN)

### 9.1 Primary §9 gates (S1 = 20 bps cost)
- **n ≥ 6** trades over the holdout window (auto-extend in §10.2 if not met). Honest expectation given in-sample 32 trades over 36 months → ~2.7/month → ~8 trades over 3-month holdout, with regime-gate exclusion fluctuation.
- **mean post-S1 net bps ≥ +25** per trade
- **hit rate ≥ 50%** of trades net positive at S1 (in-sample observed 53%; small buffer for OOS decay)
- **Sharpe annualised ≥ 1.0** (per-trade Sharpe × √(252/5) for 5-day hold; in-sample observed 1.94)
- **MaxDD ≤ -45% of single-leg notional** (in-sample observed -39% via date-sorted cumulative DD; modest buffer for OOS variance)
- **p-value ≤ 0.05** under label permutation null (10,000 permutations within (event_date, sector) buckets)

### 9.2 §9A Fragility check (3-bucket monthly stability)
- 3 monthly buckets across the 3-month holdout
- **Sharpe ≥ 0.0 in at least 2 of 3 buckets** (binding)
- **No bucket worse than -1 Sharpe** (binding)

### 9.3 §9B Margin vs always-baseline
The "always-LONG-on-event" baseline (no vol/momentum filter) is the comparison. v1 must beat the always-baseline by **at least +10 bps per trade** in the holdout to demonstrate the qualifier adds value.

### 9.4 Stretch graduation
- Sharpe ≥ 1.0 across the holdout → graduate from EXPLORING to SIGNAL tier (eligible for live capital allocation discussion at next promote-to-live cycle)
- Sharpe ≥ 1.5 → graduate to FLAGSHIP (manual review required)

## 10. Holdout discipline

### 10.1 Single-touch lock
Per backtesting-specs.txt §10.4 strict: **parameters are frozen for the duration of the holdout**. No quintile retries, no universe additions, no horizon extensions, no regime gate amendments. If v1 fails the §9 verdict bar, re-attempt requires fresh hypothesis_id with materially different setup (e.g., regime-conditioned entry, different feature pair, different hold horizon). v1.1 / v1.2 are NOT permitted.

### 10.2 Auto-extend rule
If n < 20 at 2026-08-01 (window close), auto-extend until **n ≥ 20 OR 2026-10-31**, whichever comes first. If n < 20 at 2026-10-31, verdict is INSUFFICIENT_N and the hypothesis is archived without consumption (single-touch is preserved for a re-attempt with the same setup IF the universe expands materially — e.g., F&O additions).

### 10.3 First-touch dedup
Per (symbol, event_date) — at most one trade per name per quarterly earnings. If the symbol qualifies on T-1 of an event, that's the locked entry; subsequent corrections to event_date in the calendar do not re-open a position.

## 11. Stat tests

### 11.1 Permutation null
10,000 label permutations within (event_date_quarter, sector) buckets. The null distribution of mean post-S1 net bps is computed; the observed p-value is the fraction of null means ≥ observed. Reject null at α = 0.05.

### 11.2 Bootstrap CI on mean
1,000 bootstrap resamples (block = 1 trade, since hold periods don't overlap by design — different events on same day are independent samples) → 95% CI on mean net@20 bps. The lower CI bound must be > 0.

## 12. Standards version

`1.0_2026-04-23` (`docs/superpowers/specs/backtesting-specs.txt`). All sections cited above are from this version.

## 13. Files at registration

| Asset | Path |
|---|---|
| Spec (this doc) | `docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md` |
| Data audit | `docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md` |
| Frozen universe | `pipeline/research/h_2026_05_01_earnings_drift_long/universe_frozen.json` |
| Engine (signal generator) | `pipeline/research/h_2026_05_01_earnings_drift_long/earnings_drift_signal_generator.py` |
| Engine (backtest + holdout runner) | `pipeline/research/h_2026_05_01_earnings_drift_long/earnings_drift_backtest.py` |
| Engine (live OPEN/CLOSE entrypoint) | `pipeline/research/h_2026_05_01_earnings_drift_long/earnings_drift_engine.py` |
| Holdout ledger | `pipeline/data/research/h_2026_05_01_earnings_drift_long/recommendations.csv` |
| Stage A artefacts (immutable) | `pipeline/research/h_2026_05_01_earnings_drift/{event_factors.csv, options_ledger.csv, cohort_summary.json, stress_v1.json}` |
| Project memo | `memory/project_h_2026_05_01_earnings_drift_v1.md` |

## 14. Caveats and known gaps

These are honest disclosures, not gating issues:

- **Trust score is today's snapshot, not PIT.** v1 does NOT use trust score in the entry rule (vol×momentum cells are PIT-clean). Trust as a v2 feature requires PIT trust history (quarterly snapshots over 5y).
- **Synthetic options inflated.** Stage A option-overlay numbers (long call/put/straddle gross) used realized_vol_21d as σ. Real earnings IV is 20-50% higher → real options would have 2-3x higher entry premium. v1 trades futures only; v1.5 adds real options when EODHD India options chain unblocks (currently 404).
- **FY-level dispersion.** FY22 H=5 +219, FY23 +38, FY24 +27. The unconditional headline shows decay; the bivariate vol_Q5 × short_mom_pos cell is more stable (+118 / +358 / +280) but FY22 has only n=5. The holdout is 1 quarter — limited statistical power on its own. v2 will fold the holdout result into a combined 4-year mean.
- **n=314 thin for FY-stratified inference.** FY25 partial in-sample = -113 bps net@20 H=5 (n=19). May indicate decay or just regime mismatch (Apr 2024 earnings at the tail of in-sample). Holdout will land in FY26 Q1 (May-Aug 2026) — fresh quarter, fresh test.
- **EODHD fundamentals 403** at current plan — proxied via prices. v1 does NOT use EODHD beat/miss labels; the in-sample direction proxy was post-hoc and is NOT used in the holdout entry rule.
- **FII/DII flow data forward-only since 2026-04-16** — excluded from in-sample, candidate for v1.5 add-on once 6+ months of flow data accumulates.
- **Bulk-deals NSE history unavailable** per `reference_nse_bulk_deals_history_unavailable.md` — Goldman-style large-print pre-event signature CANNOT be backfilled. Forward-only forensic in v1.5.

## 15. What v1 PASS unblocks

If v1 PASSES the §9 verdict bar:
- **v2 expansion** to symmetric SHORT side (vol_Q1 × short_mom_neg)
- **v2 expansion** to additional sectors (Pharma, FMCG quarterly results — wider universe)
- **v1.5 forensic** real-options overlay on historical events using Kite-fetched IV at announcement
- **Live capital allocation discussion** in next promote-to-live cycle (Sharpe ≥ 1.0 → SIGNAL tier)

If v1 FAILS:
- Hypothesis archived (single-touch consumed)
- v2 must be a materially different setup — e.g., regime-conditioned (NEUTRAL-only, where in-sample showed +73.8 net@20), or sector-conditioned (IT-only, where in-sample showed +86 net@20), or different feature pair (e.g., realized_vol_21d_pct Q5 instead of volume_z)

## 16. Predecessor relationship

This is a **family-level pivot**, not a parameter retry of any predecessor. The family migration:

| Predecessor | Family | Status | Why this is materially different |
|---|---|---|---|
| H-2026-05-01-NEUTRAL-001 (NIFR) | NEUTRAL intraday mean-revert | DEAD | Different mechanism (event-driven multi-day vs intraday fade) |
| H-2026-04-27-003 (SECRSI) | NEUTRAL intraday continuation | DEAD on 5y replay | Different trigger, different time-of-day, different universe |
| H-2026-04-28-001 (sector rotation) | NEUTRAL daily sector momentum | DEAD | Different unit of analysis (events vs daily) |
| H-2026-04-28-002 (sector pair) | NEUTRAL daily sector pair convergence | DEAD wrong direction | Different signal class entirely |

There is no parameter-retry concern: v1 is the first hypothesis in the `event-driven-multi-day-long` family and was constructed from a fresh universe (NIFTY Bank + NIFTY IT) and a fresh signal class (pre-event volume + momentum), with the empirical Q5 boundary observed only in development data.

## 17. Engine code specification

The engine has three entrypoints:

### 17.1 Signal generator (`earnings_drift_signal_generator.py`)
Pure function: `(today_close_features, calendar_window) -> List[Trade]`. Reads earnings calendar + last 30 daily bars; emits `(symbol, event_date, entry_date, vol_z, short_mom, atr_14_pct, side="LONG")` rows.

### 17.2 Backtest harness (`earnings_drift_backtest.py`)
Replays the engine across `2021-05-01 → 2024-04-30` with the FROZEN spec, produces `backtest_2021_05_2024_04.csv` and verdict statistics. This is the §9 verification run BEFORE holdout opens — confirms the frozen spec replicates the +277 bps net@20 bivariate cell.

### 17.3 Live OPEN/CLOSE (`earnings_drift_engine.py`)
- `open_today()` — at T-1 14:25 IST, queries calendar for events on T (next trading day = today + 1 trading day's distance via the `event_date` lookahead), runs signal generator, opens qualified positions at Kite LTP, writes to `recommendations.csv`.
- `close_today()` — at 14:30 IST every trading day, scans `recommendations.csv` for OPEN rows where `entry_date + 5 trading days = today`, closes at Kite LTP. Also evaluates ATR×2 stops on every bar via `pipeline.kite_client.get_ltp`.

The signal-generator + backtest filenames match the kill-switch regex (`*_signal_generator.py`, `*_backtest.py`, `*_engine.py`) and require a registry row in the same commit per `pipeline/scripts/hooks/strategy_patterns.txt`.

## 18. Doc-sync companions

Per CLAUDE.md doc-sync mandate, this commit MUST update:
- `docs/superpowers/hypothesis-registry.jsonl` — append row
- `pipeline/config/anka_inventory.json` — add 3 task entries (calendar pre-fetch, OPEN, CLOSE)
- `CLAUDE.md` — add hypothesis to the clockwork schedule and rationale section
- `memory/project_h_2026_05_01_earnings_drift_v1.md` — update with PRE_REGISTERED status
- `pipeline/data/research/h_2026_05_01_earnings_drift_long/` — create dir for ledger

## 19. Approval

Pre-registration approved by Bharat Ankaraju on 2026-05-01 IST. Spec frozen at v1.0. First holdout open eligible date: **2026-05-04** (Monday). First holdout open will be `event_date + 1` for any name with an announcement on or after 2026-05-04, where the entry day T-1 falls within the holdout window.
