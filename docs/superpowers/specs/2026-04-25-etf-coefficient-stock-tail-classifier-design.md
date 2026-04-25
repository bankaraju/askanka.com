# H-2026-04-25-002 — ETF coefficient → per-stock tail-class classifier (design)

**Hypothesis ID:** `H-2026-04-25-002`
**Date registered:** 2026-04-25
**Author:** bharatankaraju
**Strategy class:** `etf-conditional-stock-tail-classifier`
**Strategy name:** `etf-coefficient-stock-tail-mlp-v1`
**Standards version:** 1.0_2026-04-23 (per `docs/superpowers/specs/backtesting-specs.txt` §15.1)
**Data validation policy:** `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` (all input datasets at Approved-for-research, Tier D2)
**Deployment path:** D (forecast accuracy panel only) — path B (basket tilt) is a separate v2 if D passes

---

## Amendment 1 (2026-04-25, before single-touch holdout consumed)

The hypothesis is amended in two non-substantive ways before the holdout is run for the first time. Both changes are recorded here and in `docs/superpowers/hypothesis-registry.jsonl` under the `amendments` field for H-2026-04-25-002. The single-touch holdout is **intact** — no run has been executed against the model yet.

**A1.1 — Sectoral indices added to the global state vector.**
Data audit on 2026-04-25 found the registered ETF state vector under-uses available India-side market state. The 10 NSE sectoral indices (BANKNIFTY, NIFTYAUTO, NIFTYENERGY, NIFTYFMCG, NIFTYIT, NIFTYMEDIA, NIFTYMETAL, NIFTYPHARMA, NIFTYPSUBANK, NIFTYREALTY) are added to `C.ETF_SYMBOLS` and contribute identical-shape features (returns, vol z-score, distance from highs, etc.) to the global state vector. Net effect: the global state vector grows from 28 to 38 indices. Stock context features are unchanged.

Rationale: sectoral indices have continuous 5-year coverage with no IPO discontinuities; they fill the gap left by the unrecoverable pre-2024 NSE F&O archive. They also provide explicit India-side directional signal that the original 28-ETF state vector approximates only via global proxies (e.g. KBW Bank Index for BANKNIFTY).

The §15.1 ladder is unchanged. The Delta-margin (0.005 nats), p-floor (0.01), sigma-threshold (1.5), and family size (1, no multiplicity correction) remain locked. No model hyperparameter was calibrated against any held-out number.

**A1.2 — Universe pinned to canonical_fno_research_v1 (154 tickers).**
The hypothesis was registered against the F&O universe at large (~211 tickers). Data audit revealed:
- NSE pre-2024 F&O archive endpoints permanently 404 — universe membership for 2021-04-23 to 2024-01-31 is unrecoverable from public sources
- 62 tickers in the 2024+ universe history have no F&O CSV (data backfill task tracked separately)
- 22 IPOs are correctly absent before listing date (point-in-time correct)

The canonical universe `canonical_fno_research_v1` (154 tickers = 133 stable F&O members + 21 IPOs with at least 100 bars) is locked as the input universe for this and all subsequent hypotheses. Survivorship bias is documented and bounded in `docs/superpowers/specs/2026-04-25-canonical-fno-research-dataset-audit.md` Section 7.

---

## 1. Claim

A small multi-task MLP (`etf_stock_tail_mlp_v1`) conditioned on the day-T-1
ETF state vector predicts the day-T per-stock 3-class tail label
(`down_tail` / `neutral` / `up_tail`, σ-thresholded per ticker) with held-out
cross-entropy loss strictly less than the strongest of three locked
baselines (always-prior, regime-one-hot logistic, full-feature logistic with
ETF×stock-context interactions) by a margin of at least **0.005 nats per
prediction**.

Statistical significance: p-value via 100k-permutation label-permutation
null on held-out predictions, p < 0.01. **Family size = 1**, no
multiplicity correction. Single-touch holdout per spec §10.4.

This is a **forecast-quality claim**, not a P&L claim. No money is gated by
this model. Path B (basket tilt) is a separate hypothesis registered after
D ships and shows held-out lift over baselines.

## 2. Pre-exploration disclosure

User pre-locked the following design parameters in conversation 2026-04-25
(brainstorming session, after H-2026-04-25-001 backtest verdict):

