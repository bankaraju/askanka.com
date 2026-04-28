# H-2026-04-29-ta-karpathy-v1 — Per-stock TA Lasso (top-10 NIFTY pilot)

**Hypothesis ID:** `H-2026-04-29-ta-karpathy-v1`
**Strategy class:** `per-stock-ta-lasso`
**Family scope:** ticker-family, n=10 (BH-FDR-corrected)
**Standards version:** 1.0_2026-04-23 (`docs/superpowers/specs/backtesting-specs.txt`)
**Spec version:** v1.1 (amended 2026-04-28 with §12 Deflated Sharpe gate; original v1.0 frozen at registry append)

---

## 1. Claim

For each stock in a frozen Top-10 NIFTY universe, a Lasso-regularised logistic regression trained on a ~60-feature daily TA vector (computed from 5y of bars ending 2026-04-25) will, on a single-touch forward holdout from 2026-04-29 → 2026-05-28 (≈21 trading days), produce per-stock predictions whose held-out hit-rate ≥ 55% AND mean per-trade T+1 P&L ≥ +0.5% (gross of slippage, ATR-stop-conditional) on the subset of stocks whose walk-forward mean fold-AUC ≥ 0.55 AND fold-AUC std ≤ 0.05.

Stocks failing the qualifier gate are not traded; the holdout is evaluated only over the qualifying subset. **Honest expectation: 0–3 stocks qualify.** The hypothesis is registered specifically to discover whether per-stock TA edges exist at daily frequency for high-liquidity NIFTY names — a known-failed broader test (H-2026-04-24-001, mean_auc=0.509) suggests this is a long shot.

## 2. Pre-exploration disclosure

A predecessor hypothesis (H-2026-04-24-001) tested the same architecture restricted to a single stock (RELIANCE) with ~30 features and vanilla LogisticRegression. **Result: FAIL — mean walk-forward AUC=0.509, min fold-AUC=0.173.** That single-touch holdout was consumed and is closed.

This new hypothesis is registered as a **distinct family** (10 stocks, ~60 features, Lasso regularisation) — the parameter grid is materially different, and the universe expansion to top 10 is a strategic widening, not a re-run. Per backtesting-specs §0.3, no thresholds are derived from RELIANCE's observed AUC; the 0.55/0.05/0.5%/55% gates are inherited from the framework's standard hurdle, not from the predecessor's numbers.

**Rationale for re-attempting after RELIANCE failed:** Two material levers were identified post-FAIL (`memory/project_ta_scorer_rework.md`):
- **Feature space too narrow** — ~30 features missing momentum oscillators (Williams %R, CCI, MFI, ROC), trend strength (ADX, DI), volume features (OBV slope, vol z-score), and finer MA distances (8/13/21/34 EMAs)
- **Model form** — vanilla logistic with manual interactions; no automatic feature selection or regularisation tuning per stock

This v1 addresses both: feature library expanded to ~60, model swapped to LassoCV with per-stock alpha auto-tuning. The Lasso L1 penalty acts as automatic feature selection — each stock keeps the subset of features that actually predict its T+1 direction.

**No held-out data has been observed.** The 21-day forward window starting 2026-04-29 is the single-touch holdout. The 2026-04-26/27/28 bars were used by the predecessor and are not part of this hypothesis's evaluation.

## 3. Universe (FROZEN)

Top 10 stocks by NIFTY 50 free-float weight as of 2026-04-25 close, locked to:

```
RELIANCE
HDFCBANK
ICICIBANK
INFY
TCS
BHARTIARTL
KOTAKBANK
LT
AXISBANK
SBIN
```

**Why these 10:** highest liquidity in F&O segment, tightest Zerodha SSF round-trip cost (~6–8 bps), longest continuous listing through the full 5y training window. No survivorship bias since none have been delisted or merged in the window. PIT compliant — no aliases needed.

Universe is **frozen at registration time**. If any of the 10 is materially impaired (corporate action, trading suspension) during the 21-day holdout, that stock is excluded from holdout evaluation but the qualifier gate still requires ≥3 qualifying stocks for §15.1 PASS.

## 4. Data lineage

