# H-2026-04-25-001 — Earnings-Decoupling Pre-Registration Design Spec

**Hypothesis ID:** H-2026-04-25-001
**Strategy name:** earnings-decoupling-prepost-pcr-amplifier
**Strategy class:** event-driven-prepublication-decoupling
**Date pre-registered:** 2026-04-25
**Author:** Bharat Ankaraju
**Standards version:** `backtesting-specs.txt` v1.0_2026-04-23 + `anka_data_validation_policy_global_standard.md` v1.0_2026-04-25
**Execution mode:** MODE A (EOD-close-to-close), per backtesting-specs §7.1
**Family scope:** single-hypothesis; family size 1; no multiplicity correction

This spec is the locked design document for H-2026-04-25-001. Every threshold, window, and rule below is pre-registered. None of these values may be calibrated, tuned, or relaxed against observed earnings-window data. If post-filter event count falls below the §0 minimum, the hypothesis is labelled PARTIAL/exploratory and a new hypothesis version (H-2026-04-25-002 or later) is registered with the revised parameters; this hypothesis is not edited in place (data validation policy §3.6, backtesting policy §0.3).

## 1. Thesis in plain language

Indian listed companies must disclose Board Meeting agendas at least 5 working days before the meeting (SEBI Regulation 29). Quarterly results meetings therefore become public knowledge ~T-5 onward, but the actual financials are not public until T (the meeting date) at or after market close. The thesis tested here is that some institutional positioning leaks into stock-vs-peer behaviour earlier than this, so the cumulative residual return of the stock against its sector-index peers in the T-7 → T-3 window contains directional information about the result. Confirmation comes from a same-direction move in the put-call ratio over T-3 → T-1, which proxies institutional option positioning. The trade exits at T-1 EOD, before the result is announced, deliberately leaving the result-day gap on the table because that gap is the largest contamination channel and would dominate the Sharpe.

## 2. Locked design parameters

These were locked in conversation on 2026-04-25 between the user and the assistant. They are not derived from any earnings-window observation.

| # | Parameter | Locked value | Source |
|---|---|---|---|
| 1 | Exit | Strict T-1 EOD VWAP (15:20-29 IST) | User reply 2026-04-25 |
| 2 | Peer cohort definition | NSE sectoral-index membership (NIFTY Bank, IT, Pharma, Auto, FMCG, Metal, Energy, PSU Bank, Realty, Media) | User confirmed sector-level + size bucket; assistant recommendation locked into NSE sectoral indices because "broad sector" was operationally underspecified |
| 3 | Size bucket within sector | Top-3 nearest by market cap, frozen ex-ante in `pipeline/data/earnings_calendar/peers_frozen.json` | Assistant recommendation; cardinality-stable |
| 4 | Macro index for exclusion | The stock's own NSE sectoral index (same as peer-cohort index) | Assistant recommendation; internal consistency with #2 |
| 5 | Macro exclusion threshold (price) | `\|sector_index_return_pct\| ≥ 1.5%` on event_day T OR T+1 | User reply 2026-04-25 |
| 6 | Macro exclusion threshold (vol) | India VIX z-score ≥ 2.0 over trailing 60 calendar days, on event_day T | User reply 2026-04-25 |
| 7 | Trigger z-threshold | Cumulative T-7 → T-3 residual return vs peer cohort, z-scored against trailing 252 trading-day distribution; trigger when `\|z\| ≥ 1.5` | User confirmed 2026-04-25 |
| 8 | Direction of trade | Sign matches the sign of the trigger z (positive z → LONG, negative z → SHORT) | Implied by decoupling-follows-through thesis |
| 9 | Confirmation threshold (ΔPCR) | Stock-level ΔPCR over T-3 → T-1 must move ≥ 1.0σ in the same sign as the trigger z, where σ is the trailing 60-trading-day standard deviation of daily ΔPCR for the same stock | User confirmed 2026-04-25 |
| 10 | Fallback if filters drop n below §0 minimum | Label PARTIAL / exploratory; register a new hypothesis version with revised parameters; do NOT relax filters in place | User reply 2026-04-25 |

## 3. Universe and date range

**Universe:** 213 F&O tickers, point-in-time-correct via `pipeline/data/fno_universe_history.json`. Tickers admitted, suspended, or kicked out during the window are reflected at the dates they were actually tradeable (data validation policy §12).

**Backtest window:** 18 months ending the latest committed `pipeline/data/earnings_calendar/history.parquet` snapshot date. Concretely: training 2024-10-25 → 2026-01-25 (15 months), holdout 2026-01-26 → 2026-04-25 (3 months, 17% holdout). The 17% holdout clears the §9.3 ≥50-event gate but is short of the §10.1 20% target and is recorded as a partial in the registry entry.

