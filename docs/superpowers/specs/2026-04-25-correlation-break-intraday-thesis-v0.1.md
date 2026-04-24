# Intraday Correlation-Break Replay — v0.1 Pre-Registration (Sector-Gated)

**Date:** 2026-04-25
**Branch:** `feat/phase-c-v5`
**Previous anchor:** v0 thesis `docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis.md` @ `9cab5d4`; v0 results `docs/superpowers/specs/2026-04-25-correlation-break-intraday-results.md` @ `7901b69`
**Authors:** Anka Research (Bharat Ankaraju) + Claude Opus 4.7 assistance
**Status:** PRE-REGISTRATION. Frozen before any v0.1 results are computed.

---

## Abstract

The v0 backtest of the intraday correlation-break setup returned a FAIL verdict, but the result was invalidated by a date-range implementation bug: the replay sampled only a single trading day (2026-04-24) rather than the intended 60-session window. A post-hoc forensic audit of 40 live Phase C paper-trade records over 2026-04-20…2026-04-24 overturned two core assumptions of v0. First, the *same-day* closure assumption was wrong — of 40 trades, the 19 that were held overnight produced an average P&L of +3.74% (win rate 17/19) while the 11 that closed same-day averaged −0.64% (win rate 1/11). Second, the v0 mechanism model — symmetric mean-reversion of a peer-cohort gap — misdescribed the mechanics. Cross-referencing each trade against its NSE sector index showed an average **alpha-vs-sector of +2.44%** across 23 overnight trades; the strongest residuals occurred where the sector itself barely moved while the named stock cratered (UNIONBANK +9.22%, APLAPOLLO / VEDL +4.60%, IEX +7.02%, CROMPTON / HAVELLS / BLUESTARCO +3.03%). We restate the mechanism as **pent-up demand gated by sector permission**: a σ > 1.5 laggard carries a stored positional imbalance that resolves toward the sector's direction when the sector provides directional support at or near the entry bar. This thesis pre-registers the v0.1 test of that mechanism over 60 trading sessions with a sector-alignment gate, an alpha-vs-sector primary metric, and a symmetric falsifier that re-runs the same sample *without* the gate.

---

## §1 Motivation

v0 hypothesized that the gap between a stock and its peer-cohort regime-conditional expectation would close symmetrically within the trading session, yielding an intraday edge net of 20 bps round-trip costs. That model failed on two grounds: the implementation did not sample the 60-day window, and the live forensic evidence shows the gap closure is *not* symmetric — it resolves directionally, with resolution timing biased toward the overnight window rather than within-session. Forensic findings that motivate v0.1:

1. **Hold-duration stratification** (n=40): same-day trades −0.64% average (1 win / 11 total); overnight trades +3.74% average (17 wins / 19); 2-day holds +2.78% (5 / 6); still-open 2+ night +2.22% (4 / 4). Same-day exit systematically loses; overnight exit systematically wins.
2. **Sector alpha attribution** (n=23 overnight): raw stock move −2.73%, sector index move −0.72%, NIFTY 50 move −0.79%, **α vs sector +2.44%**, **α vs NIFTY 50 +2.40%**. The sigma setup's alpha is cross-sectional within a sector, not pure beta.
3. **Sector-support conditionality** (anecdotal): the three losing overnight trades (PATANJALI, TMPV 04-20, KAYNES) occurred where the sector index moved strongly against the sigma direction. Wins clustered where sector either moved with the sigma direction or was flat.
4. **Earnings-week contamination**: 9 of 17 overnight winners had a Q4FY26 earnings catalyst during the hold window. The sigma setup appears to implicitly pre-position into pre-earnings weakness. v0.1 does not filter on earnings; it stratifies reporting by earnings-week membership.

## §2 Mechanism (restated for v0.1)

**M1. Pent-up demand.** A stock classified OPPORTUNITY_LAG with `|z| > 1.5` has drifted materially from the regime-conditional peer-cohort drift. The interpretation is not that peer cohort has mispriced; it is that the named stock has accumulated a positional imbalance — shorts not yet covered, longs not yet filled — relative to where its regime + sector fundamentals say it should be.

