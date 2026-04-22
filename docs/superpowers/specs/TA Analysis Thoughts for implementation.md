
Below is a single, self-contained **Markdown document** that consolidates everything we discussed about the TA Coincidence Scorer v1 (REL-only): problem framing, design spec, and implementation plan in the same style as your existing Feature Coincidence Scorer docs.[^1][^2]

***

# TA Coincidence Scorer v1

**Status:** draft, ready for implementation
**Author:** Bharat + TA Brainstorm
**Date:** 2026-04-22

***

## 1. Problem Statement

The current system already has:

- A **Feature Coincidence Scorer** that produces a per-ticker 0–100 attractiveness score based on cross-sectional features (regime, sector flow, breadth, trust, etc.), fit weekly and applied intraday.[^2]
- A rich **technical-analysis engine** that can detect candlestick patterns, moving-average relationships, momentum, volatility, and volume conditions, and assign pattern-level confidence (e.g., “Doji, 70% historically”).[^3][^4][^1]

The gap:

- Pattern signals (e.g., *RELIANCE doji with 70% historical win-rate*) are not yet integrated into a **probability-aware, context-conditioned** scorer that answers:
> “Given today’s TA setup in RELIANCE, and its context (trend, sector, market), how attractive is a 1-day (or 3-day) trade under our *actual* stop hierarchy?”[^5][^6]

This spec defines a **TA Coincidence Scorer v1**:

- v1 scope: **RELIANCE only**, daily bars.
- Output: **0–100 TA attractiveness score**, once per day, using a fixed TA/context feature set and logistic model.
- Role: **ranking / research**, not a gate or sizing engine. It can rank RELIANCE setups across days but does not decide whether to trade.[^2]

***

## 2. Design Decisions (Locked)

| Decision | Options considered | Locked choice |
| :-- | :-- | :-- |
| Universe | Single ticker vs full FO | v1 = **RELIANCE only** pilot to avoid sparse regimes and overfitting. |
| Timeframe | Intraday vs daily bars | **Daily bars only** in v1; intraday TA is deferred. |
| Prediction target | Raw direction vs realized P\&L | **Realized P\&L under existing B9/B10 stop logic**, horizon 1D (primary) and 3D (secondary research). |
| Signal role | Gate vs rank vs size | **Rank only**: TA score never blocks a trade or sets size in v1. |
| Feature set | Huge indicator library vs small fixed | **Small fixed TA+context vocabulary**, deliberately constrained. |
| Optimization cadence | Daily vs weekly vs monthly | **Weekly fit**, daily scoring. No daily re-optimization. |
| Model class | Logistic vs trees vs deep | **Logistic regression with explicit interactions** for interpretability. |
| Validation | Single split vs walk-forward | **Rolling 2y/3mo walk-forward**, AUC-based health bands. |
| Health | Soft warning vs hard band | Explicit **GREEN/AMBER/RED/UNAVAILABLE** based on mean and min fold AUC. |
| UI surface | Trading / Positions / TA | v1 = **TA panel only**, no Trading/Positions integration yet. |


***

## 3. Prediction Target and Labels

We want to predict **tradeability**, not raw price direction, in line with the existing Feature Coincidence Scorer.[^2]

### 3.1 Base data

- Ticker: RELIANCE daily OHLCV (clean, corporate actions-adjusted).[^4][^3]
- Sector index: relevant NIFTY sector index (e.g. NIFTYENERGY) daily OHLCV.[^7]
- Market index: NIFTY daily OHLCV + precomputed regime labels (RISK_OFF, NEUTRAL, etc.).[^7][^2]


### 3.2 Trade simulation

For each trading day $t$:

1. Simulate a **LONG entry at RELIANCE close on day $t$**.
2. Apply the **existing stop/trail hierarchy (B9/B10)** used elsewhere in the system:
    - Daily stop-loss.
    - Trailing stop with monotonic ratchet.
    - Target if applicable.
    - Time stop (max days in position).
    - Exit reason recorded as in the other scorer.[^1][^2]