- **Purpose:** path D (forecast accuracy table on Terminal), path B
  conditional on D passing.
- **Label set:** 3 classes (down_tail / neutral / up_tail), per-ticker
  σ-thresholds (`|r_t| > 1.5 × σ_60d` is tail).
- **ETF input representation:** raw ETF returns at multiple windows + stock
  embeddings + stock context features (no pre-aggregation into regime label
  on the input side).
- **Test claim:** single-claim model-level (C1) + calibration backstop (M3).
- **Model under test:** small MLP shared trunk (architecture A).
- **Comparator baseline to ship if A fails:** logistic with interactions
  (architecture C).
- **Holdout window:** 12 months, 2025-04-26 → 2026-04-25, ≥ §10.1 20%.
- **Δ margin = 0.005 nats; p-floor = 0.01; σ = 1.5; no transformer in v1.**

No threshold, margin, baseline weight, or hyperparameter was calibrated
from any held-out forecast number. The 0.005 nat margin is a framework
default copied forward from prior precedent (H-2026-04-23-001 family);
0.01 p-floor is one decade tighter than the H-2026-04-25-001 0.05 floor
because path D publishes accuracy claims directly to users and the cost of
a false positive is reputational, not a one-trade loss. σ = 1.5 was chosen
because it generates ~7% per-tail base rates on Indian F&O daily returns
(verified by ad-hoc count on RELIANCE/HDFCBANK/TCS without inspecting any
return value beyond the count). No exploratory model was fit before this
registration.

## 3. Data lineage

All input datasets are Approved-for-research, Tier D2, point-in-time
correct.

| Dataset | Path | Status | Notes |
|---|---|---|---|
| `etf_panel_daily_v1` | `pipeline/data/research/phase_c/daily_bars/<etf>.parquet` | Approved-for-research | 30 ETFs, daily close, used by existing autoresearch v2 |
| `fno_daily_v1` | `pipeline/data/fno_historical/<symbol>.csv` | Approved-for-research | 213 tickers, daily OHLCV |
| `fno_universe_history_v1` | `pipeline/data/fno_universe_history.json` | Approved-for-research | Point-in-time membership, used by H-2026-04-25-001 |
| `regime_cutpoints_v1` | `pipeline/data/regime_cutpoints.json` | Approved-for-research | q20/q40/q60/q80 cutpoints, calibrated on 2018-01-01..2021-04-22 |
| `sector_mapping_v1` | `opus/artifacts/<sym>/indianapi_stock.json` + `pipeline/config/sector_taxonomy.json` | Approved-for-research | Used by `pipeline/scorecard_v2/sector_mapper.py` |
| `regime_history_v1` | `pipeline/data/regime_history.csv` | Approved-for-research | Daily regime label, recomputed nightly |

No new datasets introduced by this hypothesis. The trained model artifact
(`etf_stock_tail_mlp_v1.pt`) and the labeled training panel
(`pipeline/data/research/etf_stock_tail/panel_v1.parquet`) are derived
artifacts under the same governance ladder as the inputs.

## 4. Panel construction

**Build script:** `pipeline/etf_stock_tail/build_panel.py` (deterministic,
SHA256 manifest of inputs + output recorded in
`panel_build_manifest.json`).

For every (ticker, date) pair where date ∈ training/validation/holdout
windows AND ticker was in F&O membership on date:

**ETF features (90 dims):** for each of 30 ETFs in
`pipeline/autoresearch/etf_optimal_weights.json`, compute
`{ret_1d, ret_5d, ret_20d}` from ETF parquets, strict T-1 close, no T-day
leakage. Missing ETF rows → forward-fill ≤ 5 days, else NaN → row dropped
with `DROPPED_INSUFFICIENT_ETF_DATA`.

**Stock context features (6 dims):**
- `ret_5d` — log return T-6→T-1 close
- `vol_z_60d` — z-score of trailing 20d realized vol against trailing
  60d distribution
- `volume_z_20d` — z-score of T-1 volume against trailing 20d
- `adv_percentile_252d` — percentile of T-1 ADV (close × volume) against
  trailing 252d
- `sector_id` — integer 0..K-1 from `SectorMapper.map_all()` snapshot
  on T-1 (frozen daily, not per-event)
- `dist_from_52w_high_pct` — `(close_t-1 / max(close_t-252..t-1)) - 1`