**M2. Sector as the release valve.** The resolution direction of the imbalance is the direction the sector index is already moving. Absent sector support, the imbalance can persist for days (the stock drifts sideways as peers move without it). With sector support, the imbalance resolves — often within one overnight window as post-close positioning absorbs the residual.

**M3. Asymmetric resolution.** Resolution does not require peers to retreat toward the laggard. The dominant mode is the laggard catching up to peers *in the direction peers already moved*. This is why same-day mean-reversion framings (v0) failed and overnight framings (live) succeed.

**M4. Earnings as an accelerant, not a requirement.** Q4 earnings prints in 2026-04-20…2026-04-24 provided catalytic acceleration. The mechanism is expected to hold outside earnings windows but at smaller effect size; this is an empirical question v0.1 will answer via stratification.

## §3 Data & sample

- **Universe:** all F&O-listed NSE tickers with a valid entry in `pipeline/autoresearch/reverse_regime_profile.json` and a sector mapping in the table in Appendix A.
- **Price source:** Kite Connect historical 1-minute bars, 60-day retention.
- **Window:** 60 trading sessions ending 2026-04-24, inclusive. Approximate start 2026-02-02.
- **Sector index source:** same Kite historical endpoint at 1-minute interval for 16 NSE sector indices (see Appendix A). For lookback days beyond the 1-min retention we fall back to daily close.
- **Regime assignment:** `pipeline/data/regime_history.csv` at day open.
- **Profile vintage:** `reverse_regime_profile.json` as it existed at the scan time (no forward-profile leakage). Since the profile is updated only by the overnight batch, using the latest on-disk profile is acceptable for this 60-day window; any profile-refresh events during the window will be flagged in the results artifact.

## §4 Hypotheses

Let π_i denote the signed net P&L of trade *i* in bps after 20 bps round-trip transaction cost. Let σ_i denote its sector-index return over the trade's hold period. Define **α_i = π_i − (−σ_i) for SHORT trades and α_i = π_i − σ_i for LONG trades** — i.e. the trade's P&L minus the sector-beta component in the trade's own direction.

- **H0 (null):** E[α_i] ≤ 0. The sigma setup produces no alpha over simply taking the sector-beta trade.
- **H1 (primary):** E[α_i] > 40 bps net (after costs). The sigma setup produces meaningful cross-sectional dispersion alpha.
- **H1a (mechanism sub-hypothesis — gated sample):** Within trades where the sector-alignment gate (§5.2) passes, E[α_i | gate=pass] > 40 bps.
- **H1b (mechanism falsifier — ungated sample):** Within trades where the gate would have *failed*, E[α_i | gate=fail] ≤ 0 (or significantly below the gated sample).

If H1a holds and H1b fails (gated wins, ungated loses), the sector-alignment mechanism is supported. If both H1a and H1b hold at comparable levels, the gate contributes no information and the claimed mechanism is rejected — the edge must be from something else (or absent).

## §5 Methodology

### §5.1 Trigger

Every trading day, at each 15-minute scan from 09:30 to 14:30 IST:

1. For each universe ticker, compute today's return `R_t = (close_t / open_0915 − 1) × 100`.
2. Load regime + profile; compute `E_t` and `S_t` as in `reverse_regime_breaks.py:446-451`.
3. Compute `Z_t = (R_t − E_t) / S_t` (floor `S_t` at 0.1% as in the live engine).
4. Call `classify_event_geometry(E_t, R_t)`; retain triggers with `geometry == "LAG"` AND `|Z_t| > 1.5`.
5. Direction = `SHORT` if `E_t < 0`, `LONG` if `E_t > 0`. No trades when `|E_t| < 0.1%`.

### §5.2 Sector-alignment gate (the new v0.1 rule)

Given the trigger's ticker, look up `sector = TICKER_SECTOR_MAP[ticker]`. Compute the sector index's return at the scan time:

