# Task #24 — Data discovery log (2026-04-30)

Per spec section "Source data — news trigger replay" and Anka data validation policy §11, the news-trigger source must be registered + clean before consumption. This log records what was found and how the backtest run is structured around it.

## Sources audited

| Source | Path | Status | Coverage |
|---|---|---|---|
| Equities (canonical) | `pipeline/data/fno_historical/<TICKER>.csv` | ✓ Registered, audit-passed (`docs/superpowers/specs/2026-04-26-fno-historical-data-source-audit.md`) | 5y daily, 276 tickers, 2021-04-23 → 2026-04-22 |
| Regime tape (PIT) | `pipeline/data/research/etf_v3/regime_tape_5y_pit.csv` | **needs build** — `regime_history.csv` is hindsight-contaminated per memory `reference_regime_history_csv_contamination.md` | rebuild required |
| News events history | `pipeline/data/news_events_history.json` | partial | 4,101 items, year breakdown {2024: 15, 2025: 767, 2026: 2,434}; **2021-2023 effectively empty** |
| Live news verdicts | `pipeline/data/news_verdicts.json` | live, daily | last ~6 months only |

## News history gap → dual-mode execution

The 13 INDIA_SPREAD_PAIRS_DEPRECATED baskets fire on classifier-output triggers like `oil_up`, `escalation`, `hormuz`, `sanctions`, `trump_threat`, `defense_spend`, `oil_positive`, `refining_margin`, `energy_crisis`, `de_escalation`, `diplomacy`, `rbi_policy`, `nbfc_reform`, `ev_policy`, `infra_capex`, `tax_reform`. Reconstructing these labels back to 2021-04-23 from raw text is impossible without a 5y archive of headlines we never collected.

The spec section "News trigger replay" already provides for this case ("if available; else simulate via keyword extraction"). Honest interpretation:

### Mode A — news-conditional (2024-04-23 → 2026-04-22)
- Window: ~24 months where `news_events_history.json` has coverage
- Trigger: re-classify each historical headline through `political_signals.py` to derive trigger labels
- Open: basket fires at next-day open if any of its trigger keywords is detected
- Provenance: every event row carries `(url, title, published, classifier_output)` per the news provenance protocol (Task #23 spec)
- This is the truthful test of the basket's claim "news triggers profitable spreads"

### Mode B — trigger-agnostic structural test (2021-04-23 → 2026-04-22)
- Window: full 5y
- Trigger: every trading day fires (no news condition)
- Open: basket opens at every day's open
- This tests whether the long-short pair earns positive expectancy in the absence of news conditioning

### Verdict logic across modes
| Mode A | Mode B | Interpretation |
|---|---|---|
| PASS | PASS | Robust — both news-conditioned and structurally edged |
| PASS | FAIL | News conditioning matters; structural pair is null without trigger |
| FAIL | PASS | Pair is structurally edged; news adds noise or is irrelevant |
| FAIL | FAIL | Basket dies — neither news nor structure pays |
| PASS | n/a | Can't test structurally because pair dataset incomplete |

Both modes are reported per (basket × regime × hold) with full cost discipline (20bp + 30bp). Verdict bar applies independently to each mode; the basket is "PROMOTABLE" only on Mode A pass. Mode B PASS without Mode A is a "STRUCTURAL_PAIR_PROMOTABLE_TO_OWN_HYPOTHESIS" — it gets its own forward-only single-touch holdout, NOT a news-conditioned production trade.

## Data-validation gate satisfied

- Equities CSVs: registered + audited per existing audit doc.
- News history file: registered as PARTIAL (Mode A only). Limitation documented above. No claim is made of edge over the 2021-2023 window using news triggers.
- PIT regime tape: must be rebuilt from V3 CURATED weights before Mode A or Mode B run; `regime_history.csv` must NOT be used.

## Run plan

1. Build PIT regime tape over 5y from V3 CURATED weights → `regime_tape_5y_pit.csv` (offline, one-shot, deterministic given weights)
2. Mode A run: 2024-04-23 → 2026-04-22, news-conditioned, 13 baskets, per-regime, per-hold
3. Mode B run: 2021-04-23 → 2026-04-22, trigger-agnostic, 13 baskets, per-regime, per-hold
4. Aggregate across modes, write `summary_<date>.csv` and `findings_<date>.md` per spec
5. Per-basket verdict per the dual-mode logic above

## Honest expectation

Mode B will likely produce some false positives — without the news condition, pairs that mean-revert structurally over 5y will pass the bar even if their live paper P&L was driven by news conditioning. That's exactly why we need Mode A as the primary verdict: it ties the result back to the actual live mechanism.

Mode A may produce few results because trigger-firing days are rare (~5-15% of trading days per basket per back-of-envelope) and 24 months × 5-15% × 13 baskets divided across 5 regimes × 3 holds = some cells will have n < 10 (INSUFFICIENT_N).