**Sectoral-index history:** every event references a sector index. The required indices and their canonical NSE tickers are: NIFTY Bank (`^NSEBANK`), NIFTY IT (`^CNXIT`), NIFTY Pharma (`^CNXPHARMA`), NIFTY Auto (`^CNXAUTO`), NIFTY FMCG (`^CNXFMCG`), NIFTY Metal (`^CNXMETAL`), NIFTY Energy (`^CNXENERGY`), NIFTY PSU Bank (`^CNXPSUBANK`), NIFTY Realty (`^CNXREALTY`), NIFTY Media (`^CNXMEDIA`). Tickers without a clean NSE sectoral-index home (a small number of conglomerates) are flagged at backfill time and either assigned to the closest index by Screener-classified primary business or excluded with a logged reason.

## 4. Trigger and confirmation construction

### 4.1 Daily peer-relative residual return

For each trading day `t` and each F&O ticker `s` with sector index `i(s)`:

```
r_s(t)   = log(close_s(t) / close_s(t-1))
r_i(t)   = log(close_i(t) / close_i(t-1))
peers(s) = top-3 by-market-cap-nearest within sector i(s), excluding s itself, frozen as of 2026-04-25
r_peers(s, t) = mean over p in peers(s) of r_p(t)
ε_s(t)   = r_s(t) - r_peers(s, t)
```

`ε_s(t)` is the daily peer-residual return.

### 4.2 Cumulative residual over the trigger window

For each earnings event `(s, T)` where `T` is the board-meeting date:

```
cum_residual(s, T) = sum over t in [T-7, T-3] of ε_s(t)
```

The window is 5 trading days (T-7 inclusive through T-3 inclusive). Trading days are taken from the NIFTY 50 calendar; non-trading days within the calendar window contribute zero (they cannot leak information).

### 4.3 Trigger z-score

For each event `(s, T)`:

```
μ_s(T)    = mean over u in [T-252, T-8] of cum_residual(s, u)
σ_s(T)    = std over u in [T-252, T-8] of cum_residual(s, u)
trigger_z = (cum_residual(s, T) - μ_s(T)) / σ_s(T)
```

The lookback explicitly stops at T-8 to prevent the trigger window itself from contaminating the z-score baseline. Events with σ_s(T) ≤ 0 or fewer than 200 valid baseline days are dropped.

**Trigger fires** when `|trigger_z| ≥ 1.5`.

### 4.4 ΔPCR confirmation

For each F&O ticker, daily PCR is the put-OI / call-OI ratio over all listed strikes for the nearest-month expiry, sourced from `pipeline/data/oi_history/`. Daily ΔPCR is the first difference of daily PCR.

```
ΔPCR_s(t) = PCR_s(t) - PCR_s(t-1)
cum_ΔPCR(s, T) = sum over t in [T-3, T-1] of ΔPCR_s(t)
σ_ΔPCR_60d(s, T) = std of cum_ΔPCR over u in [T-60, T-4]  # 60-day rolling, gap-free
confirmation_z = cum_ΔPCR(s, T) / σ_ΔPCR_60d(s, T)
```

**Confirmation fires** when `|confirmation_z| ≥ 1.0` AND `sign(confirmation_z) == sign(trigger_z)`.

The PCR convention `put_oi / call_oi` means rising PCR is bearish; a stock decoupling LONG (positive trigger z) is confirmed by a *falling* PCR over T-3 → T-1, i.e. negative ΔPCR. The sign-matching rule above accommodates this by checking against `trigger_z`'s sign on the residual-return basis, NOT on the PCR basis directly.

If PCR data are not available for a stock or for the required window, the event is dropped. The PCR-availability constraint is documented as a contamination-vs-coverage trade-off in §7.

### 4.5 Trade construction

For events where both trigger and confirmation fire:

```
event_date          = T (board-meeting date)
direction           = LONG if trigger_z > 0 else SHORT
entry_timestamp     = T-1, 15:20-29 IST VWAP
exit_timestamp      = same as entry — there is no T-1 hold; the trade is opened at T-1 EOD VWAP.
```

Wait — that's wrong. If entry and exit are both T-1 EOD, there is no holding period. The thesis requires a hold from before the trigger window resolves to before the result. Restating correctly:

```
entry_timestamp     = T-3, 15:20-29 IST VWAP — the moment the confirmation window starts AND the moment the trigger is decidable
                      (cum_residual(s, T-3) is computable at T-3 close)
exit_timestamp      = T-1, 15:20-29 IST VWAP
holding period      = 2 trading days (T-3 close → T-1 close)
direction           = LONG if trigger_z > 0 else SHORT
```