### 3.3 Target labels

Primary label (1-day horizon):

- $y_{1d}(t) = 1$ if realized P\&L at exit (under the above logic) reaches or exceeds a **1-day win-threshold** $X\%$ (e.g. 0.8–1.0%).
- Otherwise $y_{1d}(t) = 0$.[^6][^8]

Secondary label (3-day horizon, research-only):

- $y_{3d}(t) = 1$ if realized P\&L at exit (within up to 3 trading days) reaches or exceeds a 3-day win threshold $Y\%$.
- Otherwise 0.

If the simulation cannot be run (missing data, corporate action holes), we drop that row from the training dataset.

***

## 4. Feature Vocabulary v1 (Fixed)

Features are computed **point-in-time as of close on day $t$** and must not peek into the future.[^9][^10]

### 4.1 Candlestick pattern flags

Binary indicators:

- `doji_flag`
- `hammer_flag`
- `shooting_star_flag`
- `bullish_engulfing_flag`
- `bearish_engulfing_flag`

Patterns use classic TA definitions (body vs total range, shadow lengths, gap/overlap rules), consistent with mainstream resources.[^4][^5][^6]

### 4.2 Trend and level context

Using RELIANCE daily closes:

- `dist_20dma_pct` = (close − MA20) / close
- `dist_50dma_pct` = (close − MA50) / close
- `dist_200dma_pct` = (close − MA200) / close
- `bb_pos` = (close − lower_BB20) / (upper_BB20 − lower_BB20), clipped to [−0.5, 1.5].[^3]


### 4.3 Momentum

- `rsi14` – 14-day RSI.[^3][^4]
- RSI buckets (one-hot, mutually exclusive):
    - `rsi_oversold` (RSI < 30)
    - `rsi_neutral` (30 ≤ RSI ≤ 70)
    - `rsi_overbought` (RSI > 70)
- `ret_3d` – 3-day log return ending at day $t$.
- `ret_10d` – 10-day log return ending at day $t$.
- `macd_hist` – MACD histogram value at day $t$.
- `macd_hist_slope` – MACD histogram slope (today − yesterday).[^3]


### 4.4 Volatility and range

- `atr20_pct` – ATR(20) / close.[^9][^3]
- `range_pct` – (high − low) / close for day $t$.


### 4.5 Volume and participation

- `vol_rel20` – volume_today / mean(volume_last_20d).
- `vol_spike_flag` – 1 if `vol_rel20 ≥ 1.5`, else 0.[^9]


### 4.6 Sector and market context

Sector (S = sector index, e.g. NIFTYENERGY):

- `sector_ret_5d` – 5-day log return of S.[^7]
- `sector_trend_flag` – 1 if MA20(S) > MA50(S), else 0.[^7]
- `sector_breadth_estimate` – fraction of sector constituents above 20DMA (or a proxy if you already have a breadth engine).

Market (NIFTY):

- `nifty_ret_5d` – 5-day log return of NIFTY.[^4][^7]
- Regime one-hot:
    - `regime_RISK_OFF`
    - `regime_NEUTRAL`
    - `regime_RISK_ON`
    - `regime_EUPHORIA`
    - `regime_CRISIS`

***

## 5. Interaction Terms v1

Explicit, limited interactions to encode “confirmation” logic without free-form feature search.[^11][^2]

- `doji_x_dist200` = `doji_flag * dist_200dma_pct`
- `doji_x_rsi_oversold` = `doji_flag * rsi_oversold`
- `engulfing_x_vol_spike` = (`bullish_engulfing_flag` OR `bearish_engulfing_flag`) * `vol_spike_flag`
- `hammer_x_bb_pos` = `hammer_flag * bb_pos`
- `rsi14_x_sector5d` = `rsi14 * sector_ret_5d`
- `dist20_x_ret3d` = `dist_20dma_pct * ret_3d`

These encode the idea that **candlestick signals are stronger when confirmed by levels, momentum, and volume in the right context**, as commonly described in TA literature.[^5][^6][^4]