`σ_now = (sector_price_at_scan / sector_open_0915 − 1) × 100`

Gate passes when:

- For a SHORT trigger (E_t < 0): `σ_now ≤ +0.3%` (sector is down, flat, or only mildly up — permission granted).
- For a LONG trigger (E_t > 0): `σ_now ≥ −0.3%` (sector is up, flat, or only mildly down).

If the gate fails, the trigger is recorded and classified as `GATE_BLOCKED`, and **no position is taken**. These triggers contribute to the falsifier sample only.

### §5.3 Entry

If the gate passes, schedule entry at the NEXT 15-min scan's close (kills look-ahead). If the trigger occurs at the 14:30 final scan, the trade is not taken (no next scan in the session). Record `entry_scan`, `entry_price`, `sector_at_entry`, `nifty_at_entry`.

### §5.4 Hold & intra-hold gate re-check

Per live behavior: at each subsequent 15-min scan during the trade's day-of-entry, re-evaluate:

- **Hard stop:** if per-minute low/high breaches `entry_price ± 1.5 × S × entry_price / 100` (SHORT: high ≥ stop; LONG: low ≤ stop), close at stop price. Exit reason `STOP`.
- **Sector-flip exit:** at each 15-min scan, recompute sector cumulative return since entry. If the sector has moved ≥ 0.5% *against* the trade direction since entry (SHORT: sector_ret_since_entry ≥ +0.5%; LONG: sector_ret_since_entry ≤ −0.5%), close at this scan's close. Exit reason `SECTOR_FLIP`.
- **Z_CROSS:** if `|Z_t| < 1.5` at a scan strictly after the entry scan, close at this scan's close. Exit reason `Z_CROSS`.

### §5.5 Exit (T+1 default)

If no earlier exit rule fires, hold overnight. At 09:43 IST on day T+1 (first scan after open), force close at that scan's close. Exit reason `T1_CLOSE`.

**If no bars exist on day T+1 (holiday),** close at the next available trading day's 09:43 scan and flag the trade as `SKIP_CLOSE` in the artifact.

### §5.6 Cost model

Round-trip 20 bps deducted from gross P&L. Gross P&L uses entry and exit scan closes (not intrabar mids); STOP uses stop price directly (conservative for shorts in a gap-down, conservative for longs in a gap-up).

### §5.7 Per-trade record fields

`trade_id, ticker, sector, regime, prev_regime, trigger_time, trigger_z, trigger_Et, trigger_St, gate_pass, sector_at_entry, entry_time, entry_price, stop_price, exit_time, exit_price, exit_reason, hold_minutes, gross_pnl_pct, net_pnl_pct, sector_return_over_hold, nifty_return_over_hold, alpha_vs_sector_pct, alpha_vs_nifty_pct, sigma_bucket, earnings_window_flag, direction`.

## §6 Power, sample, and pre-committed stratifications

### §6.1 Power

Live forward shadow gives E[α] ≈ 244 bps at σ ≈ 180 bps across 23 trades. Under H1 = 40 bps, using a Welch one-sided t-test with α = 0.05, the MDE at N = 60 trades is ≈ 40 bps (matches the hypothesis threshold). At N = 120 trades the MDE drops to ≈ 28 bps. Expected N over 60 sessions in CAUTION/NEUTRAL regime is ~60-200 triggers *after* gate filtering; the full-60-day run should exceed N = 60 unless the gate filters too aggressively.

### §6.2 Cluster-robust SE

Treat each (ticker, entry_date) as a cluster. Compute the mean of α_i within each cluster and the SE across clusters; this is conservative against same-day multi-ticker correlation (e.g. five IT shorts on a single IT-down day).

### §6.3 Pre-committed stratifications (reported, not gating)

Report primary α_i statistics additionally split by:

- **Regime at entry:** NEUTRAL / CAUTION / RISK-OFF (other regimes if they appear).
- **Direction:** LONG vs SHORT.
- **σ bucket:** [1.5, 2) / [2, 3) / [3, ∞).
- **Sector:** each of the 16 mapped sectors with N ≥ 3.
- **Earnings-window flag:** within 5 calendar days of the ticker's Q4FY26 earnings date (constructed from `news_verdicts.json` and `news_events_history.json` hits).

