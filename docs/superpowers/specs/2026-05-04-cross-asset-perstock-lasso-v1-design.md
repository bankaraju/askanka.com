# H-2026-05-04-cross-asset-perstock-lasso-v1 — Per-stock cross-asset elastic-net

**Hypothesis ID:** `H-2026-05-04-cross-asset-perstock-lasso-v1`
**Strategy class:** `per-stock-cross-asset-elastic-net`
**Family scope:** ticker-family, n=101 (BH-FDR-corrected across (stock × direction) cells, 200 → 101 after PRE_HOLDOUT_FIX)
**Standards version:** 1.0_2026-04-23 (`docs/superpowers/specs/backtesting-specs.txt`)
**Spec version:** v1.0 (frozen at registry append) + PRE_HOLDOUT_FIX amendment 2026-05-03

---

## 0. Amendments (post-registration fixes pre-holdout)

### A1: PRE_HOLDOUT_FIX — sector mapping defect, 2026-05-03 13:52 IST

The first VPS deploy on 2026-05-03 produced "0 cells fit" because (a) the runner imported `pipeline.sector_mapper.map_one`, which does not exist (correct API is `pipeline.scorecard_v2.sector_mapper.SectorMapper().map_all()`), and (b) only 11 of the 24 keys in `pipeline/config/sector_taxonomy.json` map to a published Nifty sectoral index (the §5.3 `own_sector_ret_5d` feature requires one). A bare `try/except Exception` in the runner silently swallowed the import error and dropped every ticker.

**Fix landed before holdout opens:**

- New module `pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/sector_mapping.py` owns `SECTOR_TO_INDEX_FILE` (sector_key → CSV file name) and `load_sectoral_index_close` (handles the lowercase `date,close` convention in `pipeline/data/sectoral_indices/*_daily.csv`).
- `runner.py` now imports `SectorMapper` from the correct path, builds `sector_map = SectorMapper().map_all()` once at the top of `main()`, and per-ticker resolves through `index_csv_for_sector()`.
- `preflight.py` Check 1 applies the same filter at universe-freeze time, so `universe_frozen.json` contains only sector-resolvable tickers.
- New test `pipeline/tests/research/h_2026_05_04_cross_asset_perstock_lasso/test_sector_mapping.py` exercises the integration end-to-end and asserts at least 30 universe tickers resolve to a sectoral index — catches the defect class going forward.

**Universe consequence:** 200 → 101 stocks (just clears the §3 minimum of 100). The dropped 99 stocks belong to sectors with no published Nifty index (NBFC_HFC, Capital_Goods, Capital_Markets, Chemicals, Insurance, Infra_EPC, Consumer_Discretionary, Cement_Building, Logistics_Transport, Defence, Telecom, Business_Services). Pre-flight orthogonality re-measured: max abs corr PC × TA = 0.079 (was 0.074 with broader universe — minor shift, still well under 0.4).

**Holdout consequence:** holdout window postponed 1 trading day to **2026-05-05 09:15 IST → 2026-08-05 14:25 IST**. The hypothesis_id retains the 2026-05-04 date as the registration-locked date matching standard convention; first forward trade is 2026-05-05. Auto-extension trigger date follows the same shift: `n_qualifying < 5` at 2026-08-05 → extends to 2026-10-31.

**No scientific parameter changed.** Thresholds, features, ratios, label semantics, ATR stop, position size, and PASS bars are all unchanged. The §3 universe filter was tightened to require a constraint the §5.3 feature already implicitly imposed; this is a defect-class fix, not a results-driven parameter tweak.

The body of this spec retains its original wording (universe ~180-200, holdout 2026-05-04 → 2026-08-04) where the discussion logic is unaffected by the amendment. Operational scheduling references (§7, §10, §15, §16) and the verdict bar in §12 are read with the amended dates and universe size.

---

## 1. Claim

### 1.A Primary unit of inference (governance contract)

**The hypothesis is evaluated at the BASKET level, not the per-cell level.** Specifically:

- For each (stock, direction) **cell**, an elastic-net regularised logistic regression is fit per §8.
- The cell is **qualified** for forward trading iff it clears the §9 gate (mean fold-AUC ≥ 0.55, fold-AUC std ≤ 0.05, BH-FDR p<0.05 across the full cell grid, n predicted-positive ≥ 5 in in-sample-holdout, permutation-null beat ≥ 95%).
- The hypothesis is deemed **PASS** if the BH-FDR-qualified cells *collectively* satisfy the §12 forward criteria (basket-pooled hit-rate ≥ 55%, basket-pooled mean P&L ≥ +0.4% net@S1, comparator ladder cleared, fragility passes, single-touch undisturbed).
- **Non-qualified cells are treated as non-tradeable, not as failed predictions.** The hypothesis does not claim that every (stock, direction) pair has a predictable T+1 direction; it claims that the qualifier pipeline can isolate a tradeable *subset* of cells whose pooled forward edge is positive net of costs.