***

## 6. Model Choice and Training

### 6.1 Model

- Logistic regression (binary classification) with:
    - L2 penalty
    - `C = 1.0` (tunable, but stay conservative)
    - `max_iter = 500`
    - `solver = "lbfgs"`
- Continuous features standardized (mean 0, std 1) per ticker before fitting.
- One-hot and binary features left as-is.[^10][^11]


### 6.2 Training dataset

For each labeled day $t$:

- Row:
    - `date`
    - all features (scalars, one-hots, interactions)
    - `y_1d` (primary label)
    - `y_3d` (secondary, optional)

For v1, model focuses on `y_1d`.

***

## 7. Validation Scheme and Health Bands

We adopt the same **rolling walk-forward** philosophy used in the Feature Coincidence Scorer, adapted to a single ticker.[^12][^13][^2]

### 7.1 Walk-forward setup

For RELIANCE:

- Train window: 2 years of history.
- Test window: 3 months.
- Step: 3 months (quarterly).
- Max folds: 6 (last ~4.5 years, if data exists).

For each fold:

1. Train on [train_start, train_end].
2. Test on [test_start, test_end].
3. Skip fold if:
    - Train rows < 400 or test rows < 40, or
    - Either train or test has only one class.
4. Compute test AUC, base win-rate, and top-score-bucket win-rate.[^8]

### 7.2 Health classification

Let:

- `mean_auc` – mean of valid fold AUCs.
- `min_fold_auc` – minimum fold AUC.
- `n_folds` – number of valid folds.

Health:

- **GREEN**: `n_folds ≥ 3` AND `mean_auc ≥ 0.55` AND `min_fold_auc ≥ 0.52`.[^8]
- **AMBER**: `n_folds ≥ 3` AND `mean_auc ∈ [0.52, 0.55)` OR `mean_auc ≥ 0.55` but `min_fold_auc < 0.52`.
- **RED**: `n_folds ≥ 3` AND `mean_auc < 0.52`.
- **UNAVAILABLE**: `n_folds < 3` (insufficient data / unstable).[^8]

The model is only used in the UI if health ∈ {GREEN, AMBER}. RED is logged but not surfaced as a strong signal.

***

## 8. Fit and Scoring Cadence

### 8.1 Weekly fit

Task: `AnkaTAScorerFit` (pilot).

- Schedule: **Sunday 01:30 IST**, weekly.
- Inputs:
    - RELIANCE daily OHLCV
    - Sector index daily OHLCV
    - NIFTY daily OHLCV and regime history
- Outputs:
    - `pipeline/data/ta_feature_models.json`

The weekly cadence is a compromise: it updates slowly enough to avoid noise-chasing, but frequently enough to adapt to structural changes.[^13][^8]

### 8.2 Daily scoring

Task: `AnkaTAScorerScore`.

- Schedule: daily at **16:00 IST** (after EOD bars are locked).
- Inputs:
    - Today’s RELIANCE bar and context (sector, NIFTY, regime).
    - Cached model from `ta_feature_models.json`.
- Output:
    - `pipeline/data/ta_attractiveness_scores.json` with today’s RELIANCE 0–100 score.

***

## 9. Storage Schemas

### 9.1 `pipeline/data/ta_feature_models.json`

Structure:

```json
{
  "version": "1.0",
  "fitted_at": "2026-04-27T01:30:00+05:30",
  "universe_size": 1,
  "models": {
    "RELIANCE": {
      "source": "own",
      "ticker": "RELIANCE",
      "horizon": "1d",
      "health": "GREEN",
      "mean_auc": 0.57,
      "min_fold_auc": 0.53,
      "n_folds": 5,
      "n_train_rows": 612,
      "coefficients": {
        "doji_flag": 0.182,
        "dist_200dma_pct": -0.109,
        "sector_ret_5d": 0.145,
        "doji_x_rsi_oversold": 0.210,
        "dist20_x_ret3d": -0.074
      },
      "standardization": {
        "dist_200dma_pct": { "mean": 0.012, "std": 0.036 },
        "sector_ret_5d": { "mean": 0.004, "std": 0.022 }
      },
      "folds": [
        {
          "train_start": "2021-01-01",
          "train_end": "2022-12-31",
          "test_start": "2023-01-01",
          "test_end": "2023-03-31",
          "n_train": 490,
          "n_test": 58,
          "auc": 0.56,
          "base_win_rate": 0.36,
          "top_bucket_win_rate": 0.48
        }
      ]
    }
  }
}
```