## §7 Verdict rule (FROZEN)

Evaluated in the following order; the first condition met determines the verdict.

1. **FAIL** if cluster-robust mean α_i < 20 bps OR one-sided p-value against H1 ≥ 0.10.
2. **WEAK** if cluster-robust mean α_i ∈ [20, 40) bps AND one-sided p ∈ [0.05, 0.10).
3. **PASS** if cluster-robust mean α_i ≥ 40 bps AND one-sided p < 0.05 AND hit rate ≥ 0.50.
4. **PASS-CONDITIONAL** if the above PASS condition is satisfied only after excluding earnings-window trades — reported but not promoted to live.

Secondary sub-hypothesis gates (all must also be met for PASS to be claimed cleanly):

- **H1b falsifier:** `mean α_i | gate=fail` < `mean α_i | gate=pass` by at least 25 bps. If the ungated sample is comparably profitable, the gate is uninformative and PASS downgrades to WEAK regardless of the primary metric.
- **No-lookahead invariant:** reported `entry_price == next_scan_close`, never open-snap. Any row that violates this is logged and excluded; more than 1% such rows voids the run.

## §8 Falsifier detail

Every trigger that *would* have entered a trade but was blocked by the sector-alignment gate (§5.2) is recorded as a paper trade anyway in a parallel artifact (`intraday_break_replay_60d_ungated.parquet`). These trades use the same entry timing rule, same exit ladder, same cost model. The ungated artifact is never used for verdict claims; it exists solely to test H1b.

## §9 Identification threats (disclosed)

