# H-2026-04-26-001 — σ-break mechanical mean-reversion (design)

**Hypothesis IDs covered:**
- **H-2026-04-26-001** — Unconditional σ-break mean-reversion (production candidate)
- **H-2026-04-26-002** — Same rule, regime-gated (skip NEUTRAL days)
- **H-2026-04-26-003** — NEUTRAL-day long-only intraday (sister, separate alpha source) — **deferred to its own spec; not in this registration.**

This spec registers H-2026-04-26-001 and H-2026-04-26-002 as **sister cohorts on the same signal stream**: both consume identical entry signals; they differ only in a downstream decision filter. Both are pre-registered together because the gate decision is binary on a single column — they are not testing different signals, they are testing whether one filter dominates the other.

## 1. Claim

**H-2026-04-26-001 (unconditional):** When a stock's intraday correlation residual against its sectoral index breaks to ≥ 2.0 standardised deviations on the day, taking a position that fades the divergence (LONG the laggard / SHORT the leader) at 09:30 IST market price, with an ATR(14)×2 stop and a trailing exit (arms at +0.6%, trails by 1.2%), and a hard mechanical close at 14:30 IST, will achieve held-out hit rate ≥ 70% and mean per-trade P&L ≥ +0.5% (gross of slippage) over the 30-day forward paper window 2026-04-27 → 2026-05-26.

**H-2026-04-26-002 (regime-gated):** Same rule, restricted to days where the daily regime label (V4 taxonomy: CAUTION / NEUTRAL / RISK-ON / EUPHORIA / RISK-OFF, sourced from `pipeline/data/regime_history.csv`) is **not NEUTRAL**, will achieve held-out hit rate ≥ 75% and mean per-trade P&L ≥ +1.0% (gross of slippage) over the same 30-day window AND deliver Sharpe ≥ 1.5× the unconditional rule on a per-day-deployed basis.

Both claims are evaluated on the same `recommendations.csv` ledger with the gate state recorded as a column tag (`regime_gate_pass: bool`); H-2026-04-26-002's verdict reads only the rows where `regime_gate_pass=True`.

## 2. Pre-exploration disclosure

This rule was discovered via a 60-day in-sample mechanical replay (`pipeline/data/research/mechanical_replay/v2/trades_no_zcross.csv`, generated 2026-04-25 from canonical_fno_research_v1, 154 tickers, replay window 2026-02-24 → 2026-04-24). The replay-discovered numbers were:

| Slice | n | Hit | Mean P&L | Total |
|---|---|---|---|---|
| All ≥2σ (unconditional) | 42 | 92.86% | +1.66% | +69.83pp |
| ≥2σ × non-NEUTRAL | 37 | 94.59% | +1.76% | +65.02pp |
| ≥2σ × NEUTRAL only | 5 | 80.00% | +0.96% | +4.81pp |

**These numbers may not be cited as evidence for the production rule.** They are in-sample and the rule was selected from a search over: (a) PCR-confirmed vs PCR-stripped slice, (b) Z_CROSS exit vs TIME_STOP+TRAIL+ATR exit, (c) σ thresholds {1.5, 2.0, 2.5, 3.0, 4.0}, (d) regime gating on/off. The selection was driven by the observation that PCR-confirmed slice was −3.30pp / 60 days while PCR-stripped slice was +169.77pp / 388 trades, and within PCR-stripped the ≥2σ subset hit 92.86% in-sample.

**Search size for §10.4 / §11.2 multiple-comparison adjustment:** at least 4 PCR axes × 3 exit-rule axes × 5 σ-threshold axes × 2 gating axes = **120 cells searched**. The Bonferroni-adjusted significance threshold for any single cohort claim is α/120 = 0.05/120 ≈ **0.000417**.

**No held-out data was used to choose any rule parameter.** The 30-day forward window is the single-touch holdout for both H-2026-04-26-001 and H-2026-04-26-002.

## 3. Data lineage

| Dataset ID | Path | Tier | Required Acceptance |
|---|---|---|---|
| canonical_fno_research_v3 | `pipeline/data/canonical_fno_research_v3.json` | D2 | Approved-for-research |
| nse_sectoral_indices_v1 | `pipeline/data/sectoral_indices/*.csv` | D2 | Approved-for-research |
| regime_history_v4 | `pipeline/data/regime_history.csv` | D2 | Approved-for-research |
| live_kite_ltp | Kite Connect API | D1 (live, no audit) | Operational; not used for backtest, only for paper-trade entry/exit prices |