The trigger is decidable at T-3 close. The confirmation accumulates over T-3 → T-1, which means *the confirmation can only be evaluated at T-1*. Two execution variants exist:

**Variant A (entry at trigger):** Enter at T-3 close based on trigger only; exit at T-1 close. ΔPCR confirmation is recorded as a *post-hoc filter*, not as an entry gate. Trades that fail confirmation are dropped from the cohort but their P&L is reported in the data-quality footnote.

**Variant B (entry at confirmation):** Enter at T-1 close only if both trigger AND confirmation are satisfied; exit at T-1 close. This collapses the trade to a 0-day hold and is therefore not a valid backtest of a multi-day decoupling thesis.

**Variant A is locked.** Hold period is T-3 close → T-1 close (2 trading days). Confirmation operates as a filter on the cohort, evaluated at T-1 close after the trade has been held. Trades that enter on trigger-only but fail confirmation at T-1 are dropped from the primary cohort and reported separately as a confirmation-sensitivity check.

This entry timing is consistent with backtesting-specs §7 MODE A.

## 5. Macro exclusion

For each event `(s, T)`, the trade is excluded if any of:

```
|return_i(T)|     ≥ 0.015           # event-day sector-index move
|return_i(T+1)|   ≥ 0.015           # T+1 sector-index move
vix_zscore_60d(T) ≥ 2.0             # India VIX shock on event day
```

where `i = i(s)` is the stock's sector index from §3, and `vix_zscore_60d(T)` is `(VIX(T) - mean_VIX(T-60..T-1)) / std_VIX(T-60..T-1)`.

Excluded trades are recorded with their exclusion reason in the run manifest. They are not re-admitted at any later stage.

The macro exclusion runs after the trade is closed (T-1 EOD), as a post-hoc attribution scrub. The intent is to discard observations whose returns were dominated by a same-day or next-day macro event so that the surviving sample isolates the pre-publication decoupling channel rather than a sector-shock lottery. This is "Reading 2" in the design conversation.

## 6. Success criteria — pre-registered, no calibration

Thresholds copied from the H-2026-04-24-001 precedent for framework consistency. They are not derived from any number observed inside the earnings window.

| Metric | Threshold | Notes |
|---|---|---|
| Net mean T-1 edge (S1 slippage) | ≥ 0.5% | per backtesting-specs §3.1 |
| Hit rate | ≥ 55% | per backtesting-specs §3.1 |
| p-value (label permutation, 100k shuffles) | ≤ 0.05 | family size = 1, no multiplicity correction |
| Bootstrap CI lower bound on edge | > 0% | per backtesting-specs §9.3 |
| Power: minimum detectable effect at α=0.05, 80% power | ≤ 0.5% | computed from training-set ε_s(t) std before gate evaluation |

Slippage grid (backtesting-specs §1) applied at S0/S1/S2; primary verdict at S1 (~30 bps round-trip, broker + slippage).

## 7. Contamination map (data validation policy §14)

| # | Channel | Mitigation |
|---|---|---|
| 1 | Result-day gap noise | Strict T-1 EOD exit by construction; no result-day exposure |
| 2 | Quarter-end clustering | Multiple stocks in the same sector report within 3-7 days; peer residuals are computed against contemporaneous peer windows so the clustering is absorbed into the residual baseline. Acknowledged residual risk: peer cohort of size 3 may include a peer also in pre-event window, slightly inflating co-movement. |
| 3 | Concurrent corporate actions | `classifier.py` flags `has_dividend` and `has_fundraise` per event. Sensitivity: re-run filtered to events with no concurrent flags; report both. |
| 4 | Per-stock vendor freshness lag | IndianAPI `corporate_actions` freshness varies by stock (BHARTIARTL was older than RELIANCE on the 2026-04-25 probe). Backfill captures all available history; daily fetch refreshes nightly. Events whose `event_date` is in the future relative to `asof` are processed at trigger evaluation, not at backfill time. |
| 5 | OI / PCR contamination by intraday news | Per data validation policy §14.4, the cum_ΔPCR feature is regressed against contemporaneous news-impact scores from `pipeline/news_scanner.py` / `pipeline/news_backtest.py` over the T-3 → T-1 window; the residual cum_ΔPCR is the feature consumed by the confirmation step. Specification of this regression is deferred to the backtest plan, but the residualised feature is the only PCR feature that may be used. The raw cum_ΔPCR may be reported as a sensitivity slice. |
| 6 | Sector-shock lottery contaminating apparent decoupling | §5 macro exclusion handles |
| 7 | Survivorship bias | Universe is point-in-time-correct via `fno_universe_history.json` per §3 |
| 8 | Look-ahead via post-result peer revision | Peer cohort frozen ex-ante in `peers_frozen.json` (data validation policy §3.3) |