All causal — verified by `test_panel_causal.py` (mirror of
`pipeline/tests/autoresearch/regime_autoresearch/test_features_causal.py`).

**Stock embedding (8 dims):** learned `nn.Embedding(211, 8)` indexed by
ticker. Initialised `N(0, 0.01)`. L2 weight decay 1e-3 on the embedding
matrix specifically (10× the trunk weight decay) to suppress overfit on
recent F&O additions with <500 training examples.

**Total input dim:** 90 (ETF) + 6 (context) + 8 (embedding) = **104**.

**Label (3 classes):** for each (ticker, date), compute
`r_t = close_t / close_{t-1} - 1` and
`σ_t = stdev(r_{t-60..t-1})` (strict, excludes t).
- `up_tail` if `r_t > 1.5 × σ_t`
- `down_tail` if `r_t < -1.5 × σ_t`
- `neutral` otherwise

Base rates expected ~7% / 7% / 86% per ticker. Verified at panel build:
each ticker must have ≥30 down_tail and ≥30 up_tail examples in the
training window or it is dropped from the universe with
`DROPPED_INSUFFICIENT_TAIL_LABELS`. The dropped-ticker list is logged in
the panel manifest and disclosed in the verdict.

## 5. Splits

| Split | Window | Approx size | Purpose |
|---|---|---|---|
| Train | 2020-04-23 → 2024-12-31 | ~1170 trading days × 211 tickers ≈ 245k rows | Model fit |
| Validation | 2025-01-01 → 2025-04-25 | ~80 days × 211 ≈ 17k | Early stopping + hyperparameter selection only — never used for verdict |
| Holdout | 2025-04-26 → 2026-04-25 | ~250 days × 211 ≈ 52k | **Single-touch.** Used exactly once for the verdict. Re-runs blocked by `holdout_touch_log.json`. |

Holdout fraction: 52k / (245k + 17k + 52k) ≈ **17%**.

§10.1 target is 20%. Therefore §10 verdict: **PARTIAL** (matches
H-2026-04-25-001 precedent at 17% — same waiver template applies; logged
in registry pre-registration).

If the user wants a clean §10.1 PASS at registration, the holdout extends
to 2024-04-26 → 2026-04-25 = 24 months ≈ 33%, at the cost of training
shrinking to 4 years. Default in this spec is 12-month holdout for
direct comparability with the recent H-2026-04-25-001 holdout convention.

**Regime coverage check at panel build:** holdout must contain ≥30 days
labelled in each of 5 regimes (DEEP_PAIN/PAIN/NEUTRAL/EUPHORIA/MEGA_EUPHORIA)
per `regime_history.csv`. If not, panel build aborts with
`INSUFFICIENT_REGIME_COVERAGE` and the holdout extends to whatever window
satisfies the constraint (logged in manifest).

## 6. Model under test (architecture A)

**Module:** `pipeline.etf_stock_tail.model.EtfStockTailMlp`
**Framework:** PyTorch (already on VPS, version pinned in
`requirements-vps.txt`).

```python
class EtfStockTailMlp(nn.Module):
    def __init__(self, n_etf_features=90, n_context=6, n_tickers=211, embed_dim=8):
        super().__init__()
        self.embedding = nn.Embedding(n_tickers, embed_dim)
        in_dim = n_etf_features + n_context + embed_dim  # 104
        self.trunk = nn.Sequential(
            nn.Linear(in_dim, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64),    nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, 3),
        )

    def forward(self, etf_x, ctx_x, ticker_ids):
        e = self.embedding(ticker_ids)
        x = torch.cat([etf_x, ctx_x, e], dim=-1)
        return self.trunk(x)  # logits over 3 classes
```

**Total parameters:** ~50k (211×8 embed + 104×128 + 128×64 + 64×3 ≈ 50,500).

**Training:**
- Loss: `nn.CrossEntropyLoss` with class-balanced sampling (each minibatch
  draws equally from down_tail / neutral / up_tail rows).
- Optimizer: `AdamW(lr=1e-3, weight_decay=1e-4)` for trunk;
  `AdamW(lr=1e-3, weight_decay=1e-3)` for embedding (separate parameter
  group, 10× weight decay).
- Batch size: 256.
- Max epochs: 100.
- Early stop: on validation log-loss, patience 10 epochs.
- Random seed: 42 (locked, must be reproducible).
- Wall-clock budget: ~5 minutes on VPS 12-core (CPU only — no GPU).