| Dataset | Path | Tier | Acceptance status |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| daily_bars (5y, dividend-adjusted close) | `pipeline/data/research/phase_c/daily_bars/<ticker>.parquet` (preferred) or `pipeline/data/fno_historical/<ticker>.csv` (fallback) | D2 | Approved-for-research |
| sectoral_indices_v1 | `pipeline/data/sectoral_indices/*.csv` | D2 | Approved-for-research |
| nifty_index | `pipeline/data/india_historical/indices/NIFTY.csv` | D2 | Approved-for-research |
| regime_history_v4 | `pipeline/data/regime_history.csv` | D2 | Research-only (per `memory/reference_regime_history_csv_contamination.md`, this file is HINDSIGHT-built and shall NOT be used for OOS comparisons; for OOS we read `pipeline/data/today_regime.json` per-bar) |
| vix_history | `pipeline/data/india_historical/indices/INDIAVIX.csv` | D2 | Approved-for-research |

**Adjustment mode:** dividend-adjusted close on equity series; total-return-index on sectoral indices.
**Point-in-time correctness:** verified — all 10 stocks listed continuously since 2021-04-29; no PIT alias mapping required.
**Stale-bar gate:** the §5A staleness validator runs at fit time; any stock with ≥3 stale bars in any walk-forward fold disqualifies that stock from the experiment. Documented but counts as `qualifier_fail` not as model failure.

## 5. Feature library (FROZEN, ~60 features)

All features point-in-time, computed from bars with `date <= as_of` only.

### 5.1 Momentum oscillators (10)
- `rsi_7`, `rsi_14`, `rsi_21`
- `stoch_k_14`, `stoch_d_3`
- `williams_r_14`
- `cci_20`
- `mfi_14`
- `roc_5`, `roc_10`, `roc_20`

### 5.2 Trend strength (5)
- `adx_14`
- `plus_di_14`, `minus_di_14`
- `dmi_signal` = sign(plus_di − minus_di) when adx≥25, else 0

### 5.3 Moving-average geometry (10)
- `dist_8ema_pct`, `dist_13ema_pct`, `dist_21ema_pct`, `dist_50ema_pct`, `dist_200ema_pct`
- `dist_20sma_pct`, `dist_50sma_pct`, `dist_200sma_pct`
- `ma_slope_20` = (sma_20 − sma_20_lag5) / sma_20_lag5
- `ma_slope_50` = same on 50-day

### 5.4 Volatility (4)
- `atr_14_pct` = ATR(14) / close
- `bb_pct_b_20` = (close − lower_bb) / (upper_bb − lower_bb)
- `bb_width_pct` = (upper_bb − lower_bb) / sma_20
- `range_pct_today` = (high − low) / close

### 5.5 Volume features (4)
- `obv_slope_20` = (OBV − OBV_lag20) / max(|OBV_lag20|, 1)
- `vol_zscore_20` = (vol_today − vol_mean_20) / vol_std_20
- `vol_spike_2x` = 1{vol_today ≥ 2× vol_mean_20}
- `vol_relative_60` = vol_today / vol_mean_60

### 5.6 Price action (5)
- `gap_pct` = (open_today − close_yesterday) / close_yesterday
- `body_to_range` = |close − open| / max(high − low, 1e-9)
- `upper_wick_pct` = (high − max(open, close)) / close
- `lower_wick_pct` = (min(open, close) − low) / close
- `intraday_close_pos` = (close − low) / max(high − low, 1e-9)

### 5.7 Candlestick pattern dummies (10)
Binary flags from `pipeline/pattern_scanner/detect.py` (drop BB_BREAKOUT/BREAKDOWN per 2026-04-28 finding):
- `bullish_hammer`, `bullish_engulfing`, `morning_star`, `piercing_line`, `macd_bull_cross`
- `shooting_star`, `bearish_engulfing`, `evening_star`, `dark_cloud_cover`, `macd_bear_cross`

