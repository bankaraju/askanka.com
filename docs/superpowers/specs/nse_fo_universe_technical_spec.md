# Technical Specification: NSE F&O Universe Research and Portfolio Optimization Engine

## Overview
This document specifies a research and production framework for an NSE F&O stock universe strategy that discovers per-stock technical strategies, estimates joint return dependence, and constructs a portfolio optimized for out-of-sample Sharpe ratio under liquidity, turnover, and risk constraints. The design targets a liquid Indian equity derivatives universe because the NSE F&O segment is explicitly curated around eligibility and liquidity criteria, and the listed universe expanded further in April 2026 with additional stocks entering the segment.[cite:19][cite:23]

The core idea is to separate the problem into three linked layers: alpha discovery at the single-stock level, dependence modeling at the cross-stock level, and portfolio construction at the basket level. This separation is necessary because high standalone Sharpe strategies can still fail at the portfolio level if correlation, tail dependence, turnover, or capacity are ignored.[cite:22][cite:24][cite:25]

## Objectives
The system objective is to maximize realized out-of-sample portfolio Sharpe ratio after transaction costs while preserving robustness across market regimes. The optimization must explicitly account for parameter uncertainty, trading costs, stock-level and portfolio-level turnover, and cross-sectional dependence among strategy returns.[cite:22][cite:25][cite:27]

Secondary objectives are to minimize drawdown, reduce sensitivity to overfitting, and maintain implementation feasibility in the NSE F&O segment through liquidity-aware constraints. The framework must therefore treat gross Sharpe as insufficient on its own and evaluate every candidate under a joint scorecard that includes net Sharpe, stability, turnover, and dependence-aware diversification quality.[cite:11][cite:19][cite:25]

## Scope
The tradable universe is the set of NSE-listed individual stocks eligible for the F&O segment at each reconstitution date, excluding index derivatives from the stock-selection layer. Public summaries indicate that the 2026 stock universe contains roughly 200 to 220 F&O-eligible names and that eight additional stocks were added from 1 April 2026, while the official NSE framework defines the continuing eligibility criteria for new and existing securities.[cite:18][cite:19][cite:23]

The specification supports cash-equity signal research, stock futures implementation, and synthetic long-short overlays where operationally permissible. The portfolio engine is agnostic to the execution wrapper but assumes that all selected instruments satisfy minimum tradability and cost-quality filters before inclusion.[cite:19][cite:28]

## Design Principles
The research loop must prefer robust, simple, and stable rules over fragile peak in-sample performers. Standard in-sample versus out-of-sample practice exists precisely because unconstrained search over large parameter spaces can produce misleadingly high backtest metrics that decay in live trading.[cite:11][cite:15]

The architecture must also be portfolio-first rather than stock-first at the final decision stage. Academic and practitioner evidence shows that constraints, shrinkage, and turnover-aware optimization often improve realized Sharpe relative to unconstrained tangency-style optimization, especially when estimation error is material.[cite:22][cite:25]

## System Architecture
The platform consists of six modules:

- Universe Manager: maintains the point-in-time NSE F&O stock list and eligibility metadata.[cite:19][cite:23]
- Data Layer: stores adjusted prices, corporate actions, futures chain data, volumes, open interest, borrow or funding proxies, and transaction cost estimates.
- Signal Research Engine: generates and evaluates technical-analysis strategy families per stock.
- Dependence Engine: estimates joint behavior of stock- or strategy-level returns using covariance, rank correlation, and copula-based models.[cite:21][cite:24][cite:27][cite:30]
- Portfolio Optimizer: selects stock-strategy combinations and target weights under risk, turnover, and exposure constraints.[cite:22][cite:25][cite:28]
- Validation and Monitoring Layer: runs walk-forward tests, regime analysis, drift detection, and production diagnostics.[cite:11][cite:15]

All modules must be reproducible, versioned, and driven by point-in-time datasets. No forward-looking constituent, price, or cost information may enter model training, validation, or optimization.

## Universe Definition
### Eligibility Rules
At each monthly or quarterly rebalance date, the universe manager must load the point-in-time list of NSE F&O-eligible stocks. The official exchange framework for equity-derivatives selection is the governing source for admission and continuation rules, while contemporaneous circulars or exchange notices determine additions or removals at each review date.[cite:19][cite:23]

### Investability Filters
Within the official F&O set, the production universe must apply additional internal filters:

- Minimum median daily notional traded value over the lookback window.
- Minimum median futures open interest for implementable derivatives exposure.
- Maximum average bid-ask spread threshold.
- Corporate-action and data-quality completeness checks.
- Exclusion of names under prolonged surveillance, ban periods, or recurring execution impairment.

These filters are implementation rules rather than exchange eligibility rules, and they exist to reduce slippage, capacity risk, and false diversification.