**Universe:** 273 tickers from canonical_fno_research_v3 (243 with full 5y depth + 20 short ≥3y + 10 PIT-aliased corporate actions). The 2 truly missing tickers (PEL, SAMMAAN — both Kite-only) are excluded from this hypothesis.

**Adjustment mode:** F&O equity series = `dividend_adjusted_close`; sectoral indices = `total_return_index`. Per `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` §10.

**Point-in-time correctness:** The PIT ticker list at `docs/superpowers/specs/tickers list .xlsx` provides current-symbol → past-name mapping for 9 corporate actions. The `pit_alias_map` in canonical_fno_research_v3 carries 5 active aliases. No look-ahead in universe selection: tickers IPO'd within the holdout window are excluded.

## 4. Signal construction

**Per-day, per-ticker Z computation:**
1. For each ticker T in canonical_fno_research_v3, identify its sectoral index S using the F&O sector mapping in `pipeline/sector_mapper.py`.
2. At signal time (09:25 IST), compute the residual return: `r_residual(T,t) = r_T(t) - β(T,S) × r_S(t)` where β is the trailing 60-day OLS slope of T on S, refit nightly.
3. Compute the trailing 60-day mean μ and standard deviation σ of `r_residual(T)`.
4. Z(T,t) = `(r_residual(T,t) − μ) / σ`.
5. **Trigger:** |Z(T,t)| ≥ 2.0.
6. **Direction:** if Z > 0 (T outperformed S), the position is **SHORT T** (T is the leader, expected to revert down). If Z < 0, position is **LONG T** (T is the laggard, expected to revert up).

This is the same signal pipeline that produces `pipeline/data/correlation_breaks.json` daily.

## 5. Trade rules (locked)

| Parameter | Value | Why locked |
|---|---|---|
| Entry timestamp | 09:30 IST | First clean print after open auction; matches in-sample replay |
| Entry price | Kite LTP at 09:30 | Live-execution proxy |
| Stop loss | ATR(14) × 2.0 from entry | ATR computed from canonical_fno_research_v3 daily bars at end of T-1 |
| Trail | Arms at +0.6% profit, trails by 1.2% | In-sample optimum among {0.4/0.8, 0.6/1.2, 1.0/2.0} |
| Hard exit | 14:30 IST mechanical close at LTP | No overnight; matches in-sample TIME_STOP |
| Position size | Equal-notional ₹50,000 per leg | Same as old phase_c_shadow for comparability; size is not the hypothesis |
| What is NOT used | PCR, OI, options sentiment | Indian options OI too sparse; in-sample showed PCR-confirmed slice was the loser |
| What is NOT used | Z-cross exit (residual returning to mean) | In-sample showed Z_CROSS exit cost more than it saved |

## 6. Splits

- **In-sample (already consumed):** 2026-02-24 → 2026-04-24 (60 trading days, 388 unfiltered trades, 42 ≥2σ trades).
- **Single-touch holdout (forward paper test):** 2026-04-27 → 2026-05-26 (≈21 trading days; expected ≥30 trades at 0.7/day historical rate, but trade volume varies with regime).
- **No re-fit, no re-tuning, no re-selection during the holdout.** Per backtesting-specs.txt §10.4, any parameter change after 2026-04-27 09:30 IST consumes the single-touch and requires fresh hypothesis registration.

## 7. Comparator baselines (§15.1 §9B.1 ladder)

| Baseline ID | Description | Required margin to clear |
|---|---|---|
| **B0** — always-prior | Open random LONG/SHORT on every signal day at 09:30, exit 14:30 | Margin ≥ +0.5% mean P&L per trade |
| **B1** — random-direction | Same signal trigger (|Z|≥2.0), but flip a coin for LONG vs SHORT | Margin ≥ +0.3% mean P&L per trade |
| **B2** — trend-follow opposite | Same signal trigger, but take the OPPOSITE side (LONG leader / SHORT laggard) — must LOSE money | If B2 ≥ 0, our edge isn't really mean-reversion → kill |
| **B3** — passive long index intraday | Long NIFTY at 09:30, close at 14:30 every day | Margin ≥ +0.5% over passive intraday beta |
| **B4** — random-day, same direction | Pick same number of random days from the holdout, take same side | Margin ≥ +0.5% mean P&L per trade |

H-2026-04-26-001 must clear **B0, B1, B2 (with negative sign), B3, and B4 simultaneously** for §15.1 PASS.