### 9.2 `pipeline/data/ta_attractiveness_scores.json`

Daily snapshot:

```json
{
  "updated_at": "2026-04-27T16:05:00+05:30",
  "scores": {
    "RELIANCE": {
      "ticker": "RELIANCE",
      "horizon": "1d",
      "score": 72,
      "band": "HIGH",
      "health": "GREEN",
      "source": "own",
      "p_hat": 0.72,
      "top_features": [
        { "name": "doji_flag", "sign": "+", "magnitude": 24, "value": 1 },
        { "name": "sector_ret_5d", "sign": "+", "magnitude": 18, "value": 0.031 },
        { "name": "dist_200dma_pct", "sign": "-", "magnitude": 15, "value": 0.015 }
      ],
      "computed_at": "2026-04-27T16:05:00+05:30"
    }
  }
}
```

`magnitude` is a normalized contribution measure based on |coef × standardized_feature|, scaled to sum ≈ 100.

***

## 10. Score Bands and Interpretation

Band mapping (v1 default):

- 0–39: LOW
- 40–59: MEDIUM
- 60–79: HIGH
- 80–100: VERY_HIGH

Interpretation (for RELIANCE, 1D):

- **Score ~50**: roughly neutral; TA context not particularly favorable or unfavorable relative to base.
- **Score ~70**: upper tail of historical setups; historically, such contexts have materially higher 1D win-rate than baseline.
- **Score ≥ 80**: rare configurations; must be used with care and only when health=GREEN and sample sizes are adequate.

In v1, this band is **only descriptive**; it does not auto-trigger actions.

***

## 11. UI Surfaces (v1)

Initial v1 UI is limited to the **TA panel for RELIANCE**:

When RELIANCE is selected in the TA tab:

- Show a “TA Attractiveness” row:
    - `Score: 72 (HIGH, health: GREEN)`.
    - Tooltip with:
        - “1D TA score p≈0.72, model mean AUC 0.57 (n_folds=5), based on 600+ historical setups.”
- Show a feature contribution table:
    - Top positive and negative drivers with current values:
        - `Doji present` (+24)
        - `Sector strong 5d` (+18)
        - `Price near 200DMA` (−15)

No changes to Trading tab or Positions tab in v1; this is purely a **research panel**.

***

## 12. Implementation Plan (Task-by-Task)

This is the executable plan, modeled after the Feature Coincidence Scorer Implementation Plan.[^1]

### Task 1 – Package skeleton

**Files**

- `pipeline/ta_scorer/__init__.py`
- `pipeline/ta_scorer/fit_universe.py`
- `pipeline/ta_scorer/score_universe.py`
- `pipeline/tests/ta_scorer/__init__.py`
- `pipeline/tests/ta_scorer/test_package.py`

**Test stub**

```python
# pipeline/tests/ta_scorer/test_package.py
import importlib

def test_package_imports():
    ts = importlib.import_module("pipeline.ta_scorer")
    assert hasattr(ts, "__version__")

def test_fit_universe_callable():
    from pipeline.ta_scorer import fit_universe
    assert callable(fit_universe.main)

def test_score_universe_callable():
    from pipeline.ta_scorer import score_universe
    assert callable(score_universe.main)
```

**Implementation stub**

- `__init__.py` sets `__version__ = "0.1.0"`.
- `fit_universe.main()` and `score_universe.main()` log and return 0.

***

### Task 2 – Candlestick pattern detection

**Files**

- `pipeline/ta_scorer/patterns.py`
- `pipeline/tests/ta_scorer/test_patterns.py`