### 5.8 Macro context (8)
- `nifty_ret_5d`
- `vix_level`, `vix_zscore_60`, `vix_change_5d`
- `regime_RISK_ON`, `regime_NEUTRAL`, `regime_RISK_OFF` (one-hot from today_regime.json, NOT regime_history.csv)
- `sector_ret_5d` (the stock's mapped sectoral index from `pipeline/sector_mapper.py`)

### 5.9 Periodicity (4)
- `dow_mon`, `dow_tue`, `dow_wed`, `dow_thu` (Friday is reference category)

**Total feature count target: ~60.** Final count fixed at fit time and recorded in the run manifest. The Lasso L1 penalty selects a per-stock subset; the manifest records the chosen alpha and surviving features per stock per fold.

## 6. Label

**Primary label (LONG):** `y_long = 1{(close_t1 − open_t1) / open_t1 ≥ +0.4%}`, else 0.
**Primary label (SHORT):** `y_short = 1{(open_t1 − close_t1) / open_t1 ≥ +0.4%}`, else 0.

Two binary labels per (stock, day) — two independent Lasso models per stock (one for LONG, one for SHORT).

**Why ±0.4% and not symmetric T+1 close-vs-open binary:**
- Avoids labeling intraday noise as a "win"
- Matches the cost-buffer needed to clear S1 slippage (~6 bps × 2 = 12 bps) plus a meaningful margin
- Predecessor H-2026-04-24-001 used a thinner threshold which is one suspected contributor to AUC=0.509

**Holding-period:** T+1 open-to-close intraday only. **No overnight risk** per user's 2026-04-28 directive. No T+2/T+3 hold variants in this hypothesis.

## 7. Splits

| Split | Window | Use |
|---|---|---|
| Training | 2021-04-29 → 2025-10-25 | Lasso fit + alpha CV per fold |
| Walk-forward folds | 4 contiguous quarters within training, expanding origin | Fold-AUC for qualifier gate |
| In-sample holdout | 2025-10-26 → 2026-04-25 (~6 months) | Final qualifier check before forward predictions begin |
| **Single-touch forward holdout** | 2026-04-29 → 2026-05-28 (≈21 trading days) | **The only test that decides PASS/FAIL** |

**No re-fit, re-tuning, or re-selection during the forward holdout.** Per backtesting-specs §10.4, any parameter change between 2026-04-29 09:15 IST and 2026-05-28 15:30 IST consumes the single-touch and requires fresh hypothesis registration.

## 8. Model

**Class:** `sklearn.linear_model.LogisticRegression` with `penalty='l1'`, `solver='liblinear'`, `class_weight='balanced'`.

**Hyperparameter:** alpha (= 1/C in sklearn parameterisation) selected per (stock, fold) via 5-fold time-series CV over an alpha grid `{1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0, 10.0}`.

**Standardisation:** features Z-scored using training-fold mean/std only; same stats applied to holdout (no leakage).

**Per-stock fit:** 10 stocks × 2 directions = 20 independent Lasso models. Each gets its own selected feature subset.

**Final model for forward predictions:** for each stock, refit Lasso on the full training+in-sample-holdout window using the median alpha across walk-forward folds, then freeze.

## 9. Qualifier gate (PRE-FORWARD)

A stock-direction (RELIANCE-LONG, RELIANCE-SHORT, etc. — 20 cells) is **eligible for forward trading** only if all of:

1. **Walk-forward mean fold-AUC ≥ 0.55** across the 4 quarterly folds
2. **Walk-forward fold-AUC std ≤ 0.05** (no single fold dominating)
3. **In-sample-holdout AUC ≥ 0.55** (consistency check, not the gate that decides PASS/FAIL)
4. **n predicted-positive days ≥ 3 in in-sample holdout** (ensures the model isn't always predicting one class)
5. **BH-FDR p-value < 0.05** corrected across 20 (stock × direction) cells, computed via 10,000-shuffle label permutation null per fold

A cell that fails any of (1)–(5) is **not eligible** for forward trading. Its forward predictions are still emitted (as research artifacts) but excluded from the §15.1 verdict.

## 10. Forward trading rule (HOLDOUT)

For each eligible (stock, direction) cell, every trading day in `[2026-04-29, 2026-05-28]`:

1. At T-day EOD (16:00 IST), compute the feature vector using bars through T close.
2. Score the eligible cell's frozen Lasso model → `p_long`, `p_short` per stock.
3. **Entry rule:** if `p_long ≥ 0.6 AND p_short < 0.4`, fire LONG signal for T+1; mirror for SHORT.
4. **Entry timestamp:** T+1 09:15 IST market open price (Kite LTP).
5. **Stop loss:** `entry_price ± ATR(14) × 2.0` (ATR computed from bars through T close).
6. **Hard exit:** T+1 15:25 IST mechanical close at LTP.
7. **No overnight, no T+2 hold, no scale-out, no trail.**

**Position size:** equal-notional ₹50,000 per leg per stock (matching existing phase_c_shadow ledger for comparability). Size is not the hypothesis.

**Slippage assumption:** S1 = 6 bps round-trip on Zerodha SSF (the cheapest tradeable instrument).

## 11. Comparator baselines (§9B.1 ladder)

| ID | Description | Required margin to clear |
|---|---|---|
| **B0** — always-prior | LONG every day every stock at 09:15, exit 15:25 | mean P&L margin ≥ +0.5% per trade |
| **B1** — random-direction | Same eligible cells, but flip a coin LONG vs SHORT | margin ≥ +0.3% per trade |
| **B2** — flipped Lasso | Same Lasso predictions, take the OPPOSITE side (must lose money for our edge to be real) | If B2 P&L ≥ 0, kill — our model isn't picking direction, it's just picking volatile days |
| **B3** — passive intraday NIFTY | LONG NIFTY 09:15, exit 15:25 every day | margin ≥ +0.5% over passive intraday beta |
| **B4** — random-day, same direction | Pick same number of random days, take same side as Lasso | margin ≥ +0.5% per trade |

H-2026-04-29-ta-karpathy-v1 must clear **B0, B1, B3, B4 simultaneously AND B2 must lose money** for §15.1 PASS.

## 12. §15.1 PASS criteria

| Gate | Criterion |
|---|---|
| §5A — sample size | ≥ 30 trades total across qualifying cells in the 21-day holdout |
| §6 — pre-registered claim met | Held-out hit-rate ≥ 55% AND mean per-trade P&L ≥ +0.5% (S1 net) |
| §7 — beats all baselines | Margin > 0 vs B0/B1/B3/B4; B2 P&L < 0 |
| §9B.2 — permutation null | 100,000-shuffle p < 0.05 BH-FDR-corrected across qualifying cells |
| §10.4 — single-touch | No parameter changes during holdout window |
| §11A — implementation risk | LTP-vs-VWAP slippage < 15 bps on the 21-day window |
| §11B — NIFTY-beta neutral | Residual Sharpe ≥ 0 after regressing out NIFTY beta |
| §12 — decay | Recent-7-day hit-rate not catastrophically below early-7-day |
| §12B — Deflated Sharpe (v1.1) | **REPORT-ONLY at v1.** Compute and emit PSR + DSR on basket-level daily P&L; do not gate-block. |

### 12.1 Deflated Sharpe Ratio metric (v1.1 amendment, 2026-04-28)

Per user feedback (`docs/superpowers/specs/Sharpe_ Ratio _ Karparthy.txt`), raw Sharpe is inflated when many configurations are searched per stock. With 9 alphas × 20 (stock × direction) cells = 180 trial configs, the expected maximum Sharpe under the null is ~2.73 standard errors above zero — for a 21-day holdout that translates to ≈+9.6 annualised SR threshold, which is essentially impossible to clear empirically.

**v1 stance: report DSR, do not gate on it.** Adopting the gate at v1 with only 21 days of data would mathematically guarantee `FAIL_DEFLATED_SHARPE` regardless of true edge — making the gate uninformative. Instead:

- Compute and emit PSR + DSR + raw SR + skew + kurtosis on the holdout basket P&L.
- Surface the numbers in `terminal_state.json` and the EOD report for transparency.
- **DSR becomes gate-blocking at v2** (when the holdout window grows to ≥100 days and the deflation threshold falls into a testable range). v2 spec must explicitly fix N (number of trials) at the v2 search-space cardinality.

**Implementation (Bailey & Lopez de Prado 2014):**
- z_max = (1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)),  γ = Euler-Mascheroni ≈ 0.5772
- SR_threshold (annualised) = z_max × SE(SR_hat) where SE per Bailey-LdP eq. 8
- PSR = Φ((SR_hat - SR_threshold) × √(T-1) / √(1 - g3·SR_hat + (g4/4)·SR_hat²))
- All inputs are observable at verdict time; threshold (0.95) is literature-standard and not derived from observed numbers.

**Why this is a pre-holdout amendment compatible with §10.4:**
- Threshold inherited from published literature (not from observed data).
- Adds a NEW report-only metric; does not change any existing PASS criterion.
- Spec amended 2026-04-28 BEFORE the holdout window opens 2026-04-29 09:15 IST.

### 12.2 Stability discount (v1.1 amendment, 2026-04-28)

When ranking qualifying cells for basket inclusion, apply a stability multiplier:
`stability(c) = max(0, 1 - std(fold_aucs_c) / 0.10)` — cells whose AUC is unstable across folds get downweighted at the basket-construction stage. Cells with stability < 0.5 are excluded from the basket even if they passed the §9 qualifier gate. This is a NEW filter that ADDS conservatism.

**Failure modes recognised in advance:**
- **0 stocks qualify (zero-survivor):** TERMINAL_STATE = `FAIL_NO_QUALIFIERS`. Genuine learning that per-stock TA edges don't exist at daily frequency in NIFTY-10. No re-run with relaxed gates.
- **Some qualify but P&L < 0.5% mean:** TERMINAL_STATE = `FAIL_INSUFFICIENT_EDGE`.
- **Hit-rate ≥ 55% but P&L < 0.5%:** TERMINAL_STATE = `FAIL_THIN_EDGE` — directional sense exists but profit-per-trade too thin to clear costs.
- **Statistically significant but B2 P&L ≥ 0:** TERMINAL_STATE = `FAIL_VOLATILITY_PROXY` — we're picking volatile days, not direction.
- **§6/§7/§9 gates pass with low PSR (v1.1):** NOT a terminal state at v1 — PSR is report-only here (§12.1). Low PSR at v1 is documented in `terminal_state.json` and forwards to v2's gate budget if v1 PASSes.

## 13. Power analysis

For each eligible cell, expected trades in 21-day holdout:
- Maximum: 21 trades (every day predicts above threshold)
- Realistic: 5–15 trades (Lasso typically predicts above-threshold on a fraction of days)
- Minimum gate: ≥ 3 trades per eligible cell to count toward §5A pooled n

**Min detectable effect at 80% power:** for n=10 trades per cell, σ ≈ 1.5% (typical NIFTY-10 daily ATR), MDE ≈ 0.95% per trade. Our claimed +0.5% is below this — meaning **even at PASS we'll have wide confidence intervals**. This is acknowledged: a PASS here triggers expansion to 30/50 stocks (more power), not direct deployment.

## 14. Outputs

All paths under `pipeline/data/research/h_2026_04_29_ta_karpathy_v1/`:

| File | Purpose |
|---|---|
| `manifest.json` | Run config, alpha grid, qualifying cells, fold-AUCs, BH-FDR survivors |
| `feature_matrices/<TICKER>.parquet` | Per-stock feature matrix (training + in-sample holdout) |
| `models/<TICKER>_<DIRECTION>.pkl` | Frozen Lasso models, 20 total |
| `walk_forward_results.json` | Per-cell per-fold AUC, alpha-CV, feature-survivor list |
| `permutation_null.json` | 10k-shuffle BH-FDR-corrected p-values |
| `today_predictions.json` | Daily forward predictions, written 04:30 IST after EOD scorer runs |
| `recommendations.csv` | Holdout trade ledger (entry, stop, exit, P&L) |
| `terminal_state.json` | PASS/FAIL/abandoned + reason, written after holdout closes |

## 15. Lifecycle & cadence

| Date | Step | Output |
|---|---|---|
| 2026-04-28 | Pre-registration commit | this spec + JSONL append |
| 2026-04-28 (today) | Build feature_extractor expansion + Lasso model + walk-forward + qualifier | code commits |
| 2026-04-28 (tonight) | Kick off VPS fit job (~2h compute on 10 stocks × 60 features × 5y) | manifest.json + walk_forward_results.json |
| 2026-04-29 04:30 IST | First forward prediction emitted | today_predictions.json |
| 2026-04-29 09:15 IST | First qualifying-cell trades open | recommendations.csv (OPEN) |
| 2026-04-29 15:25 IST | First trades close | recommendations.csv (CLOSE) |
| 2026-04-29 → 2026-05-28 | 21-day single-touch forward holdout | recommendations.csv accumulates |
| 2026-05-29 | §15.1 verdict computed, terminal_state written | terminal_state.json |

## 16. Implementation tasks (handed to writing-plans)

T0: Pre-registration commit (this file + registry append + 2 commits) — `H-2026-04-29-ta-karpathy-v1` registered
T1: Extend `pipeline/ta_scorer/features.py` with the ~30 new features in §5
T2: Add `fit_lasso_cv` to `pipeline/ta_scorer/model.py` with alpha-grid CV per stock per fold
T3: Extend `pipeline/ta_scorer/walk_forward.py` with the 4-fold qualifier gate + BH-FDR permutation null
T4: New `pipeline/ta_scorer/karpathy_runner.py` orchestrating the 10-stock fit
T5: VPS fit job + .service/.timer (kicked off tonight, completes ~21:00 IST)
T6: New `pipeline/ta_scorer/karpathy_predict.py` for daily forward prediction (04:30 IST scheduled)
T7: New `pipeline/ta_scorer/karpathy_holdout.py` for trade entry/close ledger maintenance
T8: AnkaTAKarpathyOpen and AnkaTAKarpathyClose VPS systemd timers (09:15 OPEN / 15:25 CLOSE)
T9: Watchdog inventory entries + freshness contracts on the new outputs
T10: Terminal Trading tab card surfacing the forward predictions when any cell is eligible
T11: §15.1 verdict runner — runs 2026-05-29 after holdout closes, writes terminal_state.json
T12: Docs sync — SYSTEM_OPERATIONS_MANUAL.md + memory files

## 17. Self-review checklist (§0.3 / §10.4 compliance)

- [x] Universe frozen at registration time (10 NIFTY top names by 2026-04-25 weight)
- [x] Feature list frozen at registration time (~60, drop BB per 2026-04-28 evidence)
- [x] Label frozen (T+1 open-to-close ±0.4% binary, two directions)
- [x] Model class frozen (Lasso logistic with alpha-CV grid pre-specified)
- [x] Qualifier gates pre-specified (mean fold-AUC ≥ 0.55, std ≤ 0.05, BH-FDR α=0.05)
- [x] Forward holdout window pre-specified (21 trading days from 2026-04-29)
- [x] No held-out data observed for parameter selection
- [x] No thresholds derived from predecessor H-2026-04-24-001's observed numbers
- [x] §15.1 PASS criteria fully enumerated, including failure-mode taxonomy
- [x] Comparator ladder pre-specified
- [x] Power analysis acknowledges thin-power conditions
- [x] Single-touch holdout discipline locked

**This spec is complete and pre-registered as of git commit timestamp at append.**

---

## 18. Forward roadmap — alignment with `nse_fo_universe_technical_spec.md`

H-2026-04-29-ta-karpathy-v1 is the **"Signal Research Engine" layer** of the broader NSE F&O Universe spec (`docs/superpowers/specs/nse_fo_universe_technical_spec.md`). It deliberately scopes a top-10 NIFTY pilot at 1 strategy per stock to keep the single-touch holdout small and cheap. The full engine adds the following layers, each gated on v1 not failing in a way that kills the architecture:

| Stage | Name | Adds | Trigger |
|---|---|---|---|
| v1 (this spec) | Signal Research Engine, single-strategy | Per-stock Lasso, 10 stocks, 1 model per direction | Holdout 2026-04-29 → 2026-05-28 |
| v2 | Per-stock Top-10 candidate basket | Composite score (Sharpe^net + stability − turnover − fragility), retain 10 strategies per stock instead of 1 | If v1 yields ≥ 3 qualifying cells AND PSR ≥ 0.95 |
| v3 | Universe expansion to ~220 F&O names | PIT eligibility, monthly reconstitution, internal liquidity filters | If v2 maintains net Sharpe across walk-forward folds |
| v4 | Dependence Engine | Shrunk covariance + Student-t copula overlay for joint downside probability | If v3 candidate baskets exceed 30 stocks |
| v5 | Portfolio Optimizer | SCO with turnover/JDP/CVaR penalties, max-1-strategy-per-stock | If v4 produces non-degenerate joint-loss diagnostics |

**v1.1 amendment (2026-04-28) explicitly aligns with the broader spec on:**
- Multiple-testing control via deflated Sharpe (broader spec §Validation Framework / Multiple-Testing Control)
- Stability/fragility-aware composite score (broader spec §Per-Stock Candidate Basket)
- Walk-forward train / validation / test discipline (broader spec §Data Splits)

What v1 deliberately defers to v2+: copula-based dependence, portfolio optimizer, top-10 basket per stock, ~220-stock universe, multi-regime stratification. This is to keep v1's experimental budget tight and the holdout window short.

**Source files referenced for v1.1 framing:**
- `docs/superpowers/specs/Sharpe_ Ratio _ Karparthy.txt` — deflated Sharpe + meta-learning + portfolio-aware selection insight
- `docs/superpowers/specs/nse_fo_universe_technical_spec.md` — full multi-layer engine design
