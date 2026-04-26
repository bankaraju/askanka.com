# v2 deep-read findings — what I missed in the first pass

**Date:** 2026-04-26
**Context:** User pushback on my v3 FAIL verdict — "you have to read v2 in depth, deep enough to refute". This document captures what a proper end-to-end trace of the production v2 pipeline reveals.

---

## Finding 1 — v2 uses 1-day returns; v3 used 5-day returns

`pipeline/autoresearch/etf_reoptimize.py:451`:
```python
returns = close.pct_change() * 100   # 1-day returns
```

`pipeline/autoresearch/etf_daily_signal.py:203`:
```python
returns = close.pct_change() * 100
last_row = returns.iloc[-1]   # last 1-day return
```

My v3 (`build_features` in `etf_v3_research.py`) used `(close / close.shift(5) - 1) * 100` for every foreign ETF. **v3 was not a fair re-test of v2.** It was a different model in a different feature space. Whatever I learned from the v3 walk-forward applies to v3, not necessarily to the production v2 architecture.

---

## Finding 2 — v2's Indian features are LEVELS, not returns

`pipeline/autoresearch/etf_reoptimize.py:_build_indian_features` extracts:
- `india_vix_daily` — close LEVEL (range ~10–30)
- `nifty_close_daily` — close LEVEL (range ~17,000–25,000)
- `fii_net_daily` — raw crores (range ~−5,000 to +5,000)
- `dii_net_daily` — raw crores (range ~−3,000 to +6,000)

These are joined to 29 columns of 1-day ETF returns (range ~−5 to +5) and the joint matrix is fed to the optimizer **without standardization**.

The Karpathy seed weights are correlations with the target. NIFTY level has near-perfect autocorrelation with NIFTY level shifted by 1 day, and `target = sign(nifty.shift(-1))` is itself derived from NIFTY → so the seed weight on `nifty_close_daily` is dominated by autocorrelation, not by predictive content. The signal at decision time is then `weight × NIFTY_close_value`, which is `weight × ~20000` — a huge magnitude that swamps the ETF return contributions unless the optimizer drives that weight tiny.

This is a structural bug in v2 that v3 did NOT inherit (v3 used VIX level + VIX 5d change as separate features, NIFTY 1d/5d returns + RSI). v3's feature engineering is cleaner; v2's is mixed-scale by accident.

---

## Finding 3 — v2 silently DROPS Indian weights at signal time

`pipeline/autoresearch/etf_daily_signal.py:165`:
```python
needed_names = [n for n in etf_names if n in name_to_yf]
```
`name_to_yf` is built from `GLOBAL_ETFS` only. So when `compute_daily_signal` reads the stored weights from `etf_optimal_weights.json`, it **silently discards any weight whose key is not in the GLOBAL_ETFS dict**.

In the current `etf_optimal_weights.json` (verified live):
- 20 weighted features stored
- 17 actually used at signal time (in GLOBAL_ETFS)
- 3 silently dropped: `dii_net_daily` (−0.0219), `fii_net_daily` (−0.0121), `india_vix_daily` (−0.0009)
- Total magnitude dropped: 0.0350 / 39.43 = 0.1% of weight mass

So in the current configuration the leak is small. But the architecture is wrong — if a future Saturday refit finds Indian features predictive, those weights will still be silently zeroed at decision time. The optimizer and the signal computer disagree about what features matter.

---

## Finding 4 — v2 never had PCR in the optimizer

`pipeline/data/positioning.json` is a **stock-level** snapshot (per-symbol OI/PCR for ~211 F&O stocks). It has:
- No top-level `pcr` key
- No top-level `market_pcr` key
- No `NIFTY` block

`_load_positioning` (etf_reoptimize.py:634) reads `data.get("pcr") or data.get("market_pcr") or data.NIFTY.pcr` — currently all three return None. So `pcr` is silently absent. Even if it were present, it would be a single snapshot scalar — not a time series — and the historical builder `_build_indian_features` does not extract PCR at all. **PCR has never been a feature in the optimizer in this build.**

Note: the docstring on line 10 of `etf_reoptimize.py` claims `load_indian_data` returns "FII/DII flows, India VIX, Nifty, Bank Nifty, PCR, RSI-14, breadth indicators". That contract is partially fictitious — PCR is wired in but currently null; RSI/breadth are wired in but only for the latest snapshot, never historical. The history builder uses 4 features: VIX, NIFTY, FII, DII.

Implication for the user's question "if we put PCR back would it help": there is nothing to put back. PCR was never historically present at the optimizer level. To honestly test "PCR-included v3", we would need to BUILD a 5-year historical PCR time series (we don't have one — `positioning.json` is a single snapshot).

---

## Finding 5 — production v2 fit window is short and noisy

`run_reoptimize` builds Indian features from `pipeline/data/daily/*.json` files. Currently 41 such files (2026-03-02 through 2026-04-24). v2's fit joins 3 years of yfinance ETF returns (~750 trading days) with 41 days of Indian features. After `ffill().bfill()` the Indian features become **near-constant** for the 700 days where they have no historical data. So v2's actual production fit is:
- 750 days of ETF returns + 4 Indian features that are constant for ~94% of the window
- The optimizer then finds correlations with `nifty_close.shift(-1).sign()`, where nifty_close is itself a constant for those 94% of days

This is a degenerate fit. It "works" in the sense that the global ETF momentum component still picks up something, but the Indian features cannot contribute information they don't have. v2's claimed 62.3% accuracy was generated under this configuration.

---

## Implication for v3 verdict

My v3 module **fixed several v2 structural issues** but did so in a way that put it in a different design space:
- v3 uses 5d returns (v2 uses 1d) — different signal class
- v3 uses VIX level + 5d change (v2 uses VIX raw level only) — cleaner but different
- v3 uses 5y of historical Indian features via parquet (v2 uses ~6 weeks via JSON ffill) — much better data but different fit
- v3 uses T-1 anchor (v2 doesn't explicitly shift) — eliminates a possible same-day leak in v2 that I haven't confirmed

So the v3 walk-forward verdict (FAIL, mean edge -0.73pp, null p=0.770) does NOT directly refute v2's claimed 62.3%. It refutes a *different model*, in a *different design space*, with *cleaner data*.

To honestly evaluate the production v2 architecture, I need to build a **faithful v2 replicator**:
1. 1-day ETF returns (not 5d)
2. Indian features as raw levels (not engineered)
3. Same `ffill().bfill().fillna(0)` join
4. Same target `sign(nifty.shift(-1))`
5. Same Karpathy random search (2000 iter)

Then run **rolling weekly refit walk-forward** on a window where Indian features have actual history (parquet-based, 5 years). This gives v2 the "best plausible production scenario" — the production architecture with actually-informative Indian features available.

If THAT shows edge, the user is right and the production architecture works. If it doesn't, then the 62.3% is genuinely a methodology artifact and the production system needs deeper rethinking.

---

## What I owe the user

1. Acknowledgement that v3 was not a fair v2 test — it tested v3, not v2.
2. The 5 structural findings above, written up with line-number citations.
3. A rebuild of the rolling-refit harness that **faithfully replicates v2** (not v3) and runs on the parquet-backed 5y panel.
4. A re-stated verdict that distinguishes "v3 design failed" (still true under v3 protocol) from "v2 production architecture has no edge" (NOT YET TESTED).

That last test is what should run next. It is the one that actually answers the user's question.