### Reconstitution Frequency
The official F&O list must be refreshed whenever exchange changes become effective, while internal liquidity filters should be recomputed monthly. Portfolio holdings may rebalance more frequently than universe reconstitution, but no stock may enter the optimizer unless it passed the point-in-time universe screen as of that rebalance date.[cite:19][cite:23]

## Data Specification
### Required Datasets
The system requires the following point-in-time datasets:

- Daily and intraday OHLCV for cash equities.
- Continuous and contract-level futures prices, volume, open interest, and lot sizes.
- Corporate actions, splits, bonuses, dividends, and symbol changes.
- Sector and industry tags.
- Market index data, factor returns, and risk-free rate proxies.
- Slippage and fee models calibrated to venue and instrument.
- Optional securities-lending or funding proxies for short exposure assumptions.

### Data Quality Controls
The data layer must enforce split-adjustment integrity, stale-price checks, duplicate timestamp removal, missing-bar repair policy, and point-in-time symbol mapping. Every backtest must record the exact data snapshot hash, feature-generation version, and cost-model version used to produce results.

## Research Layer
### Strategy Search Space
For each stock, the signal research engine must define a parameterized library of technical strategies, including but not limited to trend, momentum, breakout, mean reversion, volatility compression-expansion, relative strength, volume-price interaction, and regime-conditioned rules. Candidate features may include moving averages, RSI, stochastic oscillators, MACD, ADX, Bollinger measures, ATR, Donchian channels, volume z-scores, gap variables, and futures basis or open-interest signals where available.

Each strategy is represented as a fully specified decision program containing feature definitions, parameter values, signal rules, position logic, risk scaling, and trade filters. Search may be performed with grid search, Bayesian optimization, genetic programming, or an autoresearch loop that mutates strategy programs and accepts candidates only through a fixed evaluation protocol.[cite:6][cite:11]

### Per-Stock Candidate Basket
For each stock and walk-forward training window, the engine must retain a basket of the top 10 candidate strategies rather than only the single best strategy. The retention score should not be raw in-sample Sharpe alone; it should be a composite function that rewards net Sharpe, parameter stability, low turnover, low dependence on a single regime, and resilience under perturbation.

A recommended composite score is:

\[
Score_i = w_1 \cdot Sharpe^{net}_{IS} + w_2 \cdot Sharpe^{val} - w_3 \cdot Turnover - w_4 \cdot Fragility - w_5 \cdot Concentration + w_6 \cdot Stability
\]

where fragility measures sensitivity to neighboring parameter settings, concentration penalizes return dependence on a few dates or trades, and stability measures consistency across folds and regimes.

### Robustness Filters
A strategy may enter the candidate basket only if it passes all of the following:

- Positive net Sharpe in training and validation splits.[cite:11][cite:15]
- Minimum trade count and minimum holding diversity.
- Acceptable turnover after estimated costs.[cite:25]
- Limited performance collapse under parameter jitter.
- Limited dependence on single-event profits.
- No rule violations under realistic execution assumptions.

## Validation Framework
### Data Splits
The framework must use rolling or expanding walk-forward validation. A minimum structure is train, validation, and test, where model search occurs only on train, model ranking occurs on validation, and the final score is computed on untouched test data.[cite:11][cite:15]

Example configuration:

| Window | Length | Purpose |
|---|---:|---|
| Train | 5 years | Parameter and rule search |
| Validation | 1 year | Candidate ranking and pruning |
| Test | 1 year | Final out-of-sample evaluation |

The windows then roll forward by one quarter or one month depending on turnover tolerance and data density.

### Regime Tests
Every strategy and portfolio must be evaluated across multiple market regimes, including trending up, trending down, high-volatility, low-volatility, crisis, event-driven, and sideways conditions. This requirement exists because dependence structures and strategy efficacy are time-varying, and copula-GARCH style models are specifically motivated by non-linear dependence and changing volatility across stress periods.[cite:24][cite:27]

### Multiple-Testing Control
Because the engine evaluates a large strategy universe, the reported performance must include defenses against data mining. At minimum, the research report should track the number of tested variants, apply deflated or multiple-testing-aware Sharpe interpretation, and compare realized OOS outcomes with the expected decay from in-sample selection bias.[cite:11][cite:25]

## Dependence Modeling
### Rationale
Stock-level or strategy-level returns cannot be treated as independent. Research on copula-based portfolio construction emphasizes that asset returns exhibit non-linear dependence, asymmetry, and tail co-movements that standard covariance models can miss, especially during stress periods.[cite:21][cite:24][cite:27][cite:30]

### Return Objects
The dependence engine may model either of the following objects:

- Stock returns conditioned on the selected strategy for each stock.
- Pure strategy returns where each candidate strategy is treated as an asset.
- Hierarchical two-level dependence where stock dependence and strategy dependence are modeled separately.

The third option is preferred when multiple candidate strategies per stock are preserved up to the portfolio-selection stage.

### Joint Probability Models
The engine must estimate a joint distribution of next-period returns using one or more of the following:

- Shrunk covariance matrix for baseline optimization.
- Rank-correlation and distance-correlation matrices for robust dependence screening.
- Gaussian copula for baseline multivariate simulation.
- Student-
\(t\) copula for tail dependence and heavy-tail co-movements.[cite:21][cite:24][cite:27]
- Vine copulas for higher flexibility when pairwise structures differ materially.[cite:24][cite:30]
- GARCH or EWMA volatility models on marginals before copula fitting when conditional heteroskedasticity is material.[cite:24][cite:27]

### Joint Probability Outputs
For each rebalance date, the dependence engine must produce:

- Expected return vector \(\mu\).
- Conditional covariance matrix \(\Sigma\).
- Tail dependence matrix.
- Scenario cube of simulated joint returns.
- Probability of simultaneous loss events above specified thresholds.
- Pairwise and cluster-level stress co-movement diagnostics.

A core risk output is the joint event probability:

\[
P(R_1 < c_1, R_2 < c_2, \dots, R_n < c_n)
\]

for user-defined downside cutoffs \(c_i\). This quantity is used to penalize portfolios that look diversified under linear correlation but retain high crash co-occurrence risk.[cite:21][cite:24][cite:27]

## Portfolio Construction
### Optimization Universe
At each rebalance date, the optimizer receives a candidate set consisting of up to 10 strategies per stock for every eligible stock that passes internal filters. The optimizer may select zero or one strategy per stock by default, though an alternative design may allow multiple low-correlation strategies per stock with tighter aggregate exposure caps.

### Objective Function
The primary optimization target is maximum expected out-of-sample net Sharpe ratio of the portfolio under transaction costs and estimation risk. A dependence-aware formulation is:

\[
\max_w \; \frac{\mathbb{E}[R_p - TC(w)]}{\sqrt{Var(R_p)}} - \lambda_1 \cdot TO(w) - \lambda_2 \cdot JDP(w) - \lambda_3 \cdot DD(w)
\]

where \(TC(w)\) is expected transaction cost, \(TO(w)\) is turnover, \(JDP(w)\) is a joint-downside-probability penalty derived from the copula scenario engine, and \(DD(w)\) is a drawdown or CVaR proxy. This follows the literature direction that turnover constraints and ex-ante cost-aware shrinkage can materially improve realized net Sharpe.[cite:22][cite:25][cite:28]

### Constraint Set
The optimizer must support the following constraints:

- Long-only, long-short, or dollar-neutral mode.
- Maximum weight per stock.
- Maximum weight per sector.
- Maximum number of active positions.
- Maximum one-way turnover per rebalance.[cite:28]
- Gross and net exposure limits.
- Beta or factor exposure neutrality bands.
- Liquidity participation caps by average traded value or open interest.
- Minimum expected implementation capacity.
- At most one active strategy per stock unless multi-strategy mode is explicitly enabled.

### Optimization Methods
The baseline optimizer should use constrained quadratic or second-order cone formulations when covariance-based risk is sufficient. When the objective includes copula-scenario tail penalties or discrete strategy-selection decisions, the production stack should use mixed-integer optimization, stochastic programming, or a two-stage heuristic that first prunes candidates and then solves a continuous weight problem.

### Shrinkage and Estimation Error
Expected returns, covariance, and strategy Sharpe estimates must be shrunk before optimization. Research on Sharpe-optimal portfolios under estimation risk shows that naive sample-optimal tangency portfolios are unstable, and that shrinkage plus ex-ante transaction-cost integration can materially improve net out-of-sample Sharpe.[cite:25]

Recommended defaults:

- Shrink expected returns toward zero or sector means.
- Shrink covariance toward a factor or constant-correlation target.
- Shrink strategy-level Sharpe estimates toward universe medians.
- Penalize unstable candidates with high estimation error.

## Technical Indicators and Parameter Families
The following strategy families must be included in version 1 of the research engine:

| Family | Example Parameters | Typical Risk |
|---|---|---|
| Trend following | Fast and slow MA lengths, ADX threshold | Late entries, whipsaw |
| Breakout | Channel length, breakout buffer, hold time | False breakout |
| Mean reversion | RSI bands, z-score window, stop distance | Regime mismatch |
| Volatility expansion | ATR window, compression threshold | News-driven gaps |
| Relative strength | Cross-sectional rank window, hold time | Crowding |
| Volume-price | Volume z-score, breakout confirmation | Event dependence |
| Basis or OI-aware | Basis percentile, OI change threshold | Microstructure shifts |