H-2026-04-26-002 must additionally clear: **per-day-deployed Sharpe ≥ 1.5× H-2026-04-26-001** AND mean P&L per trade ≥ +1.0% (the regime-gating premium claim).

## 8. §15.1 verdict ladder

| Gate | H-2026-04-26-001 PASS criterion | H-2026-04-26-002 PASS criterion |
|---|---|---|
| §5A — sample size | n ≥ 30 trades in holdout | n ≥ 20 in non-NEUTRAL holdout days |
| §6 — pre-registered claim met | hit ≥ 70% AND mean ≥ +0.5% | hit ≥ 75% AND mean ≥ +1.0% |
| §7 — beats all baselines | Margin > 0 vs every baseline in §7 above | Same + Sharpe gate |
| §8 — direction integrity | B2 (trend-follow opposite) mean P&L < 0 with |mean| ≥ +0.3% | Same |
| §9 — no execution drag killing alpha | Mean P&L net of 0.05% per-side slippage ≥ +0.4% | ≥ +0.9% |
| §9A — fragility | Out-of-sample-ish robustness via per-week stratification: at least 3 of 4 holdout weeks individually deliver mean ≥ 0 | Same |
| §9B.1 — comparator margin | Margin ≥ +0.5% nats vs B0 | Same |
| §9B.2 — permutation null | p < 0.000417 (Bonferroni for 120-cell search) on hit-rate permutation | Same |
| §10 — single-touch hygiene | No parameter change post-2026-04-27 09:30 | Same |
| §11B — calibration-residualised margin | Hit-rate margin holds after deflating for hit-rate base rate | Same |

**Failure of any gate = FAIL = no real-capital deployment, no re-run with adjusted parameters.** Per §10.4, a fresh hypothesis registration is required for any retry.

## 9. Calibration backstop

Not applicable — this is a binary direction decision, not a probability forecast. The §11B residualisation is on hit-rate base rate.

## 10. Deployment surface (post-PASS)

**Tier 1 (PASS holdout + Tier 1 perm null):** Move from PRE_REGISTERED → APPROVED_FOR_PAPER_TRADING_TIER_1. Continue paper-trading with full instrumentation for additional 60 days.

**Tier 2 (PASS Tier 1 + Tier 2 block-bootstrap):** Move to APPROVED_FOR_REAL_CAPITAL_PILOT. Real capital at 0.5% portfolio risk per trade, hard cap of 5 concurrent positions.

**Tier 3 (PASS Tier 2 + Tier 3 synthetic minute paths across regimes):** Move to APPROVED_FOR_PRODUCTION. Real capital at standard portfolio sizing.

**No Tier may be skipped. No Tier may be entered while a lower-Tier validation is in-flight.**

## 11. Risks pre-registered

1. **Regime-overfit:** The in-sample window was war/CAUTION-dominated (139 of 388 trades, 7 of 30 days). Long-run NEUTRAL is ~85% of trading time. The holdout is not guaranteed to be NEUTRAL-heavy either; regime mix in the holdout is a confounder for both hypotheses. Mitigation: post-holdout regime stratification of P&L by cohort.

2. **NEUTRAL-regime n is small in-sample (5 trades):** the +0.96% mean / 80% hit in NEUTRAL is statistically meaningless. H-2026-04-26-002's claim "regime-gating helps" cannot be cleanly tested with only 5 NEUTRAL trades in-sample. The holdout will produce additional NEUTRAL trades; verdict criterion specifically requires ≥30 NEUTRAL trade-days accumulated before any real-capital decision (separate from §15.1 PASS).

3. **Live execution drag:** Replay assumes perfect 09:30 fills and 14:30 closes. Real Kite execution has slippage (~0.05% per side typical for F&O liquid names), occasional partial fills, and gap-open scenarios that bypass the ATR stop. §9 net-of-slippage gate addresses point estimate; gap-open risk is residual and accepted.

4. **Sectoral-index β instability:** β(T,S) refit nightly may swing on news days; a stale or noisy β produces spurious Z signals. Mitigation: drop signals on days where β(T,S) shifted by >25% vs prior 5-day median (already implemented in correlation_breaks.json filter).

5. **Survivorship bias in canonical_fno_research_v3:** universe is current F&O constituents minus IPOs without history. Stocks that exited F&O in the past 5y are absent. Documented bias bound: per the dataset audit doc, expected effect on backtest hit rate is ≤2 pp.

## 12. Compute budget