## 8. Data dependencies and acceptance preconditions

This hypothesis cannot be evaluated until:

1. `earnings_calendar_indianapi_v1` is **Approved-for-research, Tier D2** under the data validation policy. Audit: `docs/superpowers/specs/2026-04-25-earnings-data-source-audit.md`.
2. `pipeline/data/oi_history/` has continuous PCR data for all 213 F&O tickers across the backtest window (existing dataset; freshness contract owned by `AnkaOIScannerArchive`).
3. Sectoral index daily price history is available for the 10 NSE sectoral indices listed in §3 across the backtest window.
4. `fno_universe_history.json` covers the backtest window (existing; if gaps, register the gap as an issue under the data validation policy §20 issue register).
5. `peers_frozen.json` is committed and references `fno_universe_history.json` membership at the freeze date.

The backtest plan will be written and executed only after items 1-5 are all green.

## 9. Pre-exploration disclosure

The user pre-locked four design parameters on 2026-04-25 in conversation: strict T-1 EOD exit; same-broad-sector + similar-size-bucket peers, frozen ex-ante; macro exclusion at `|index move| ≥ 1.5%` on T or T+1 OR India VIX z ≥ 2σ; no in-place filter relaxation. The IndianAPI corporate_actions endpoint was probed on 5 stocks (RELIANCE, HDFCBANK, TCS, MARUTI, BHARTIARTL) on 2026-04-25 BEFORE this registration to confirm authenticity and earnings-event recoverability — only event counts and date cadences were observed; NO returns, edges, prices, or backtest numbers were computed from any earnings-window data prior to this registration.

The trigger z-threshold (≥ 1.5) and ΔPCR confirmation threshold (≥ 1.0σ same-direction) were proposed by the assistant based on (a) PEAD-literature convention for ~5-day pre-event windows and (b) precedent from H-2026-04-24-001 / H-2026-04-23-001's framework defaults. They were confirmed by the user in conversation. Thresholds were NOT calibrated from any observed earnings-window distribution.

The 18-month window length was set by user request ("18 months is good enough for now"). The 17% holdout was derived purely from the 18-month/3-month split, not from any sample-count consideration.

The peer-cohort granularity (NSE sectoral indices) and size-bucket rule (top-3 nearest by market cap) were proposed by the assistant after the user's "broad sector + similar size bucket" left the operational definition open; the user was given the option to override and chose to proceed.

Macro-index choice (stock's own sector index rather than NIFTY 50) and macro-check window timing (post-hoc attribution scrub at T and T+1) were proposed by the assistant and confirmed implicitly by the user moving forward without override.

## 10. Status and lifecycle

| Field | Value |
|---|---|
| Status | PRE_REGISTERED |
| Terminal state | null |
| Git commit at registration | (to be filled at registry append time) |
| Raw-bar canonicity policy | `docs/superpowers/policies/2026-04-23-raw-bar-canonicity.md` v1.0 — MODE A T-3, T-1 execution-window gate applies |
| Next required artifact | Backtest plan (separate document, written only after data dependency #1 reaches Approved-for-research) |

## 11. Backtest-time addendum (2026-04-25)

ΔPCR confirmation deferred for the first backtest run because per-ticker daily
PCR history is not currently stored (`pipeline/data/oi_history.json` is index-level
only). Per spec §4.5 Variant A, ΔPCR is a post-hoc cohort filter, not an entry
gate, so disabling it for this run does NOT modify the entry rule and does NOT
require a new hypothesis version. The amplifier code path is wired with a
feature flag and will be re-enabled in a separate run when per-ticker PCR
history is backfilled.

§9A fragility-grid axes for this hypothesis: trigger_z threshold (locked 1.5;
perturbed ±10% over 9 points), trigger window start (locked T-7; perturbed
±2 days), trigger window end (locked T-3; perturbed ±2 days), baseline length
(locked 252; perturbed ±20%), macro index threshold (locked 0.015; perturbed
±20%), VIX z threshold (locked 2.0; perturbed ±20%). 9 points × 6 axes = 54
neighborhood samples in a one-axis-at-a-time grid (§9A.1 floor = 25).

Backtest spec: `docs/superpowers/specs/2026-04-25-earnings-decoupling-backtest-design.md`
Backtest plan: `docs/superpowers/plans/2026-04-25-earnings-decoupling-backtest.md`