Parameter ranges must be declared in machine-readable configuration. Search depth must be bounded to maintain a known multiple-testing budget per walk-forward cycle.

## Cost Model
The backtest and optimizer must incorporate explicit transaction cost estimates including brokerage, statutory levies, exchange fees, bid-ask spread, market impact, and roll costs for futures. Costs must be estimated ex ante and used during optimization rather than only deducted after weight selection, because the literature shows that cost-aware estimation and turnover control can materially improve realized Sharpe.[cite:25]

## Backtest Engine
### Execution Assumptions
The execution simulator must model realistic order timing, bar delay, slippage, contract rolls, lot-size rounding, and position carry rules. Backtests that use next-bar execution must ensure that all features are frozen before the assumed trade timestamp.

### Performance Metrics
The system must calculate and store at least the following metrics for every stock-strategy candidate and every portfolio:

- Gross and net CAGR.
- Gross and net Sharpe ratio.
- Sortino ratio.
- Maximum drawdown.
- Calmar ratio.
- Hit rate and payoff ratio.
- Turnover.
- Average holding period.
- Tail-loss metrics such as CVaR.
- Joint downside probability and tail dependence contribution.
- Regime-wise performance decomposition.

## Selection Logic
### Stock-Level Selection
For each stock, rank candidate strategies by validation composite score and retain the top 10. During portfolio formation, do not automatically select the top-ranked stock-level strategy in isolation; instead, pass the retained basket to the portfolio optimizer so that diversification and dependence structure influence final choice.

### Portfolio-Level Selection
The optimizer must choose the final set of stock-strategy pairs based on marginal contribution to portfolio-level expected net Sharpe and marginal reduction in joint downside concentration. A candidate with lower standalone Sharpe may still be selected if it improves portfolio diversification or reduces tail clustering.[cite:24][cite:27]

## Monitoring and Governance
The production system must include:

- Model registry with immutable versions.
- Rebalance audit logs.
- Parameter and constituent drift reports.
- Live versus backtest slippage comparison.
- OOS performance attribution by stock, sector, and strategy family.
- Kill-switch thresholds for drawdown, liquidity deterioration, and signal instability.

A governance report must record every research run, the number of candidate strategies tested, the chosen hyperparameters, and all validation outcomes. This is necessary for both scientific reproducibility and operational risk control.

## Deliverables
Version 1 of the system must produce the following outputs at each rebalance cycle:

- Point-in-time eligible F&O universe file.
- Per-stock top-10 candidate basket with validation statistics.
- Dependence report including covariance, copula choice, and joint-loss diagnostics.
- Optimized target portfolio with weights, expected cost, and turnover forecast.
- Walk-forward performance report with train, validation, and test metrics.
- Production order file and post-trade monitoring report.

## Recommended Default Configuration
| Component | Default |
|---|---|
| Universe refresh | Monthly, with exchange-event overrides |
| Training window | 5 years |
| Validation window | 1 year |
| Test window | 1 year |
| Rebalance frequency | Monthly or biweekly |
| Candidate basket per stock | 10 |
| Return dependence baseline | Shrunk covariance + Student-\(t\) copula overlay |
| Cost handling | Ex-ante in optimization |
| Objective | Net OOS Sharpe with turnover and joint-downside penalties |
| Selection mode | At most one strategy per stock |

## Implementation Notes
A practical implementation path is to start with daily data, monthly rebalancing, long-only or beta-controlled long-short construction, and a shrunk covariance optimizer augmented by a Student-\(t\) copula stress penalty. This setup is simpler than a full vine-copula stochastic optimizer but still aligns with the evidence that tail dependence and turnover-aware constraints materially affect realized portfolio outcomes.[cite:22][cite:24][cite:25][cite:27]

The second implementation phase can introduce intraday execution modeling, strategy-program mutation, hierarchical dependence models, and mixed-integer portfolio selection over the retained stock-strategy baskets. That phase is the natural place for an autoresearch loop to propose, evaluate, and retire strategy families under a fixed experimental budget.[cite:6][cite:11]

## Acceptance Criteria
The system is acceptable for production research use only if it satisfies all of the following:

- Uses point-in-time NSE F&O constituents and internal liquidity filters.[cite:19][cite:23]
- Demonstrates positive net OOS Sharpe after costs over multiple walk-forward windows.[cite:11][cite:15][cite:25]
- Shows no catastrophic degradation in crisis or high-volatility regimes.[cite:24][cite:27]
- Maintains turnover within predefined operational limits.[cite:22][cite:25][cite:28]
- Produces materially lower joint downside concentration than a naive top-Sharpe-per-stock assembly.[cite:21][cite:24][cite:27]
- Generates full audit artifacts for reproducibility and governance.
