# Intraday Mean-Reversion after Regime-Conditional Peer-Cohort Dislocations: A Pre-Registered Empirical Test

**Draft (v0):** 2026-04-25
**Author:** Bharat Ankaraju / Anka Research
**Status:** Pre-analysis plan — committed *before* empirical results are read. All decision rules fixed in advance to preclude retrofitting.
**Related documents:**
- Implementation plan: `docs/superpowers/plans/2026-04-24-correlation-break-hardening-and-narrative.md`
- v0 backtest code: `pipeline/autoresearch/intraday_break_replay.py`
- Live engine source: `pipeline/autoresearch/reverse_regime_breaks.py`, `pipeline/signal_tracker.py`

---

## Abstract

The Anka Research Phase-C engine trades stocks that diverge more than 1.5
standard deviations from their regime-conditional peer-cohort return
expectation, classified as LAG (stock moved in the peer direction but less
than 30% as far as expected). The hypothesis: such dislocations mean-revert
within the trading day. Over the first three forward-test days (2026-04-22
through 2026-04-24), the live strategy produced five consecutive overnight
winners with cumulative P&L of roughly 25 percentage points, while every
adjacent daily-OHLC backtest (H-2026-04-23-002, H-2026-04-24-003) has failed
statistical gates. This paper specifies a pre-registered 60-day intraday
replay — using the same 1.5σ trigger, same regime-conditional expectation,
same Z_CROSS and 14:30 exit rules — to determine whether the live strategy
has a measurable positive-expectancy edge, or whether the observed profits
are attributable to (a) luck in a 3-day window and (b) a known entry-price
look-ahead bias in the shadow ledger. The test is regime-agnostic by
construction: σ is itself normalised within each regime, so the directional
verdict does not require uniform regime coverage in the sample. Verdict
criteria are frozen ex ante and reported in §8.

---

## 1. Introduction

### 1.1 Motivation

Pairs trading and statistical arbitrage have a long empirical literature
grounded in the assumption that assets with economically similar payoffs
exhibit mean-reverting return differentials at short horizons (Gatev,
Goetzmann & Rouwenhorst 2006; Do & Faff 2010). The Anka Research Phase-C
engine applies a related idea at a finer grain: instead of pairs, it defines
a per-stock *peer cohort* (empirical, via the Phase-A reverse-regime
profile), and instead of long-horizon spread convergence, it bets on
same-session closure of an open-to-intraday divergence.

The innovation is regime conditioning. Rather than comparing a stock's
return to a static benchmark, the engine compares to a benchmark that is
itself a function of the market's current risk regime (RISK-OFF, CAUTION,
NEUTRAL, RISK-ON, EUPHORIA). The thesis is that cohort-relative
dislocations carry information about same-session reversion conditional on
regime, in a way that neither static pairs nor unconditional benchmarks
would detect.

### 1.2 Why this paper

Three days of profitable live trades are not evidence. They are a
hypothesis-generation event. Two classes of confounds prevent direct
attribution of those profits to edge:

1. **Known measurement bug.** The live shadow ledger records entry at the
   09:15 opening snap, but the σ-trigger itself cannot fire before the
   first intraday scan at 09:25–09:30. This is a look-ahead: the
   recorded entry price is one we could not have achieved. The magnitude
   is stock- and day-specific; it plausibly inflates live P&L by 30–50%
   on days where the stock moves favourably in the first 15 minutes.

2. **Daily-OHLC backtest mismatch.** The two closest formal
   tests — H-2026-04-23-002 (persistent-break EOD classification,
   T+1..T+5 drift) and H-2026-04-24-003 (asymmetric-threshold
   Lasso) — both failed compliance gates. But neither tested the
   same-session intraday trigger-and-exit structure the live engine
   uses. They measured an adjacent strategy, not this one.

This paper specifies the test that actually measures the live engine.

### 1.3 Contribution

A 60-day, minute-bar replay of the full F&O universe under execution rules
that match the live engine without the look-ahead bug, with a
pre-registered verdict rule, ex-ante robustness checks, and a
disentanglement of intraday-reversion edge from late-day time-stop drift.

---

## 2. Data

### 2.1 Sample

- **Universe:** All tickers present in `reverse_regime_profile.json` with
  at least one regime transition having statistics for the relevant
  period — approximately 210 Indian F&O single-stock futures.