**Output:** softmax probabilities over `{down_tail, neutral, up_tail}`.

## 7. Comparator baselines (locked in §15.1 §9B.1 ladder)

All baselines use identical splits, identical dropped-row handling,
identical evaluation pipeline. All trained on Train, evaluated on Holdout.

**B0 — always-prior.** Predict `[p_down, p_neutral, p_up]` = training-set
class frequencies for every prediction. Floor — sets the "no information"
log-loss.

**B1 — regime-one-hot logistic.** Inputs: 5 regime indicators
(`regime == DEEP_PAIN`, ..., `regime == MEGA_EUPHORIA`) at T-1 from
`regime_history.csv`. `sklearn.linear_model.LogisticRegression`,
`multi_class='multinomial'`, `solver='lbfgs'`. Tests the existing ETF
regime engine's information content for the per-stock tail problem. **If
A fails to beat B1, the new architecture adds nothing over the existing
regime label and the project ends.**

**B2 — full-feature logistic with interactions (architecture C).** Inputs:
104-dim base + 4 hand-designed interaction terms:
- `etf_brazil_ret_1d × sector_id` (one-hot expanded to K columns)
- `etf_dollar_ret_1d × sector_id`
- `etf_india_vix_daily_ret_1d × vol_z_60d`
- `etf_india_etf_ret_1d × dist_from_52w_high_pct`

`sklearn.linear_model.LogisticRegression` with L2, `C=1.0`,
`multi_class='multinomial'`. Strongest non-NN baseline. Pre-locked: this
specific 4-interaction set is final, no post-hoc additions.

## 8. §15.1 verdict ladder (mapped from `backtesting-specs.txt`)

| Section | Test | Required |
|---|---|---|
| §1/3 (S0/S1/S2/S3) | N/A — path D, no slippage | Replaced by **calibration table + Brier decomposition** at S0-equivalent |
| §2 risk metrics | Per-class log-loss + Brier on holdout | PASS by computation |
| §5A data audit | All input datasets Approved-for-research | PASS (no AUTO-FAIL) |
| §6 universe | F&O 211 disclosed, point-in-time via `fno_universe_history.json`, dropped tickers logged | PASS |
| §7 execution mode | `MODE_NONE_FORECAST_ONLY` (path D) | PASS by declaration |
| §8 direction audit | Model outputs probabilities only, no direction conflict possible | PASS trivially |
| §9 power | n=52k holdout predictions ≫ any per-regime floor (52k / 5 ≈ 10k per regime) | PASS by construction |
| §9A fragility | Retrain with 6 perturbations: dropout ±10%, hidden ±2 units, weight_decay ±20%, σ ∈ {1.0, 2.0}, seed ∈ {1337, 2718}. STABLE if held-out log-loss within ±2% of base on ≥4 of 6 | Required for PASS |
| §9B.1 beats baselines | `CE_model < min(CE_B0, CE_B1, CE_B2) − 0.005` nats | Required for PASS |
| §9B.2 permutation null | 100k label-permutation null on holdout, empirical p < 0.01 | Required for PASS |
| §10 single-touch | Holdout 17% < 20% target → **PARTIAL** at registration; waiver doc required | PARTIAL (not blocking PASS) |
| §11B residualization | N/A — no return target. Replaced by **calibration-residualized log-loss**: model log-loss must beat B0/B1/B2 *after* removing per-class miscalibration component (Brier reliability) | Required for PASS |

**Final verdict:** PASS iff **§9A STABLE + §9B.1 + §9B.2 + §11B-residualized
PASS**. §10 PARTIAL is acknowledged at registration and does not block
PASS, but blocks promotion to path B (which would require a new
hypothesis with 20%+ holdout).

## 9. Calibration backstop (M3)

Required outputs in `holdout_calibration.json`:

- **Reliability diagram:** 10 probability bins per class, empirical
  frequency vs. predicted probability, with bin counts.
- **Brier score decomposition:** total Brier = reliability + resolution +
  uncertainty (Murphy 1973). Logged per class.
- **Expected Calibration Error (ECE):** weighted average bin gap.
- **Per-regime calibration:** Brier per class × per regime (5 × 3 = 15
  cells) — tests whether the model is well-calibrated only in some
  regimes.