**Functions**

- `is_doji(row, body_frac_max=0.1)`
- `is_hammer(row, ...)`
- `is_shooting_star(row, ...)`
- `is_bullish_engulfing(prev_row, row)`
- `is_bearish_engulfing(prev_row, row)`

**Tests**

- Construct small OHLC examples where each pattern should/should not trigger.
- Assert flag correctness.

***

### Task 3 – Feature extractor

**Files**

- `pipeline/ta_scorer/features.py`
- `pipeline/tests/ta_scorer/test_features.py`

**Key functions**

- `close_on_or_before(df, asof)`
- `moving_average(df, window, asof)`
- `rsi14(df, asof)`
- `atr20(df, asof)`
- `bollinger_position(df, asof)`
- `volume_relative_20(df, asof)`
- `sector_context(sector_df, asof)`
- `market_context(nifty_df, regime_on_date)`
- `build_feature_vector(prices_rel, prices_sector, prices_nifty, asof, regime, sector_breadth)`

**Tests**

- Check sign and scale of MA distances.
- Check RSI buckets for known values.
- Ensure ATR non-negative.
- Volume spike flag triggers at 1.5× avg.
- Regime one-hots sum to 1.
- Feature vector has all keys and no NaNs.

***

### Task 4 – Label generator (wrap existing stop logic)

**Files**

- `pipeline/ta_scorer/labels.py`
- `pipeline/tests/ta_scorer/test_labels.py`

**Functions**

- `make_label(prices_df, entry_date, horizon_days=1, win_threshold=..., ...) -> Optional[dict]`

Implementation can reuse the same underlying `simulatedpnllabel` pattern as in the Feature Coincidence Scorer, but with horizon_days=1 and tuned thresholds.[^1][^2]

**Tests**

- Rising series → y=1, realized_pct ≥ threshold.
- Falling series → y=0 by daily stop.
- Roundtrip with trail → y=1 when trailing locks in a win.
- Missing entry date → None.

***

### Task 5 – Model wrapper

**Files**

- `pipeline/ta_scorer/model.py`
- `pipeline/tests/ta_scorer/test_model.py`

**Functions**

- `build_interaction_columns(df)`
- `prepare_X(df)`
- `fit_logistic(X, y, random_state=42)`
- `predict_proba(model, X)`
- `coefficients_dict(model)`

**Tests**

- Interactions added.
- On synthetic toy data, AUC > 0.7.
- Reproducible with fixed seed.
- Single-row prediction correct shape and in.[^14]

***

### Task 6 – Walk-forward validation

**Files**

- `pipeline/ta_scorer/walkforward.py`
- `pipeline/tests/ta_scorer/test_walkforward.py`

**Functions**

- `build_folds(asof, train_years, test_months, max_folds)`
- `classify_health(mean_auc, min_fold_auc, n_folds)`
- `run_walkforward(df, train_years, test_months, asof, max_folds)`

**Tests**

- Multiple folds generated with synthetic data.
- mean and min AUC produced.
- Strong synthetic signal → GREEN.
- Thin history → UNAVAILABLE.
- Edge cases for thresholds.

***

### Task 7 – Storage layer

**Files**

- `pipeline/ta_scorer/storage.py`
- `pipeline/tests/ta_scorer/test_storage.py`

**Functions**

- `write_models(data, out=None)`
- `read_models(path=None)`
- `write_scores(data, out=None)`
- `read_scores(path=None)`

**Tests**

- Roundtrip write/read for models and scores.
- Missing file → empty structure.

***

### Task 8 – Fit universe (REL-only)

**Files**

- `pipeline/ta_scorer/fit_universe.py`
- `pipeline/tests/ta_scorer/test_fit_universe.py`

**Flow**

1. Load RELIANCE daily, sector daily, NIFTY daily, regime series.
2. Build historical feature+label DataFrame.
3. Run walk-forward → folds + health.
4. If health != UNAVAILABLE:
    - Fit logistic model on all available data up to as-of date.
    - Serialize coefficients and standardization.