This framing prevents two specific reporting errors:
1. Conflating "many cells failed the qualifier" with "the model failed at prediction" (it didn't; the qualifier did its job by excluding noisy cells).
2. Conflating "few cells qualified" with "the model failed" (it didn't, if the qualifying basket clears §12).

### 1.B Null expectation bounds (leakage / under-specification tripwires)

| Qualifying-cell count | Interpretation | Action |
|---|---|---|
| **n_qualifying = 0** | No cells survived the gate. Either (a) per-stock cross-asset edge does not exist at this AUC bar, or (b) the gate is mis-calibrated. Concrete genuine-null outcome at v1's strict 0.55/0.05 hurdle. | TERMINAL_STATE = `FAIL_NO_QUALIFIERS`. Single-touch consumed. No re-run with relaxed gates. |
| **n_qualifying ∈ [1, 4]** | Below §12 floor (n_qualifying ≥ 5). Insufficient basket size to test claim. Could be real-but-thin or noise. | TERMINAL_STATE = `FAIL_INSUFFICIENT_QUALIFIERS`. Single-touch consumed. |
| **n_qualifying ∈ [5, 25]** | **Expected range.** Tests the §12 PASS bar honestly. | Proceed to forward verdict. |
| **n_qualifying ∈ [26, 80]** | Above expected band. Possibly genuine (cross-asset block strongly load-bearing) but increases leakage risk. **Triggers automatic §16.6 amplified leakage audit** (see below). | Run amplified audit BEFORE accepting verdict. |
| **n_qualifying > 80** | Approximately ≥ 25% of cells qualifying — implausibly high under the strict 0.55-AUC hurdle. **Strong leakage signal.** | TERMINAL_STATE = `FAIL_LEAKAGE_SUSPECT`. Pause forward holdout. Audit feature library for label-derived contamination, PIT alignment, fold-leakage. Do not declare PASS regardless of basket P&L. |

These thresholds are declared pre-holdout and are NOT amendable post-holdout.

### 1.C Concrete claim (operational form)

For each stock in a frozen F&O universe (continuously listed through 2021-05-04 → 2026-04-30 with adequate liquidity), an **elastic-net regularised logistic regression** trained on:

- 30 foreign-ETF macro features (the V3-CURATED-30 set, lagged by 1 Indian session per §4 PIT alignment) reduced to **K_ETF principal components** explaining ≥ 85% variance,
- 4 Indian macro features (Nifty near-month future, India VIX),
- 6 stock-specific TA features (own sector RS, own ATR/RSI/EMA-distance/volume),

with **exponential-decay sample weights (half-life 90 trading days)** to give recent micro-structure higher weight,

will produce a **basket of qualified (stock, direction) cells** (n_qualifying ∈ [5, 25] expected) whose **pooled** held-out hit-rate ≥ 55% AND **pooled** mean per-trade T+1 09:15→14:25 P&L ≥ +0.4% net of S1 slippage, **with the cell-level qualifier gate (4-fold walk-forward mean fold-AUC ≥ 0.55 AND fold-AUC std ≤ 0.05 AND BH-FDR p<0.05 across the full cell grid) acting as the cell-selection mechanism rather than the verdict mechanism.**

This is a deliberate widening of `H-2026-04-29-ta-karpathy-v1` along the *feature axis* (cross-asset macro added) and the *universe axis* (top-10 NIFTY → full F&O), keeping the daily-bar / T+1-intraday architecture identical. Different feature library + different universe = distinct family per backtesting-specs §0.3.

### 1.D Why logistic classification, not direct return regression

The label is a binary direction-with-magnitude-floor (`y_long = 1{T+1 open-to-close ≥ +0.4%}`), not a continuous return. The choice is deliberate:

- **Trade decision is binary at execution.** The forward trading rule (§10) fires LONG if `p_long ≥ 0.6 AND p_short < 0.4` and is otherwise flat. A continuous return forecast would have to be discretised at execution anyway, and the discretisation threshold is itself a parameter that would need its own holdout — collapsing the decision into the loss function up-front avoids that.
- **Heavy tails and asymmetric outcomes break OLS assumptions.** Daily F&O returns have kurtosis 8-15; OLS minimises squared error, which is dominated by tail days that the strategy actively wants to avoid (ATR×2 stop). Classification with `class_weight='balanced'` makes the loss insensitive to outcome magnitude conditional on direction-with-floor.
- **AUC is a calibration-invariant quality metric** (§9 qualifier). Regression metrics (R², RMSE, IC) are scale-sensitive and conflate "got the direction right" with "got the magnitude right." For a fixed-size paper trade (₹50k notional, ATR×2 stop), only direction matters above the +0.4% floor.
- **At v3, multi-horizon labels** (T+2, T+3, T+5 close-to-close) re-introduce magnitude indirectly via multiple binary thresholds — at that point a regression head becomes worth comparing. **Explicitly deferred to v3.**

This rationale is recorded so v2/v3 designers don't relitigate the classification-vs-regression decision without new evidence.

## 2. Pre-exploration disclosure

**Predecessor 1: H-2026-04-29-ta-karpathy-v1** (still in holdout, verdict 2026-05-29).
- Top-10 NIFTY pilot, ~60 daily TA features, no cross-asset macro.
- Honest expectation 0–3 cells qualify.
- This new hypothesis adds the cross-asset feature block and widens to full F&O — it is **NOT a re-attempt with relaxed gates** on the same universe. Distinct universe (~180 stocks vs 10), distinct feature library (cross-asset macro added, TA library trimmed to 6 base features), distinct model class (elastic-net vs pure-L1 Lasso, with PCA pre-step on ETF block).

**Predecessor 2: H-2026-04-29-intraday-data-driven-v1** (in holdout, verdict 2026-07-04).
- Pooled-Karpathy random search over 6 *intraday* features on NIFTY-50 stocks + index futures.
- That hypothesis is intraday-frequency (15-min bars); this one is daily-frequency (T+1 close-to-close prediction). Different bar resolution = orthogonal feature space.

**Predecessor 3: H-2026-04-24-001 RELIANCE-only TA Lasso** — FAILED (mean walk-forward AUC=0.509). Single-touch consumed and closed.

**Pre-exploration disclosure for this hypothesis:**
- The CURATED-30 ETF set was selected for the V3 regime engine over a sweep on 2024-2026 data. **No claim is made here that those 30 ETFs are the optimal feature set for per-stock prediction.** They are inherited as "the macro panel we already have PIT-clean and budget-funded." This ports an existing, accepted dataset; it does not derive thresholds from observed forward-direction stock data.
- **No held-out post-2026-04-30 data has been observed.** The 65-day forward window starting 2026-05-04 09:15 IST is the single-touch holdout.
- Number of PCA components K_ETF is selected on training-fold data via "smallest K such that cumulative variance ≥ 0.85", **declared formula not observed value** — does not introduce holdout-derived parameter selection.
- Half-life 90 trading days is the framework default, NOT tuned on this hypothesis. §9A fragility re-runs at HL=180 to test sensitivity.

## 3. Universe (FROZEN)

**Construction rule (executable):**
```
For each ticker T in pipeline/data/canonical_fno_research_v3.json:
    if T has continuous bars in pipeline/data/fno_historical/<T>.csv from 2021-05-04 → 2026-04-30:
        if median 60-day ADV ≥ ₹50 crore at 2026-04-30:
            include T
```

**Frozen list** committed alongside this spec at:
`pipeline/research/h_2026_05_04_cross_asset_perstock_lasso/universe_frozen.json`

Expected size: ~150–180 names (precise count fixed at registration commit; PIT aliases per `memory/reference_pit_ticker_list.md` applied for the 5 known active aliases — GMRINFRA→GMRAIRPORT, IDFC→IDFCFIRSTB, TATAMOTORS→TMPV, TATACHEMICALS→TATACHEM, IBULHSGFIN→SAMMAAN).

**Why these:** maximises observation count without introducing survivorship-by-recency bias, and the ₹50cr ADV gate ensures every cell that "qualifies" is actually tradeable at S1=6bps round-trip. Universe is **frozen at registration time**. Materially-impaired names during holdout (suspension, corporate action) are excluded from holdout evaluation but the n_qualifying ≥ 5 gate (§12) still binds.

## 4. Data lineage and PIT alignment

| Dataset | Path | Tier | Acceptance status |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| daily_bars (5y, dividend-adjusted close) | `pipeline/data/fno_historical/<TICKER>.csv` | D2 | Approved-for-research |
| sectoral_indices_v1 | `pipeline/data/sectoral_indices/*.csv` | D2 | Approved-for-research |
| nifty_index | `pipeline/data/india_historical/indices/NIFTY.csv` | D2 | Approved-for-research |
| nifty_near_month_future | `pipeline/data/india_historical/futures/NIFTY_<expiry>.csv` (rolled near-month series) | D2 | Approved-for-research |
| etf_panel_v3_curated | `pipeline/autoresearch/etf_v3_loader.build_panel()` (30 CURATED foreign ETFs) | D2 | Approved-for-research (inherits from V3 regime data acceptance) |
| india_vix_history | `pipeline/data/india_historical/indices/INDIAVIX.csv` | D2 | Approved-for-research |

**Adjustment mode:** dividend-adjusted close on equity/sector/index series. ETF series total-return indexed in source.

### 4.A PIT alignment for cross-asset features (CRITICAL)

NSE closes 15:30 IST = 10:00 UTC. NYSE opens 19:00 IST same calendar day (winter; 18:30 IST summer DST), closes 02:00 IST next morning.

For Indian trading day **D** (NSE 09:15-15:30 IST), the freshest *legitimately-known* US ETF data point at NSE-open is the US session whose **close occurred before NSE-D-open**. That is:

- US-D-1 close (US calendar) = available at ~02:00 IST on Indian-D
- US-D close (US calendar) = NOT available until ~02:00 IST on Indian-D+1 → forbidden as a feature for predicting Indian-D return

**Implementation:** `etf_panel_v3_curated` series are sourced from `pipeline/autoresearch/etf_v3_loader.build_panel()`, which already aligns ETF dates to the *next Indian session*. The feature column `etf_<symbol>_ret_1d` for Indian-date D is the US-ETF return computed from US-D-1-close and US-D-2-close. **This is a `shift(0)` on the panel as built by `build_panel()` because that function applies the IST-shift internally; the build_panel output has already been validated by the V3 regime engine for PIT-correctness.** Spec audit verifies this at §4.B.

For **Indian** features (Nifty futures, sector indices, India VIX), no shift needed — they close at the same 15:30 IST as the F&O underlying. Feature column is computed from same-D close.

### 4.B PIT verification gate (TRAINING-TIME)

Before fit, run:
```python
from pipeline.autoresearch.etf_v3_loader import build_panel, audit_panel
panel = build_panel()
audit = audit_panel(panel)
assert all(a.status in ("ok", "fixed") for a in audit), f"PIT audit failed: {audit}"
```

If the audit reports any `fail`, training is aborted — the hypothesis cannot be backtested on a contaminated panel. This satisfies §11 and §14 of the data validation policy.

**Stale-bar gate:** any stock with ≥ 5 stale bars (consecutive identical close) in any walk-forward fold is excluded from that fold's qualifier evaluation. Documented as `qualifier_skip_stale` in the manifest.

## 5. Feature library (FROZEN, target ~24 features post-PCA)

All features point-in-time, computed from data with `date <= as_of` only.

### 5.1 Foreign macro block — PCA-reduced (1d returns only at v1)

Raw inputs (pre-PCA): 30 CURATED foreign-ETF **1-day returns**.

```
Raw_etf_features(D) = [
    ret_1d(etf_i, D)  for etf_i in CURATED_FOREIGN_ETFS,  # 30 series, IST-aligned
]
```

**Empirical pre-flight finding (2026-05-03):** The CURATED-30 set was deliberately designed to span 30 distinct India-channel themes (US equities + AI + semis + financials + energy + healthcare + China + EM + Japan + Korea + Brazil + oil + gold + base metals + agri + dollar + treasury + EM credit + carbon + lithium + China internet + VIX + Germany + BTC + ...). On 1d returns this gives **K_ETF = 10 at 85% variance** — the panel is genuinely high-rank because each ETF carries idiosyncratic India-channel signal.

**v1 deliberately omits the 5-day return horizon** that an early draft considered. Adding the 5d block would push raw features 30 → 60 and K_ETF → 18 at 85% variance, which violates the §16 Check 2 cap (≤ 12) and the §16 Check 5 sample-size budget. **5d horizon deferred to v2.** This is recorded as a design constraint, not a hyperparameter that could be tuned later on the same single-touch.

**Dimensionality reduction:** PCA fit on training-fold raw 30-column matrix (z-scored using training-fold mean/std). Components retained:
```
K_ETF = smallest k such that cumulative_explained_variance(k) ≥ 0.85
```

K_ETF computed once per fold; stored per-fold in `walk_forward_results.json`. Final-model K_ETF is the value from the in-sample-holdout fold (the most-recent training fold). Empirical expectation from pre-flight: K_ETF ≈ 10. PC1 explains ~46% variance (a "global risk-on / risk-off" factor), PC2-PC4 each explain 6-9% (regional/sector-specific factors), PC5+ each explain ≤ 4% (residual idiosyncratic).

### 5.2 Indian macro block (4 features, no PCA)

- `nifty_near_month_ret_1d` — Nifty near-month future log-return same-D close (rolled series; carry adjustment per `pipeline/data/india_historical/futures/<expiry>.csv`)
- `nifty_near_month_ret_5d`
- `india_vix_level` — India VIX same-D close
- `india_vix_chg_5d` — log-change in India VIX over 5 sessions

**Per user directive (2026-05-03):** Nifty near-month features carry a **researcher-imposed prior weight** via column-scaling at BOTH training and inference time:
```
nifty_emphasis_factor = 1.5   # frozen scalar
nifty_near_month_ret_1d_scaled = nifty_near_month_ret_1d * sqrt(nifty_emphasis_factor)
nifty_near_month_ret_5d_scaled = nifty_near_month_ret_5d * sqrt(nifty_emphasis_factor)
```
Applied identically at fit and predict — no train/inference mismatch. Mathematically equivalent to halving the elastic-net L2 penalty on the nifty columns (since EN penalises ||β||² and scaling the column by k inflates the implied β by 1/k for the same fitted product β·x, so the same penalty budget allows a larger β·x term). Net effect: the model is allowed to lean more on Nifty features for a given regularisation strength. The 1.5 scalar is **frozen, not learnable at v1.** Recorded in `manifest.json`. At v2, this factor becomes a learnable hyperparameter on the Karpathy grid.

### 5.3 Stock-specific TA block (6 features, no PCA)

- `own_sector_ret_5d` — stock's mapped sectoral index 5d return (via `pipeline/scorecard_v2/sector_mapper.py` `SectorMapper().map_all()` resolved through `sector_mapping.SECTOR_TO_INDEX_FILE` — see Amendment A1. NOTE: `reference_sector_mapper_artifact_dependency.md` flags that map_all reads opus/artifacts. PIT verification at fit time: every stock in frozen universe must resolve to a non-"Unmapped" sector AND to a published Nifty sectoral index, else excluded; preflight enforces this so universe_frozen.json is by-construction sector-resolvable.)
- `atr_14_pct` — ATR(14) / close
- `rsi_14`
- `dist_50ema_pct` — (close − ema_50) / ema_50
- `vol_zscore_20` — (vol − vol_mean_20) / vol_std_20
- `range_pct_today` — (high − low) / close

### 5.4 Periodicity (3 features)

- `dow_mon`, `dow_tue`, `dow_wed` (Thu/Fri reference category — different from ta-karpathy v1's Friday-reference because we want the regime-coupled tape weeks separately)

**Total feature count target:** K_ETF (~10) + 4 + 6 + 3 = ~23 features per stock.

**Effective sample size (pre-flight verified 2026-05-03):**
- Training window: 2021-05-04 → 2025-10-31 = 992 trading days available in panel (panel ends 2026-04-23)
- HL=90d exponential decay → effective N per stock ≈ 130 effective observations
- obs:feature ratio at K_ETF=10: 130/23 ≈ 5.66:1 — **clears 5:1 minimum** (pre-flight Check 5 PASS)
- §9A fragility re-run at HL=180 → effective N ≈ 260, ratio ≈ 11.3:1 — comfortable

**ABORT condition:** if PCA on training-fold raw ETF block returns K_ETF > 12 (i.e., the 30 ETFs do NOT compress to ≤ 12 PCs at 85% variance), the dimensionality assumption is violated — feature library design fails and registration is aborted. Pre-flight 2026-05-03 confirmed K_ETF=10 on 1d-only block.

## 6. Label

**Primary label (LONG):** `y_long = 1{(close_t1 − open_t1) / open_t1 ≥ +0.4%}`, else 0.
**Primary label (SHORT):** `y_short = 1{(open_t1 − close_t1) / open_t1 ≥ +0.4%}`, else 0.

Two binary labels per (stock, day) — two independent elastic-net models per stock.

**Holding-period:** T+1 09:15 IST open → 15:25 IST mechanical close (intraday only). No overnight. ATR(14)×2 stop on T+1 with the 14:25 IST hard exit per `feedback_1430_ist_signal_cutoff.md` (mechanical TIME_STOPs run at 14:30; we close 5 min early to ensure fills).

Cell convention matches H-2026-04-29-ta-karpathy-v1 for direct comparability — they share the trade-mechanics layer.

## 7. Splits

| Split | Window | Use |
|---|---|---|
| Training | 2021-05-04 → 2025-10-31 | EN fit + alpha/l1_ratio CV per fold; PCA fit |
| Walk-forward folds | 4 contiguous quarters within training, expanding origin | Fold-AUC for qualifier gate |
| In-sample holdout | 2025-11-03 → 2026-04-30 (~6 months) | Final qualifier check before forward predictions begin |
| **Single-touch forward holdout** | **2026-05-04 09:15 IST → 2026-08-04 15:25 IST** (~65 trading days) | **The only test that decides PASS/FAIL** |

Auto-extension: if `n_qualifying < 5` at 2026-08-04, holdout extends to 2026-10-31 (one regime cycle). Auto-extension declared here; not amendable post-extension.

**No re-fit, re-tuning, re-PCA, or re-selection during the forward holdout.** Per backtesting-specs §10.4, any parameter change between 2026-05-04 09:15 IST and the verdict date consumes the single-touch and requires fresh hypothesis registration.

## 8. Model

**Class:** `sklearn.linear_model.LogisticRegression(penalty='elasticnet', solver='saga', class_weight='balanced', max_iter=5000)`

**Hyperparameter grid** (per (stock, direction), 5-fold time-series CV inside each walk-forward fold):
- `C` (= 1/alpha, sklearn's regularisation strength inverse) ∈ {0.01, 0.03, 0.1, 0.3, 1.0, 3.0}
- `l1_ratio` ∈ {0.1, 0.3, 0.5, 0.7, 0.9}

Total: 30 cells per CV. Selected by mean fold AUC.

**Sample weights:** `w_t = exp(-(T_max - t) × ln(2) / HL)` with HL=90 trading days primary. Weights normalised to sum to 1 per fit. The `class_weight='balanced'` overlay is applied multiplicatively after the time-decay weights.

**Standardisation:** features Z-scored using training-fold mean/std only; same stats applied to validation/holdout (no leakage).

**PCA on ETF block:** fit on training-fold raw ETF features (60-column matrix), projection matrix frozen for that fold.

**Per-cell fit:** ~150 stocks × 2 directions = ~300 independent EN models per fold × 4 folds + 1 final model per cell (refit on full training+in-sample-holdout window using median-CV hyperparameters across folds). Compute budget: ~15-25 min/fold on VPS.

## 9. Qualifier gate (PRE-FORWARD)

A (stock, direction) cell is **eligible for forward trading** only if all of:

1. **Walk-forward mean fold-AUC ≥ 0.55** across 4 quarterly folds
2. **Walk-forward fold-AUC std ≤ 0.05** (no single fold dominating)
3. **In-sample-holdout AUC ≥ 0.55** (consistency check; declared as a hurdle here, NOT used to pick parameters)
4. **n predicted-positive days ≥ 5 in in-sample holdout** (model isn't degenerate)
5. **BH-FDR p-value < 0.05 corrected across the full (stock × direction) cell grid** (~300 cells), computed via 10,000-shuffle label permutation null per fold
6. **Permutation null beat:** at least 95% of permuted-AUC values are below the cell's observed AUC

A cell that fails any of (1)–(6) is **not eligible** for forward trading. Its forward predictions are still emitted to `today_predictions.json` (as research artefacts) but excluded from the §12 verdict.

## 10. Forward trading rule (HOLDOUT)

For each eligible (stock, direction) cell, every trading day in `[2026-05-04, 2026-08-04]` (auto-extends per §7):

1. At T-day EOD (16:00 IST), compute the feature vector using bars/ETFs through T close (with §4.A IST shift on ETFs).
2. Score the eligible cell's frozen elastic-net model → `p_long`, `p_short` per stock.
3. The `nifty_emphasis_factor` column scaling is already baked into the fit per §5.2 — no extra step at score time.
4. **Entry rule:** if `p_long ≥ 0.6 AND p_short < 0.4`, fire LONG signal for T+1; mirror for SHORT. If both directions pass on the same stock-day, both fire (separate cells).
5. **Entry timestamp:** T+1 09:15 IST market open price (Kite LTP).
6. **Stop loss:** `entry_price ± ATR(14) × 2.0` (ATR computed from bars through T close).
7. **Hard exit:** T+1 14:25 IST mechanical close at LTP (5 min before universal 14:30 cutoff).
8. **No overnight, no T+2 hold, no scale-out, no trail.**

**Position size:** equal-notional ₹50,000 per leg per cell. Size is not the hypothesis.

**Slippage assumption:** S1 = 6 bps round-trip on Zerodha SSF (cash-equivalent for under-₹50k slot fills).

## 11. Comparator baselines (§9B.1 ladder)

| ID | Description | Required margin to clear |
|---|---|---|
| **B0** — always-prior | LONG every day every stock at 09:15, exit 14:25 | mean P&L margin ≥ +0.1% per trade |
| **B1** — random-direction | Same eligible cells, but flip a coin LONG vs SHORT | margin ≥ +0.2% per trade |
| **B2** — flipped EN | Same EN predictions, take the OPPOSITE side | If B2 P&L ≥ 0 → kill — model isn't picking direction, it's picking volatile days |
| **B3** — passive intraday NIFTY | LONG NIFTY 09:15, exit 14:25 every holdout day | margin ≥ +0.2% over passive intraday beta |
| **B4** — TA-only baseline | Same architecture but feature library = §5.3 + §5.4 only (no cross-asset, no PCA) | margin ≥ +0.1% per trade — **isolates the cross-asset block's contribution** |

H-2026-05-04 must clear **B0, B1, B3, B4 simultaneously AND B2 must lose money** for §12 PASS.

**B4 is the diagnostic gate:** if B4 also passes §9 qualifier and the cross-asset spec only marginally beats it, the cross-asset block is not the load-bearing piece. This is OK for v1 PASS but flags v2 (where cross-asset is supposed to be the differentiator) for re-design.

## 12. §15.1 PASS criteria

| Gate | Criterion |
|---|---|
| §5A — sample size | n_qualifying ≥ 5 cells AND ≥ 60 trades total across qualifying cells |
| §6 — pre-registered claim met | Pooled hit-rate ≥ 55% AND mean per-trade P&L ≥ +0.4% net@S1 |
| §7 — beats baselines | Margin > 0 vs B0/B1/B3/B4; B2 P&L < 0 |
| §9B.2 — permutation null | 100,000-shuffle p < 0.05 BH-FDR-corrected across qualifying cells |
| §9A — fragility | (a) HL=180 re-run preserves edge sign; (b) NIFTY-50-only sub-slice and ex-NIFTY-50 sub-slice both show non-degenerate edge (no single bucket carrying); (c) 2-of-3 monthly P&L buckets in holdout show positive Sharpe |
| §10.4 — single-touch | No parameter changes during holdout window |
| §11A — implementation risk | LTP-vs-VWAP slippage < 15 bps on holdout window |
| §11B — NIFTY-beta neutral | Residual Sharpe ≥ 0 after regressing out NIFTY beta |
| §12 — decay | Recent-15-day hit-rate not catastrophically below early-15-day |
| §12B — Deflated Sharpe | **REPORT-ONLY at v1.** Compute and emit PSR + DSR; do not gate-block. |

### 12.1 Deflated Sharpe metric (v1, report-only)

Per `docs/superpowers/specs/Sharpe_ Ratio _ Karparthy.txt`, raw Sharpe is inflated when many configurations are searched. With 30 CV cells × 300 (stock × direction) cells = 9,000 trial configs, expected max-Sharpe under null is ~3.4 SE above zero — for 65 holdout days that ≈ +5.4 annualised SR threshold, still a high bar but more measurable than the 21-day TA-Karpathy case.

**v1 stance: report DSR, do not gate on it.** v2 (when holdout window grows ≥ 100 days) makes DSR gate-blocking.

PSR/DSR computation per Bailey & Lopez de Prado 2014, identical to ta-karpathy v1.1 §12.1.

### 12.2 Failure-mode taxonomy

Aligned with §1.B null-expectation bounds:

- **n_qualifying = 0:** TERMINAL_STATE = `FAIL_NO_QUALIFIERS`. Per-stock cross-asset edge does not exist at daily frequency in F&O at the 0.55 AUC bar. Single-touch consumed. No re-run with relaxed gates.
- **n_qualifying ∈ [1, 4]:** TERMINAL_STATE = `FAIL_INSUFFICIENT_QUALIFIERS`. Below §12 floor; basket too thin to test claim. Single-touch consumed.
- **n_qualifying ∈ [5, 25] but pooled P&L < 0.4% mean:** TERMINAL_STATE = `FAIL_INSUFFICIENT_EDGE`.
- **n_qualifying ∈ [5, 25], P&L ≥ 0.4%, but B4 (TA-only) ≥ 80% of our P&L:** TERMINAL_STATE = `PASS_BUT_CROSS_ASSET_NOT_LOAD_BEARING`. v1 is technically PASS, but cross-asset block isn't the alpha source — TA features carry the prediction. v2 must re-design feature library or kill the cross-asset thesis.
- **n_qualifying ∈ [26, 80]:** §16.6 amplified leakage audit triggers. Verdict gated on audit results — if A/B/C all pass, treat as standard PASS / FAIL on §12 criteria. If any audit step flags, verdict is suspended.
- **n_qualifying > 80:** TERMINAL_STATE = `FAIL_LEAKAGE_SUSPECT`. Forward holdout paused. No declaration of PASS regardless of basket P&L until leakage source is identified and a fresh hypothesis is registered.
- **B2 P&L ≥ 0:** TERMINAL_STATE = `FAIL_VOLATILITY_PROXY` — model picks volatile days not direction.
- **§9A fragility fail:** TERMINAL_STATE = `FAIL_FRAGILE`.

## 13. Power analysis

For each eligible cell, expected trades in 65-day holdout: 5–25 per cell (EN typically predicts above-threshold on ~10-40% of days for genuine signals).

**Min detectable effect at 80% power:** at n=15 trades per cell, σ ≈ 1.4% (typical F&O daily ATR), MDE ≈ 0.65% per trade. Our claimed +0.4% is below MDE per-cell — the verdict is computed on the **pooled basket**, not per-cell.

Pooled: n_qualifying × 15 trades ≈ 75-150 trades in basket. Pooled MDE at 80% power ≈ 0.16% — comfortably below claimed 0.4% net.

**Verdict-power tension:** even a clean PASS at 65 days does not greenlight live capital. v2 expansion (longer holdout, larger universe, learnable nifty_emphasis_factor) is the path to a deployable signal.

## 14. Outputs

All paths under `pipeline/data/research/h_2026_05_04_cross_asset_perstock_lasso/`:

| File | Purpose |
|---|---|
| `manifest.json` | Run config, alpha+l1_ratio grid, qualifying cells, fold-AUCs, BH-FDR survivors, K_ETF chosen |
| `feature_matrices/<TICKER>.parquet` | Per-stock feature matrix (training + in-sample holdout) — pre-PCA raw ETF block + Indian macro + TA |
| `pca_projections/fold_<i>.npy` | PCA projection matrices, one per training fold + one final |
| `models/<TICKER>_<DIRECTION>.pkl` | Frozen EN models, ~300 total |
| `walk_forward_results.json` | Per-cell per-fold AUC, hyperparameters, PCA K_ETF, feature-survivor list |
| `permutation_null.json` | 10k-shuffle BH-FDR-corrected p-values |
| `today_predictions.json` | Daily forward predictions, written 04:30 IST after EOD scorer runs |
| `recommendations.csv` | Holdout trade ledger (entry, stop, exit, P&L) |
| `terminal_state.json` | PASS/FAIL/abandoned + reason, written after holdout closes |

## 15. Lifecycle & cadence

| Date | Step | Output |
|---|---|---|
| 2026-05-03 (today) | Spec written + self-reviewed + user-approved | this file |
| 2026-05-03 (tonight, after sample-size + orthogonality pre-flight) | Pre-registration commit | this spec + JSONL append |
| 2026-05-04 (Mon) | Build feature_extractor + EN runner + walk-forward + qualifier on VPS | code commits |
| 2026-05-04 (overnight) | VPS fit job (~3-4h compute on ~150 stocks × ~24 features × 5y × 30 CV cells) | manifest.json + walk_forward_results.json |
| 2026-05-05 04:30 IST | First forward prediction emitted | today_predictions.json |
| 2026-05-05 09:15 IST | First qualifying-cell trades open (if any cell qualified) | recommendations.csv (OPEN) |
| 2026-05-05 14:25 IST | First trades close | recommendations.csv (CLOSE) |
| 2026-05-05 → 2026-08-04 | 65-day single-touch forward holdout | recommendations.csv accumulates |
| 2026-08-05 (or auto-extend trigger) | §12 verdict computed, terminal_state written | terminal_state.json |

**Note on holdout opening:** 2026-05-04 is Monday. The fit job runs Mon overnight; first forward predictions on Tue 2026-05-05. The hypothesis ID retains the 2026-05-04 date as the *spec-locked* date matching standard convention; first trade is 2026-05-05.

## 16. Pre-flight checks (BEFORE backtest, BEFORE registration commit)

These execute tonight 2026-05-03; if any fail, the spec is amended pre-registration or the hypothesis is killed.

**Check 1 — Universe count:** the §3 construction rule yields ≥ 100 names. If < 100, loosen ADV gate to ₹25cr.
**Check 2 — PCA dimensionality:** PCA fit on raw 60-column ETF block over training window yields K_ETF ≤ 12 at 85% variance. If K_ETF > 12, kill — feature design failed.
**Check 3 — Orthogonality vs ta-karpathy:** for each ETF principal component PC_k (k ≤ K_ETF), compute Pearson correlation against each of the 6 stock-specific TA features (§5.3) on the universe-pooled training panel. **Max absolute correlation must be < 0.4.** If any PC × TA feature correlation crosses 0.4, the ETF block is duplicating TA information — flag in manifest and proceed only if at least 3 PCs remain orthogonal (else kill).
**Check 4 — PIT audit:** §4.B audit returns no `fail` rows.
**Check 5 — Sample-size:** at HL=90, effective obs:feature ratio is ≥ 5:1. If < 5, drop to HL=180 as primary.

### 16.6 Amplified leakage audit (TRIGGERED, not pre-holdout)

Triggered automatically if the §9 qualifier gate produces `n_qualifying ∈ [26, 80]` cells (above expected band per §1.B). The audit must complete before the §12 verdict is computed.

The audit re-runs the qualifier on three diagnostic rebuilds and checks consistency:

**A. Label-shift permutation control:** re-run the full pipeline with labels independently shuffled within each (stock, fold) — `n_qualifying_shuffled` should be ≤ ⌈α × N_cells⌉ at α=0.05 (~18 cells expected by chance). If `n_qualifying_shuffled` exceeds 30, the BH-FDR pipeline is leaking and the verdict is suspended.

**B. Date-shift PIT control:** re-run with the ETF block additionally shifted by +1 IST trading day (forcing future-information leakage). If `n_qualifying_shifted_forward` ≥ `n_qualifying`, the original PIT alignment is correct (forward-shift didn't help). If `n_qualifying_shifted_forward` >> `n_qualifying`, something is structurally wrong with the panel build and verdict is suspended.

**C. Feature-block ablation:** re-run with the ETF block zeroed (only Indian macro + TA + DOW). Compare `n_qualifying_ta_only` to `n_qualifying`. If they are nearly equal, the cross-asset block is not load-bearing — record TERMINAL_STATE = `PASS_BUT_CROSS_ASSET_NOT_LOAD_BEARING` (per §12.2) regardless of basket P&L.

The audit results are written to `manifest.json` and surfaced in the verdict report. The audit does NOT change the §12 PASS criteria — it provides diagnostic context for the verdict.

## 17. Self-review checklist (§0.3 / §10.4 compliance)

- [x] Universe frozen at registration time (continuity + ADV gate, list committed)
- [x] Feature library frozen (~24 post-PCA, ~64 raw)
- [x] PCA selection rule frozen (K_ETF = smallest k at 85% variance)
- [x] Label frozen (T+1 open-to-close ±0.4% binary, two directions)
- [x] Model class frozen (elastic-net logistic with C × l1_ratio CV grid pre-specified)
- [x] Sample-weight half-life frozen (90d primary, 180d fragility)
- [x] Qualifier gates pre-specified (mean fold-AUC ≥ 0.55, std ≤ 0.05, BH-FDR α=0.05)
- [x] Forward holdout window pre-specified (65 trading days from 2026-05-04, auto-extend rules declared)
- [x] No held-out post-2026-04-30 data observed for parameter selection
- [x] No thresholds derived from predecessor H-2026-04-29-ta-karpathy-v1's observed numbers
- [x] §12 PASS criteria fully enumerated, including failure-mode taxonomy
- [x] Comparator ladder pre-specified (B0-B4 with B4 cross-asset isolator)
- [x] Power analysis acknowledges per-cell thin power, pooled basket adequate
- [x] Single-touch holdout discipline locked
- [x] PIT alignment for cross-asset features documented (§4.A) and gated by audit (§4.B)
- [x] Pre-flight checks declared (§16) with kill conditions
- [x] **Primary unit of inference declared (§1.A — basket-level pass; non-qualified cells are non-tradeable, not failed predictions)**
- [x] **Null expectation bounds declared (§1.B — n_qualifying = 0 / [1,4] / [5,25] / [26,80] / >80 mapped to terminal states)**
- [x] **Classification-vs-regression rationale documented (§1.D — binary decision boundary, heavy-tail F&O returns, AUC scale-invariance, regression deferred to v3)**
- [x] **Amplified leakage audit declared (§16.6 — triggers in [26,80] band; label permutation + date-shift + ablation diagnostics)**

**This spec is complete and ready for pre-registration self-review pass.**

---

## 18. Forward roadmap

| Stage | Name | Adds | Trigger |
|---|---|---|---|
| **v1 (this spec)** | Cross-asset per-stock EN, full F&O, daily | 30 ETF PCs + 4 IND macro + 6 TA, EN logistic, HL=90d | Holdout 2026-05-04 → 2026-08-04 |
| v2 | Learnable nifty_emphasis | nifty_emphasis_factor on Karpathy grid; HL on grid | If v1 PASS with cross-asset load-bearing |
| v3 | Multi-horizon labels | Add T+2 / T+3 / T+5 close-to-close labels per cell | If v1 PASS; multi-horizon shows orthogonal alpha |
| v4 | Pooled-panel EN | Single panel regression with stock fixed effects, share parameters across F&O | If v1 cells are too sparse (n_qualifying ∈ [5, 10]) |
| v5 | Live capital pilot | 1% NAV per qualifying cell, soft launch | If v1 + v3 + v4 all PASS independent single-touch holdouts |

What v1 deliberately defers: dependence-aware basket construction (covariance + copula), portfolio optimiser, multi-horizon labels, learnable nifty emphasis, PCA on Indian macro block. Keeps v1 single-touch crisp.

**This is the second pillar of the per-stock ML programme alongside ta-karpathy-v1. They are evaluated independently; v1 PASS does not depend on ta-karpathy-v1 PASS or vice versa. If both PASS, v2 of each merges feature libraries.**