- **Temporal coverage:** Last 60 trading days available from Kite Connect
  historical minute bars (approximately 2026-01-24 through 2026-04-24,
  excluding holidays).
- **Frequency:** 1-minute OHLC bars, fetched from Kite Connect
  `historical_data` API.
- **Benchmarks:** NIFTY and INDIAVIX 1-minute bars for the same window.

### 2.2 Auxiliary data

- **Phase-A profile** (`reverse_regime_profile.json`): frozen at pre-test
  vintage; provides `avg_drift_1d`, `std_drift_5d`, `avg_drift_5d`,
  `tradeable_rate` by ticker × `"FROM→TO"` regime transition key.
- **Regime history** (`pipeline/data/regime_history.csv`): daily regime
  label for each trading day in the window; authoritative trading-day
  calendar.
- **Cost schedule:** flat 20 basis points round-trip (10 bps per side),
  treated as a conservative universe average.

### 2.3 Survivorship

The F&O universe list is taken from the live profile as of 2026-04-25, not
reconstructed vintage-by-vintage. Delisted or demoted names from prior
months are therefore absent. This is a mild survivorship exposure but its
direction is ambiguous: names that failed tend to be high-vol underperformers,
which could have either inflated or deflated σ-trigger edge. We note the
exposure and defer a vintage-correct rebuild to a compliance-grade follow-up.

---

## 3. Definitions and notation

Let $P_{it}$ denote the traded price of stock $i$ at minute $t$, with $t$
indexed in minutes from market open. Let $O_i$ denote the 09:15 opening
price on the day in question. Define the *open-relative return*:

$$R_{it} = \left(\frac{P_{it}}{O_i} - 1\right) \times 100 \qquad \text{(percent)}$$

Let $r(i, g)$ denote the Phase-A-profile lookup for stock $i$ under regime
transition $g$, returning two scalars: $\mu_{ig}$ (the regime-conditional
1-day drift mean, in fractional units) and $\sigma_{ig}^{(5d)}$ (the
regime-conditional 5-day drift standard deviation, in fractional units). We
convert to daily units and percent:

$$E_{ig} = \mu_{ig} \times 100 \qquad S_{ig} = \frac{\sigma_{ig}^{(5d)}}{\sqrt{5}} \times 100$$

For stock $i$ at scan time $t$ on a day with regime transition $g$, the
*normalised dislocation* is:

$$Z_{it} = \frac{R_{it} - E_{ig}}{S_{ig}} \qquad \text{if } S_{ig} > 0.1, \text{ else } 0$$

This is the quantity the live engine compares to the 1.5 threshold. Because
both $E_{ig}$ and $S_{ig}$ are drawn from the regime-$g$ slice of the
profile, $Z_{it}$ is *regime-normalised*: a $Z = 2$ event is equivalently
rare in CAUTION as in RISK-ON. The test is therefore regime-agnostic by
construction.

The *geometric classification* at scan time follows the live engine
(`reverse_regime_breaks.py:114-133`):

$$\text{geom}(E, R) = \begin{cases}
\text{DEGENERATE} & \text{if } |E| < 0.1 \text{ or } |R - E| < 0.1 \\
\text{OVERSHOOT} & \text{if } \operatorname{sgn}(E) = \operatorname{sgn}(R - E) \\
\text{LAG} & \text{otherwise}
\end{cases}$$

A *qualifying trigger* for this paper requires:

1. $|Z_{it}| > 1.5$
2. $\text{geom}(E_{ig}, R_{it}) = \text{LAG}$
3. PCR class does not actively disagree with the expected direction (from
   positioning data, neutral if unavailable)
4. No open-interest anomaly flag on this stock for the day
5. No existing open replay-trade on stock $i$ today (one-per-ticker-per-day)

These conditions reproduce the live engine's `classify_break` path for
`OPPORTUNITY_LAG / ADD`.

### 3.1 The trade

Upon qualifying trigger at scan time $t$:

- **Entry price** $P^{\text{entry}}_i = P_{i, \; t + 15 \text{min}}$
  (the *next* 15-minute scan after trigger — not $t$ itself, not the
  open; this is the critical deviation from the live shadow ledger's
  open-snap convention).
- **Direction:** LONG if $E_{ig} > 0$, else SHORT.
- **Stop price:** $P^{\text{stop}}_i = P^{\text{entry}}_i \cdot
  (1 - d \cdot 1.5 \cdot S_{ig} / 100)$ where $d = +1$ for SHORT, $-1$
  for LONG. (A 1.5σ adverse move terminates the position.)