5. Write `ta_feature_models.json`.

**Test**

- On fixture data, `ta_feature_models.json` created with RELIANCE model and health field.

***

### Task 9 – Score universe (REL-only)

**Files**

- `pipeline/ta_scorer/score_universe.py`
- `pipeline/tests/ta_scorer/test_score_universe.py`

**Flow**

1. Read model from `ta_feature_models.json`.
2. If missing or health=UNAVAILABLE, write scores file with a “no score” status and exit.
3. Load today’s RELIANCE bar + context.
4. Compute feature vector, standardize, predict p_hat.
5. Score = round(100 * p_hat).
6. Map to band.
7. Compute top_features contributions.
8. Write `ta_attractiveness_scores.json`.

**Test**

- Scores JSON exists, with RELIANCE entry, score in , band and health present.

***

### Task 10 – TA panel integration

Minimal v1 UI; only RELIANCE TA tab panel:

- API endpoint to expose RELIANCE TA score and feature breakdown.
- Frontend component for TA panel.

***

### Task 11 – Scheduler and inventory

- Add weekly `AnkaTAScorerFit` (warn tier, 8d freshness).
- Add daily `AnkaTAScorerScore` (warn tier, 2d freshness).
- Update operations manual with:
    - Inputs/outputs.
    - What health values mean.
    - What to check if files stale.

***

### Task 12 – Memory and documentation sync

- Add `project_ta_coincidence_scorer.md` with:
    - Scope.
    - Non-goals.
    - Fit/score cadence.
    - Relationship to Feature Coincidence Scorer.
- Update `MEMORY.md`.

***

### Task 13 – Forward uplift audit (after 60–90 days live)

Once enough forward data is collected:

- Evaluate RELIANCE:
    - Base 1D win-rate for all days vs
    - Win-rate on days where health=GREEN and score ≥ 70.
- Require uplift ≥ 5 percentage points and drawdowns within acceptable limits to consider v1 successful (same style as your other scorer’s success condition).[^2][^8]

***

This Markdown is ready to drop into `docs/superpowers/specs/2026-xx-xx-ta-coincidence-scorer.md` (or similar) and then drive a task-by-task development run, exactly like you did for the Feature Coincidence Scorer.[^1][^2]

If you want, next we can tune the concrete numbers (1D threshold X%, exact score band thresholds, HYPERPARAMS) based on RELIANCE’s historical distribution so you don’t go in blind.

<div align="center">⁂</div>

[^1]: 2026-04-22-feature-coincidence-scorer.md

[^2]: 2026-04-22-feature-coincidence-scorer-design.md

[^3]: https://www.sciencedirect.com/science/article/pii/S2666827025000143

[^4]: https://www.quantinsti.com/articles/candlestick-patterns-meaning/

[^5]: https://www.ig.com/en/trading-strategies/16-candlestick-patterns-every-trader-should-know-NEW-180615

[^6]: https://www.wrightresearch.in/blog/risk-management-with-candlestick-patterns-a-comprehensive-guide/

[^7]: https://www.msci.com/research-and-insights/blog-post/factor-and-sector-behavior-across-macro-regimes

[^8]: https://www.technical-analysis-pro.com/strategies-ai-backtesting-walk-forward-model-validation/

[^9]: https://www.luxalgo.com/blog/feature-engineering-in-trading-turning-data-into-insights/

[^10]: https://thesai.org/Downloads/Volume16No12/Paper_68-Feature_Engineering_for_Machine_Learning_Based_Trading_Systems.pdf

[^11]: https://wire.insiderfinance.io/the-secret-weapon-traders-use-logistic-regression-python-e98001ac8183?gi=39443b2122e1

[^12]: https://www.kaggle.com/code/justozner/time-series-using-walk-forward-validation

[^13]: https://blog.quantinsti.com/walk-forward-optimization-python-xgboost-stock-prediction/

[^14]: https://www.bajajfinserv.in/average-true-range-atr