- **Daily paper-trade execution (09:30 + 14:30):** ~30 sec per cycle (Kite LTP fetch + CSV append).
- **Tier 1 permutation null (planned 2026-04-27 → 2026-05-01):** 100,000 label permutations × ≈42 trades × ATR/trail recompute = est. 4-6 hours on VPS.
- **Tier 2 block bootstrap (planned next week):** est. 8-12 hours on VPS.
- **Tier 3 synthetic minute paths (planned 2026-05-04+):** est. 24-48 hours on VPS.

## 13. Out of scope for v1

- Per-stock entry size tuning (using equal ₹50,000 notional).
- Spread / pair-trade variants (the rule is single-leg directional).
- Cross-sectional ranking (no relative-strength filter beyond the σ trigger).
- Options-overlay variants (no synthetic options in this rule).
- Intraday re-entry (one trade per ticker per day).
- Holding-period sweep (locked at 09:30 → 14:30).

## 14. Cohort tags written to recommendations.csv

Each row in `pipeline/data/research/h_2026_04_26_001/recommendations.csv` carries:

| Column | Type | Purpose |
|---|---|---|
| signal_id | str | `BRK-YYYY-MM-DD-TICKER` |
| ticker | str | F&O symbol |
| date | YYYY-MM-DD | Trading day |
| sigma_bucket | str | `<2.0` / `[2.0,3.0)` / `[3.0,4.0)` / `[4.0,5.0)` / `5.0+` |
| regime | str | V4 label from regime_history.csv |
| sectoral_index | str | NIFTYBANK / NIFTYIT / etc. |
| side | str | LONG / SHORT |
| classification | str | OPPORTUNITY_LAG / OPPORTUNITY_OVERSHOOT / POSSIBLE_OPPORTUNITY |
| **regime_gate_pass** | bool | True if regime ≠ NEUTRAL (H-2026-04-26-002 verdict reads this) |
| entry_time | ISO 8601 | Actual fill time |
| entry_px | float | Kite LTP at entry |
| atr_14 | float | ATR(14) used for stop computation |
| stop_px | float | Hard stop level |
| trail_arm_px | float | +0.6% level |
| trail_dist_pct | float | 1.2 |
| exit_time | ISO 8601 | Actual exit time |
| exit_px | float | Kite LTP at exit |
| exit_reason | str | TIME_STOP / TRAIL / STOP_LOSS / GAP |
| pnl_pct | float | (exit_px − entry_px) / entry_px × side_sign |
| status | str | OPEN / CLOSED |

The `recommendations.csv` is **append-only, forward-only**; rows are never edited after CLOSED. A separate `corrections.csv` carries any post-hoc audit adjustments (slippage re-computation, etc.).

## 15. Single-touch hygiene

- The single-touch holdout window is **2026-04-27 09:30 IST → 2026-05-26 14:30 IST**.
- Before 09:30 IST 2026-04-27, this spec must be:
  - [x] Written and committed to `docs/superpowers/specs/`
  - [ ] Registered in `docs/superpowers/hypothesis-registry.jsonl` with `terminal_state: PRE_REGISTERED`
  - [ ] Linked from `pipeline/h_2026_04_26_001_paper.py` docstring
  - [ ] Validated by a smoke-test run (not against real Kite — against a synthetic dummy LTP stream)
- During the holdout window: no parameter change, no rule modification, no spec amendment — per backtesting-specs.txt §10.4 strict.
- An amendment is permitted only if (a) it is purely a **bug fix** that does not change the in-spec rule (e.g., timezone fix, file path correction), AND (b) it is documented in the registry with `single_touch_status: INTACT_holdout_not_yet_consumed_bug_fix_only`. Any change to entry/exit logic, threshold, or filter consumes single-touch.

## 16. References

- `docs/superpowers/specs/backtesting-specs.txt` — canonical §-numbered governance
- `docs/superpowers/specs/anka_data_validation_policy_global_standard.md` — data acceptance §
- `docs/superpowers/specs/2026-04-25-mechanical-60day-replay-v2-design.md` — in-sample replay engine
- `docs/superpowers/specs/2026-04-25-canonical-fno-research-dataset-audit.md` — universe audit (v1; v3 inherits adjustment_mode block)
- `docs/superpowers/specs/tickers list .xlsx` — PIT ticker source
- `pipeline/data/canonical_fno_research_v3.json` — universe pin
- `docs/trader-briefings/2026-04-26-eod-briefing.md` — plain-language version