**Exit cascade** (first to fire, checked at per-minute cadence after
entry):

1. **STOP:** price breaches $P^{\text{stop}}_i$ within any 1-minute bar
   → exit at that bar's close.
2. **Z_CROSS:** at the *next* 15-minute scan point ($t + 30, t + 45, …$),
   recompute $Z$; if $|Z| \le 1.5$, exit at that scan's price.
3. **TIME_STOP:** 14:30 IST, regardless of $Z$ state, exit at the 14:30
   1-minute bar close.

STOP has priority on ties within a single minute (worst-case assumption).
Costs: 20 bps subtracted from gross P&L percent.

---

## 4. Hypotheses

### 4.1 Null hypothesis (H₀)

The σ > 1.5 LAG trigger has no predictive power for same-session
mean reversion after realistic costs. Formally:

$$H_0: \quad \mathbb{E}[\pi_j] \le c \quad \text{where } c = 20 \text{ bps}$$

and $\pi_j$ is the net P&L in percent (basis points ÷ 100) of trade $j$,
with expectation taken over the population of qualifying triggers in the
target universe and horizon.

Under H₀, observed live P&L is attributable to a combination of: (i) the
3-day sample being a noise-driven streak, (ii) the open-snap look-ahead
inflating reported P&L by a stock- and day-specific amount, (iii)
selection bias in which trades the live ledger chose to book.

### 4.2 Alternative hypothesis (H₁)

The trigger identifies genuine same-session mean-reverting dislocations:

$$H_1: \quad \mathbb{E}[\pi_j] > 40 \text{ bps}$$

The 40-bps bar is chosen as 2× round-trip cost — a minimum-effect
threshold below which the strategy cannot survive real execution
(slippage, IOC fill rates, borrow for SHORTs).

### 4.3 Sub-hypotheses (pre-specified, exploratory)

- $H_{1a}$: $\mathbb{E}[\pi_j \mid |Z| \in [2, 3)] > \mathbb{E}[\pi_j \mid |Z| \in [1.5, 2)]$
  (rarer dislocations should carry stronger reversion).
- $H_{1b}$: At least 60% of trades exit via Z_CROSS before 14:30
  (clean intraday reversion rather than time-stop drift).
- $H_{1c}$: $|\mathbb{E}[\pi_j \mid \text{LONG}] - \mathbb{E}[\pi_j \mid \text{SHORT}]| < 30 \text{ bps}$
  (direction is symmetric — no regime bias masquerading as strategy edge).

These sub-hypotheses are pre-registered but *not* used as gating criteria.
They inform interpretation, not pass/fail. Only $H_1$ (main) gates the
verdict.

---

## 5. Empirical strategy

### 5.1 Estimator

For $N$ qualifying trades $\{\pi_j\}_{j=1}^N$ in the 60-day window:

$$\hat\mu = \frac{1}{N} \sum_{j=1}^{N} \pi_j$$

**Standard error:** cluster-robust at the ticker-day level, since multiple
triggers on the same ticker (prohibited by one-per-ticker-per-day
rule — redundant) or multiple triggers on the same day across tickers
(permitted — exposed to the same market shock) are not independent:

$$\operatorname{SE}_{\text{cluster}}(\hat\mu) = \sqrt{\frac{1}{N(N-1)} \sum_c \left( \sum_{j \in c} (\pi_j - \hat\mu) \right)^2}$$

where $c$ indexes ticker-day clusters (in practice, each cluster has
exactly one observation under one-per-ticker-per-day, so this collapses to
a day cluster — we use day-cluster SE).

### 5.2 Primary test statistic

$$t = \frac{\hat\mu - 40}{\operatorname{SE}_{\text{cluster}}(\hat\mu)}$$

Compare to $t$-distribution with degrees of freedom equal to number of
distinct trading-day clusters − 1 (not $N - 1$). One-sided test (the
strategy claim is directional).

### 5.3 Power calculation

Assume under H₁ a true effect $\mu = 50$ bps with per-trade noise
$\sigma_\pi = 150$ bps (plausible for 1-day holding period returns on
Indian F&O single stocks, cf. Rajan & Srinivasan 2021 for F&O vol
estimates). Expected trades $N \in [300, 600]$ over 60 days.

Minimum detectable effect at $\alpha = 0.05$ (one-sided), power 0.80:

