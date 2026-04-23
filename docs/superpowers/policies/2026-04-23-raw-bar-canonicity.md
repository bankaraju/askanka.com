# Raw-Bar Canonicity Policy

**Version:** 1.0
**Adopted:** 2026-04-23
**Status:** Enforceable. Code-backed. Overrides convention.
**Principal:** Bharat Ankaraju

---

## 0. Principle

Observed OHLC is canonical. Imputed values are model proxies and are never
substituted for observed prices on the authoritative compliance path.

When raw data is absent or §5A-flagged inside a trade's execution window,
the trade is invalid. It does not run, it does not score, it counts only
toward the §5A bad-data budget. Imputation, if run at all, is a parallel
sensitivity track — analytical aid, not truth.

This policy tightens `backtesting-specs.txt` §5A.4 ("silent repair is
forbidden") by making the no-repair rule an **execution gate**: trades
touched by impaired bars never enter the metric grid.

---

## 1. The Five Rules

1. **Raw bar canonicity.** The raw observed OHLC-V bar is the only source
   of truth for fills, stops, P&L, entry/exit prices, and gate metrics.
   Observed values are never overwritten.
2. **Imputation is a column, never a replacement.** If imputed values
   exist, they live in separate columns tagged `source="proxy_*"` and are
   used only for diagnostics, feature completeness, or sensitivity analysis.
3. **Referee path is raw-only.** The authoritative compliance run
   (`metrics_grid.json`, `gate_checklist.json`) reads no proxy column under
   any circumstance. The main `slippage_grid`, `metrics`,
   `naive_comparators`, `perm_scaling`, `beta_regression`, `portfolio_gate`,
   `direction_audit`, `cusum_decay`, and `impl_risk` outputs derive from
   raw bars only.
4. **Execution-window strictness.** If any bar in a trade's execution
   window (Section 2 below) carries ANY §5A impairment flag (missing,
   duplicate, stale-run, zero-price, zero-volume), the trade is marked
   invalid, excluded from the metric grid, and recorded in the
   invalid-trade log. Each invalid trade also contributes its impaired
   bars to the §5A budget — impairment is counted, not hidden.
5. **Sensitivity track segregation.** Sector-beta imputation, if invoked,
   emits to `metrics_grid_sensitivity.json` and an explicit
   `sensitivity_manifest.json`. The §15.1 gate decision reads
   `metrics_grid.json` only. Sensitivity results are for research commentary,
   never for promotion.

---

## 2. Execution-Window Definitions

Windows are bound to the execution mode declared in the strategy's
manifest (§7.1 of backtesting-specs.txt).

| Mode | Description | Execution-window bars |
|------|-------------|-----------------------|
| MODE A | EOD-close entry, close-to-close hold | T close bar AND T+1 close bar |
| MODE B | 09:45 LTP entry, intraday hold | T session bar (entry + exit same day) |
| MODE C | Intraday adaptive, t+5min fill | T session bar (entry + exit same day) |

For daily-bar backtests, MODE A requires the T and T+1 daily OHLC bars to
be clean; MODE B/C require the T daily OHLC bar to be clean. The 15:20-29
VWAP / 09:45 LTP / t+5min VWAP sub-window refinements apply when
intraday data is used; with daily data the full daily bar is the window.

**Strict interpretation (adopted).** Any §5A flag in the execution-window
bars invalidates the trade. No distinction between missing and stale —
both are treated as non-canonical under this policy. A quiet-volume day
that the detector flags stale is dropped. Lost trades are a feature,
not a bug: tightening the data filter is how we avoid the
2026-04-23 TORNTPOWER trap of "real p-value masked by low permutation
resolution".

---

## 3. Impaired-Bar Classes

From `backtesting-specs.txt` §5A.1, a bar is impaired if it fires any of:

- `missing_bar_count` — no bar present on a business day
- `duplicate_timestamp_count` — two+ bars for the same timestamp
- `stale_quote_count` — identical OHLC for ≥ N consecutive business days (N=3 default; spec leaves N open)
- `zero_or_negative_price_count` — OHLC ≤ 0
- `zero_volume_bar_count` — volume ≤ 0 on a day trading should have occurred

Under Rule 4, any of these in the execution window invalidates the trade.

---

## 4. Sensitivity-Track Imputer (Reference-Only)

If a sensitivity run is requested (`--research-sensitivity` flag on the
compliance runner), missing bars are imputed using a **sector-beta model
with strict pre-t estimation**:

```
r̂_{i,t} = β_i(t) · r_{sector,t}
P̂_{i,t} = P_{i,t-1} · (1 + r̂_{i,t})
```

where:

- **β_i(t)** is estimated from the rolling regression of `r_i` on `r_sector`
  using only bars strictly before t. Minimum 60 pre-t observations;
  otherwise the imputer refuses and the bar stays missing.
- **r_sector** is the NIFTY daily return (primary) or the ticker's declared
  sector-cohort return (fallback, must be logged as such).
- **P_{i,t-1}** is the last observed close before t.
- The residual ε_{i,t} is **not modelled** — it has mean zero by
  construction but its realised value (idiosyncratic news, gaps, liquidity
  shocks) is exactly what the imputer misses. This is the policy's
  central confession: a sector-beta proxy cannot tell you what a stock
  actually did.

### Imputer output contract

Every imputed bar is emitted with:

- `source = "proxy_sector_beta"`
- `beta_window_start`, `beta_window_end` (for audit)
- `beta_value`
- `r_sector_used`
- `P_imputed`
- `P_raw = null` (explicit — no raw to confuse with)

The imputer is in `pipeline/autoresearch/overshoot_compliance/imputer_sector_beta.py`.
Inclusion in the authoritative path is an implementation error; tests
must cover "proxy column is never read by `metrics_grid.json` writer".

---

## 5. Artifact Separation

| Artifact | Content | Decision authority |
|----------|---------|--------------------|
| `metrics_grid.json` | Per-(ticker, direction, slippage-level) metrics from raw-only bars, invalid trades excluded | **Authoritative**. Gate reads this. |
| `metrics_grid_sensitivity.json` | Same shape, computed using proxy imputation for missing bars | Analytical aid. Gate does not read. |
| `invalid_trades.json` | Per-trade rejection log (ticker, date, mode, window-bars, flags) | Audit trail for §5A.4 |
| `sensitivity_manifest.json` | Imputation config, β-window, sector-cohort map, timestamp | Required whenever sensitivity run executes |

The gate checklist emitter (§15.1) is forbidden from reading
`metrics_grid_sensitivity.json`. Any future attempt to write a rule that
uses the sensitivity grid in a decision is itself a policy violation.

---

## 6. Logging Obligations

Per `backtesting-specs.txt` §5A.4, every rejection or imputation must be
logged to `docs/superpowers/data-audits/YYYY-MM-DD-<run>.md`, cross-linked
to the run's `manifest.json::run_id`.

The authoritative run's `manifest.json` gains two new fields:

- `invalid_trade_count` — number of trades dropped under Rule 4
- `invalid_trade_log_path` — pointer to `invalid_trades.json`

If `invalid_trade_count > 0.05 × n_trades_scored`, the manifest also
emits a `WARN_HIGH_REJECTION_RATE` flag for human review. Not a gate
fail — rejection is the correct action — but a signal to the operator
that data quality is eating into statistical power.

---

## 7. Relation to `backtesting-specs.txt`

Fully compatible. This policy:

- **Implements §5A.4** ("silent repair forbidden") as a pre-metric
  execution gate rather than a post-hoc reporting obligation.
- **Tightens §5A.1** by making each named impairment class a
  trade-invalidation trigger in the execution window.
- **Respects §5A.3** budget — impaired bars count toward the 1% / 3%
  thresholds exactly as before; this policy adds trade-level action
  without changing aggregate budget math.
- **Respects §7.1** by binding execution-window scope to the strategy's
  declared mode.
- Cross-referenced as §5A.5 in `backtesting-specs.txt`.

---

## 8. Revocation

Revocation or amendment requires a new signed policy doc at
`docs/superpowers/policies/YYYY-MM-DD-raw-bar-canonicity-v<N>.md`,
supersession noted in this file. No silent overrides.

**Expiry:** none (standing policy). Review triggered if §5A baseline
assumptions change (e.g., NSE migrates to a different data vendor or bar
format).

---

## 9. Implementation References

- Validator: `pipeline/autoresearch/overshoot_compliance/execution_window.py::is_tradeable`
- Runner gate: `pipeline/autoresearch/overshoot_compliance/runner.py::_drop_invalid_trades`
- Sensitivity imputer: `pipeline/autoresearch/overshoot_compliance/imputer_sector_beta.py`
- Tests: `pipeline/tests/autoresearch/overshoot_compliance/test_execution_window.py`,
  `test_imputer_sector_beta.py`, `test_runner_raw_only.py`