Calibration plots committed as `holdout_reliability.png` (single image,
3 subplots).

## 10. Deployment surface (path D, post-PASS)

If §15.1 verdict is PASS:

**New scheduled task (CLAUDE.md update + `pipeline/config/anka_inventory.json`):**
- 04:35 IST `AnkaETFStockTailScore` — runs `pipeline.etf_stock_tail.score_universe`,
  writes `data/etf_stock_tail.json` (211 rows × {p_down, p_neutral, p_up,
  top_3_etf_contributions}).
- Sunday 02:00 IST `AnkaETFStockTailFit` — walk-forward refit, holdout
  never re-touched.

**Terminal panel:** new tab `etf_outlook` showing top-10 down-tail and
top-10 up-tail stocks for tomorrow with calibrated probabilities and
top-3 ETF contributions per stock (gradient × input attribution, not
SHAP — too slow for daily; gradient × input is the cheap approximation
appropriate for 50k-param MLP).

**Telegram morning brief addition:** one-line addition to the 07:30 IST
morning brief listing the top-3 down-tail stocks with their probabilities,
labelled clearly as "model forecast — not a trade signal."

**Watchdog:** `AnkaETFStockTailScore` registered in
`pipeline/config/anka_inventory.json` with tier=info, freshness contract
20h, expected output `data/etf_stock_tail.json`.

**No trade gating, no signal generation, no shadow ledger.** Path B
(basket tilt) is separately registered if D shows held-out lift after
≥3 months of forward-shadow accuracy.

## 11. Risks pre-registered

1. **Regime-mimicry trap.** Model may learn nothing more than "predict
   tail when regime composite is extreme." B1 baseline catches this — if
   A fails to beat B1 by ≥0.005 nats, the project ends; ship B1 as the
   forecast on the Terminal panel.
2. **Embedding overfit on small-cap stocks.** ~30 of 211 have <500
   training examples. Mitigated by 10× embedding weight decay; per-ticker
   `n_train` logged in manifest; dropped if < 30 tail examples per side.
3. **Tail label leakage via σ_60d.** σ uses dates strictly < t — verified
   by `test_panel_causal.py`.
4. **Holdout regime mix.** 12-month window covers full distribution.
   Verified at panel build (≥30 days per regime). If not, panel build
   aborts and holdout extends.
5. **Calibration without recalibration step.** Model trained with
   class-balanced sampling produces uncalibrated probabilities by
   construction. Mitigation: Platt scaling on validation set, applied
   to holdout — calibration step locked at registration, not selected
   post-hoc.
6. **Path D → path B transition risk.** A passing path-D model is not
   automatically a useful basket tilt. Path B requires its own
   pre-registration with P&L claim, P&L holdout, slippage grid.

## 12. Compute budget

VPS-only (Contabo 12-core EPYC 47 GB RAM, validated 2026-04-25). No GPU.

| Phase | Wall clock |
|---|---|
| Panel build (one-shot) | ~3 min |
| Model train | ~5 min |
| 6× fragility retrain | ~30 min |
| 100k permutation null | ~10 min |
| Calibration + verdict assembly | ~2 min |
| **Total verdict run** | **~45 min** |

Re-runs after registration are blocked by `holdout_touch_log.json` per
spec §10.4.

## 13. Out of scope for v1

- Transformer / attention layers across stocks. Reserved for v2 if MLP
  fails interestingly.
- Intraday tail prediction. v1 is end-of-day-T classification only.
- Path B (basket tilt). Separate hypothesis post-D-PASS.
- Path A (gate trades). Not on the roadmap.
- Path C (risk-off flag). Not on the roadmap.
- Earnings / event-conditional predictions. v1 ignores corporate actions
  except via the existing F&O membership filter.

## 14. References

- `docs/superpowers/specs/backtesting-specs.txt` — §15.1 ladder source
- `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` — data governance
- `docs/superpowers/runs/2026-04-25-earnings-decoupling-h-2026-04-25-001/verdict.md` — H-2026-04-25-001 reference (FAILED) for framework precedent
- `pipeline/autoresearch/regime_autoresearch/README_PILOT.md` — autoresearch v2 framework precedent for verdict gates
- `pipeline/autoresearch/etf_optimal_weights.json` — current ETF coefficient set (input feature canonical list)