$$\text{MDE} = (z_{0.95} + z_{0.80}) \cdot \frac{\sigma_\pi}{\sqrt{N}} \approx 2.49 \cdot \frac{150}{\sqrt{N}}$$

For $N = 300$: MDE ≈ 22 bps. For $N = 600$: MDE ≈ 15 bps.

Both comfortably below the 40-bps H₁ bar, so the study is adequately
powered to distinguish H₀ from a true 40+ bps edge. Cluster correction
will inflate SE by a factor of roughly $\sqrt{1 + \rho(m - 1)}$ where $m$
is average cluster size and $\rho$ intra-cluster correlation; with
$m \approx 5$ and $\rho \approx 0.2$ this inflates MDE by ~40%, giving
MDE ≈ 30 bps at $N = 300$. Still below the 40-bps bar. Study retains
adequate power.

### 5.4 Robustness checks (pre-specified)

| Check | Purpose | Expected effect if H₁ true |
|---|---|---|
| Double costs to 40 bps round-trip | Survives higher real-execution friction | $\hat\mu$ drops ~20 bps, still > 20 bps |
| Exclude σ ∈ [1.5, 2) (tighter trigger) | Tests whether edge is concentrated in rare events | $\hat\mu$ increases |
| VWAP(entry → entry+5min) entry price | Smoother execution assumption | $\hat\mu$ similar ±5 bps |
| Exclude small-cap F&O (ADV < ₹100 cr) | Eliminates the worst slippage names | $\hat\mu$ similar ±10 bps |
| Shuffle direction (LONG ↔ SHORT random) | Direction-label permutation null | $\hat\mu$ → 0 |
| Shuffle entry to random minute in day | Timing-signal permutation null | $\hat\mu$ → 0 |

Each robustness result is reported with point estimate and cluster-robust
CI. We do not multiple-test-correct these ex ante because they are
interpreted as diagnostic rather than as separate confirmatory tests.

---

## 6. Identification

### 6.1 Threats to causal interpretation

For the verdict to reflect genuine strategy edge rather than artefact:

- **No look-ahead.** Entry is next-scan price, strictly after trigger.
  Exit uses per-minute bars strictly after entry. No variable appearing
  in the exit rule is observable at trigger time. ✓
- **No data-snooping.** The profile is frozen at a vintage pre-dating
  the 60-day test window. σ-threshold is fixed at 1.5 (live engine's
  value), not tuned on the sample. ✓
- **No survivorship.** Universe definition is acknowledged survivorship-
  exposed (§2.3); robustness check on small-caps partly addresses it.
  Direction of bias ambiguous. ⚠
- **No selection.** Every qualifying trigger is taken; no discretion.
  Clustering controls for same-day correlation. ✓
- **No regime cherry-pick.** σ normalisation makes regime mix
  irrelevant to the directional verdict. ✓

### 6.2 Residual identification concerns

- **News confound.** σ triggers may correlate with scheduled corporate
  events (earnings, block deals, regulatory filings). If so, the "edge"
  is really a news-impact trade being detected via price reaction.
  Under this confound, the trade has *some* real expectancy but the
  attribution (to σ-dislocation vs to news reaction) is wrong, and the
  strategy's generalisability outside news windows is uncertain.
  Mitigation: robustness check excluding triggers within 30 min of
  known earnings announcements (deferred — requires corporate-action
  data join not yet wired).
- **Microstructure.** 1-minute prices on low-ADV F&O names can be stale
  or bid-side-only. ADV-filtered robustness check partially addresses.
- **Peer-cohort endogeneity.** The Phase-A profile defines expectations
  based on historical cohort behaviour, but if the live cohort is
  itself reacting to the lagging stock (reverse causality), the
  stock-catches-peers interpretation flips. Unlikely at daily horizons
  but non-zero in extreme names.

---

## 7. Reporting

### 7.1 Primary result

$\hat\mu$, SE, $t$-statistic, one-sided p-value, 95% CI.
Hit rate, trade count, median duration (minutes).

### 7.2 Pre-specified secondary table

Breakdown by σ bucket (three rows), direction (two rows), exit path
(three rows), regime (up to five rows), with $\hat\mu$ and $N$ per cell.

### 7.3 Robustness panel

One row per check in §5.4 with $\hat\mu$ and CI.

### 7.4 Trade-level artefact