| Threat | Description | Mitigation |
|---|---|---|
| Earnings-week contamination | 9/17 live winners had Q4 earnings catalysts. The sigma setup may implicitly front-run earnings; outside earnings season the edge may collapse. | §6.3 stratification + §7.4 PASS-CONDITIONAL carve-out. |
| Sector-mapping error | Some tickers (APLAPOLLO, KAYNES) have weak sector fit. Mis-classification biases α toward noise. | Appendix A declares the mapping. Sensitivity test: re-run with NIFTY 50 as the sector benchmark for every ticker; if the overall PASS still holds, sector-mapping is not a critical driver. |
| Profile-vintage leakage | `reverse_regime_profile.json` is refreshed by the overnight batch. Using "current" profile over historical dates introduces look-ahead if the profile materially drifted. | Results artifact records the profile file hash at run time; if the profile was unchanged across the 60-day window (likely — it updates slowly), no leakage. If it changed, flag and discuss. |
| Regime-coverage imbalance | CAUTION regime dominated the live sample. 60-day window may be similarly imbalanced. | §6.3 regime-split reporting. If NEUTRAL N < 10, report NEUTRAL as "insufficient power" rather than a zero finding. |
| Kite bar-availability gaps | Historical 1-min occasionally drops ticks. | Record bar-count per day per ticker; drop (ticker, day) pairs with < 300 1-min bars. |
| Open-snap regression | Live production has open-snap bug (#112). v0.1 replay uses next-scan entry. | Matches live spec, not live bug. Results reflect what the strategy *should* have been doing, not what it was doing. |

## §10 Implementation notes

- Source: `pipeline/autoresearch/intraday_break_replay.py` (extend, do not fork).
- New helpers needed: `sector_return_intraday(sector, from_t, to_t)`, `fetch_sector_1min_bars(sector, date)`.
- The v0 date-range bug (single day sampled): replay controller must iterate `last_n_trading_days(60, end_date=None)` correctly. Add a unit test: `len(days) == 60` and first/last dates match expectation.
- CLI: `python -m pipeline.autoresearch.intraday_break_replay --n-days 60 --gate sector_aligned --output-suffix v0.1`.
- Compute cost: estimate ~200 ticker-days × 60 days × ~30 1-min bars/scan = manageable on the local laptop but batch the Kite calls.
- Results artifact: `pipeline/autoresearch/data/intraday_break_replay_60d_v0.1.parquet` (gated) and `..._ungated.parquet` (falsifier). Summary JSON at `docs/superpowers/specs/2026-04-25-correlation-break-intraday-results-v0.1.md`.

## §11 Pre-registration integrity

This document is committed *before* the v0.1 replay is executed. No results from v0.1 exist at commit time. The verdict rule (§7) and the falsifier definition (§8) are frozen by the commit hash of this file. Any post-hoc change to the verdict rule or the primary metric (α-vs-sector, not raw P&L) voids the pre-registration and requires a separate v0.2 spec.

The 4-day forensic observations reported in §1 are *historical descriptions* of the live paper-trade ledger in `pipeline/data/signals/{open,closed}_signals.json` as of 2026-04-24. They are not data used to fit any parameter in this spec; they motivated but did not select §5.2's 0.3% / 0.5% thresholds, which were chosen on a priori grounds (0.3% ≈ one cost-units of sector noise; 0.5% ≈ two cost-units).

Divergences permitted post-commit without voiding the pre-registration:

- Implementation bug fixes that leave the verdict rule unchanged.
- Additional stratifications added to the reporting (can always add, never remove).
- Exclusion of (ticker, day) observations due to demonstrable data corruption, accompanied by a coverage audit in the results document.

Divergences *not* permitted:

- Changing the 40 bps PASS threshold, the 20 bps FAIL threshold, the α-vs-sector primary metric, or the sector-alignment gate definition.
- Moving the exit time from T+1 09:43 to another bar after observing the ungated falsifier results.

## Appendix A — Sector map

Same as the validated map used in the 4-day forensic analysis (2026-04-25). Full list in `docs/superpowers/specs/2026-04-25-correlation-break-intraday-thesis-v0.1-sector-map.json` (committed alongside). Summary:

| Sector index | Kite token | Representative traded tickers |
|---|---|---|
| NIFTY IT | 259849 | TECHM, MPHASIS, WIPRO, TATATECH, TATAELXSI |
| NIFTY BANK | 260105 | YESBANK |
| NIFTY PSU BANK | 262921 | UNIONBANK |
| NIFTY FIN SERVICE | 257801 | HDFCAMC, MOTILALOFS, NUVAMA, ABCAPITAL |
| NIFTY AUTO | 263433 | EXIDEIND, TVSMOTOR, SONACOMS, TMPV |
| NIFTY METAL | 263689 | VEDL, NMDC, APLAPOLLO |
| NIFTY ENERGY | 261641 | IEX |
| NIFTY OIL AND GAS | 289033 | PETRONET |
| NIFTY FMCG | 261897 | PATANJALI |
| NIFTY PHARMA | 262409 | LAURUSLABS, DIVISLAB |
| NIFTY HEALTHCARE | 288521 | (fallback for pharma) |
| NIFTY CONSR DURBL | 288777 | CROMPTON, HAVELLS, BLUESTARCO |
| NIFTY PSE | 262665 | RECLTD, PFC, BHEL |
| NIFTY REALTY | 261129 | — |
| NIFTY INFRA | 261385 | KAYNES |
| NIFTY 50 | 256265 | (fallback + broad market control) |

## Appendix B — What v0.1 does NOT attempt

- No entry-time experimentation (entry remains next-scan-close).
- No position sizing experimentation (equal notional across trades).
- No multi-leg / spread variants.
- No Phase C `SECTOR_INDEX` replacement of peer-cohort as the σ anchor itself — the setup still uses the regime-conditional peer expectation; the sector index only gates.
- No options overlay.
- No promotion to live trading from this run alone. PASS here is a prerequisite for a separate promotion spec that must include forward-shadow supervision and kill-switch integration.

---

**Signed off:** pre-registration commit made before any v0.1 execution. v0.1 results, when generated, will be committed as a separate document (`…-results-v0.1.md`) that interprets observations against the rules frozen here.