Parquet at `pipeline/autoresearch/data/intraday_break_replay_60d.parquet`
with one row per trade: identifier, date, ticker, regime, transition,
direction, trigger_time, trigger_z, entry_time, entry_price,
stop_price, exit_time, exit_price, exit_reason, gross_pnl_pct,
net_pnl_pct, duration_min, sigma_bucket.

---

## 8. Verdict rule (frozen ex ante)

| Condition | Verdict | Action |
|---|---|---|
| $\hat\mu > 40$ bps AND $p_{H_0} < 0.05$ | **PASS** | Proceed to execution-rule hardening (Workstream B of the paired plan). Schedule compliance-grade re-test in 90 days on expanded sample. |
| $20 < \hat\mu \le 40$ bps OR $p_{H_0} \in [0.05, 0.10]$ | **WEAK** | Park strategy live; continue paper-trading; archive all live scans; re-run in 90 days. No public narrative until strengthened. |
| $\hat\mu \le 20$ bps OR $p_{H_0} > 0.10$ | **FAIL** | Pause live entries. Attribute current live P&L to the open-snap look-ahead bug. Close the hypothesis. |

The verdict is determined **only** by the main test. Sub-hypotheses
inform interpretation under PASS/WEAK but cannot rescue a FAIL.

The verdict criteria are frozen by the commit hash of this document.
Post-hoc modification of the rule after results are visible is an
integrity violation and must be disclosed if it occurs.

---

## 9. What a PASS does *not* establish

A PASS verdict under this test is a necessary but not sufficient
condition for production deployment. It does not establish:

- That the strategy works outside the 60-day window
- That it works in regimes not sampled (per-regime claims require
  per-regime statistical power, not supplied here)
- That the 1.5σ threshold is optimal (no tuning was done)
- That the 20-bps cost model reflects live execution
- That the profile's peer-cohort definitions generalise

Production deployment requires, at minimum: (i) compliance-grade
permutation null with ≥ 10⁴ resamples, (ii) parameter-fragility sweep,
(iii) multi-year sample, (iv) registered hypothesis per the Anka
hypothesis-registry protocol, (v) formal out-of-sample holdout. All of
these are deferred to a follow-up workstream conditional on this v0
passing.

---

## 10. What a FAIL tells us

A FAIL is informative. It rules out the simplest narrative for the
three live-trading profits and suggests the dominant explanation is
the open-snap look-ahead (§1.2, item 1). Under FAIL:

- The live strategy should be paused at the entry gate pending a
  re-design.
- The execution rule hardening (Workstream B: next-scan entry,
  deterministic exit ladder, intraday expected-return refresh)
  should still proceed — it does not depend on this thesis surviving,
  because it has value for *any* intraday strategy that might replace
  the LAG thesis.
- The open-snap bug is promoted to highest remediation priority.
- The NotebookLM-style public narrative is shelved indefinitely.

A FAIL is not a waste. It is the result we need to avoid publishing
fiction.

---

## 11. Pre-registration integrity

This document was committed to git at hash $H_{\text{pre}}$ (recorded in
commit metadata) **before** the replay results are read. Any amendment
after reading the results must:

1. Be made in a new commit, not by amending this one
2. State explicitly what result the amendment responds to
3. Be reviewed before being applied to the verdict

The purpose is to preserve a credible distinction between what was
predicted and what was observed. In a regime where the engineer, the
reviewer, and the trader are the same person, this discipline is the
only defence against the strongest cognitive bias in applied empirical
finance: hindsight p-hacking.

---

## References (informal)

- Gatev, E., Goetzmann, W., Rouwenhorst, K.G. (2006). *Pairs Trading:
  Performance of a Relative-Value Arbitrage Rule.* Review of Financial
  Studies 19(3).
- Do, B., Faff, R. (2010). *Does Simple Pairs Trading Still Work?*
  Financial Analysts Journal 66(4).
- Lo, A., MacKinlay, C. (1990). *When Are Contrarian Profits Due to
  Stock Market Overreaction?* Review of Financial Studies 3(2).
- Jegadeesh, N. (1990). *Evidence of Predictable Behavior of Security
  Returns.* Journal of Finance 45(3).
- Anka Research internal: Phase-A reverse-regime profile documentation
  (`docs/SYSTEM_OPERATIONS_MANUAL.md` Station 7, Station 11).

---

**Signed off:** pre-registration to be committed alongside this file on
`feat/phase-c-v5`. Results reporting will reference this commit hash.
