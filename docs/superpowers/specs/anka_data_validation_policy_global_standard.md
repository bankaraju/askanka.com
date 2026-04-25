# Data Validation and Data Governance Policy Standard

**Document status:** Approved policy template
**Policy type:** Quantitative data governance, lineage, validation, cleanliness, monitoring, and acceptance for use in backtesting and live decision systems
**Intended audience:** Research, trading, risk, validation, audit, allocators, and external due-diligence reviewers
**Applicability:** Any dataset, feed, or external source whose values can influence research conclusions, model outputs, signal generation, capital allocation, performance reporting, or governance decisions

This standard is the data-side companion to `anka_backtesting_policy_global_standard.md`. The two policies are intended to be read together: that policy governs models; this policy governs the inputs those models depend on. A model cannot be deployable under the model policy unless the data feeding it is acceptable under this policy.

## 1. Purpose

This policy establishes the minimum governance, lineage, validation, cleanliness, contamination control, monitoring, and acceptance standards for every dataset used to inform or automate research, backtesting, signal generation, trade execution, allocation, risk control, performance reporting, or model approval decisions.

The objective of this policy is to ensure that no dataset is used in research or decision-making unless its origin, authenticity, freshness, completeness, cleanliness, point-in-time correctness, contamination profile, and operational reliability are documented, challenged, monitored, and approved.

This policy is designed to be suitable for institutional use and external scrutiny. It is intended to align with internationally recognized data risk management principles, including clear ownership, independent validation, documented limitations, disciplined change control, reproducibility, and ongoing monitoring.

## 2. Scope

This policy applies to every dataset, feed, vendor source, derived dataset, or computed artifact whose values can influence:

- Research conclusions
- Hypothesis evaluation
- Backtest outputs
- Signal generation
- Trade direction, sizing, or timing
- Risk classification
- Performance reporting
- Validation or approval decisions on any model
- Disclosure of metrics to internal or external parties

In-scope artifacts include, but are not limited to:

- Market price feeds (intraday and daily)
- Corporate-action feeds (dividends, splits, bonus, mergers, demergers, symbol changes)
- Earnings calendars and corporate disclosures
- Fundamentals data (earnings, balance sheets, cash flows, ratios)
- Options chains, OI, and PCR feeds
- News and event feeds
- Macro and reference series (FX, rates, indices, VIX, regimes)
- Alternative or third-party data
- Internally derived datasets (regimes, scores, rankings, classifications)
- Universe and membership datasets (F&O eligibility, sector classifications)
- Trust scores, attractiveness scores, and any aggregate produced from the above
- Audit logs, run manifests, and reproducibility artefacts that are themselves used as evidence

A dataset that is used to validate other datasets is itself in-scope.

## 3. Governance principles

### 3.1 Authenticity over speed

A dataset shall not be used in research or decision-making unless its authenticity has been verified end-to-end (vendor identity, transport, payload schema, content sanity).

Convenience, urgency, or familiarity shall not substitute for authenticity verification.

### 3.2 Cleanliness before backtest

Cleanliness checks (Section 9) and contamination diagnostics (Section 14) shall complete and pass before any backtest, validation, or decision system consumes the dataset.

A backtest run on uncleaned data is research evidence of nothing and shall not be cited.

### 3.3 Point-in-time integrity

Every dataset used in historical evaluation shall reflect the information actually available at the decision time being simulated.

Forward-looking values, future-dated entries, restated values, and post-event corrections shall not be silently used as if they were observable at the simulated decision moment.

### 3.4 No silent repair

Any modification to raw data — fill, splice, exclusion, mapping, override, or imputation — shall be logged with reason, method, and approver.

Silent repair, undocumented adjustment, or unannounced backfill is prohibited.

### 3.5 Lineage discipline

The full provenance chain of any dataset used in a formal evaluation shall be reproducible from source through every transformation to the bytes consumed by the model.

If lineage cannot be reconstructed, the dataset cannot be cited as evidence.

### 3.6 No retroactive redefinition

Cleanliness thresholds, schema contracts, and acceptance criteria shall be defined before evaluation and shall not be loosened to make a problematic dataset pass.

### 3.7 Effective challenge

Data acceptance requires credible challenge. Approval shall not be a rubber-stamp by the dataset's owner or proposer.

### 3.8 Commercial urgency

Commercial urgency, market-timing pressure, or research enthusiasm shall not override data control requirements. "We need this dataset by Monday" is not a reason to skip Sections 9-15.

### 3.9 Recursive application

A dataset that audits or validates other datasets is itself a dataset and must satisfy this policy.

## 4. Roles and accountability

### 4.1 First line: data owner

The data owner is responsible for:

- Source selection and vendor relationship
- Authentication, secrets management, and access policy
- Schema documentation and contract definition
- Ingestion correctness
- Cleanliness monitoring design
- Limitation disclosure
- Change requests
- Ongoing operational ownership

### 4.2 Second line: independent data validator

The data validator is responsible for:

- Independent review and effective challenge of data acceptance evidence
- Authenticity, lineage, and contamination tests
- Limitation logging
- Acceptance recommendation
- Periodic reacceptance
- Review of monitoring adequacy

The data validator shall not be the data owner of the dataset under review.

### 4.3 Third line: oversight or audit

Oversight or audit is responsible for assessing whether this policy is being followed in practice.

### 4.4 Approval authority

A designated approving authority shall accept, reject, or conditionally approve datasets based on documented evidence.

No dataset may be accepted into research-approved or deployment-approved status solely by its proposer.

## 5. Data inventory and tiering

All in-scope datasets shall be maintained in a central data inventory.

Each inventory record shall include at least:

- Dataset ID
- Dataset name
- Vendor or origin
- Owner
- Validator
- Intended use
- Acceptance status
- Risk tier
- Schema version
- Refresh cadence
- Authentication scheme reference
- Lineage chain summary
- Acceptance date
- Last validation date
- Next review date
- Linked hypothesis IDs where applicable

### 5.1 Risk tiers

Each dataset shall be assigned a risk tier.

- **Tier D1:** Capital-affecting datasets. Inputs to live signal generation, position sizing, execution decisions, or deployment-gating evaluations.
- **Tier D2:** Decision-supporting datasets. Inputs to research-class backtests and validations whose conclusions can inform Tier 1 model decisions.
- **Tier D3:** Research-only or low-impact datasets used for exploration, dashboarding, or context.

Validation depth, monitoring frequency, change control, and acceptance requirements shall scale with risk tier. A Tier D1 dataset cannot be downgraded to skip controls.

### 5.2 Use-binding

Acceptance is granted for a specific intended use and tier. Reuse of a dataset in a higher-tier or materially different use case requires reacceptance, not silent re-purposing.

## 6. Source registration and onboarding

Before any dataset is used for research, validation, or decision-making, it shall be registered.

The registry entry shall include at minimum:

- Source URL or vendor
- Authentication scheme and secret reference (never the secret itself)
- Documented endpoints and parameters
- Plan tier and rate-limit envelope
- Schema fingerprint
- Cleanliness baseline measured at onboarding
- Known limitations
- Cost model where applicable

### 6.1 Authentication discipline

Secrets, API keys, and tokens shall be stored only in the project secret store (e.g., `pipeline/.env`) and referenced by name in code, configuration, and specification documents.

Hardcoding a literal secret in any committed file is prohibited.

Specifications shall reference secrets by environment-variable name (e.g., `INDIANAPI_KEY`), not by literal value.

### 6.2 Live verification at onboarding

Onboarding shall include a documented live probe demonstrating:

- The expected endpoint returns 2xx with the expected schema
- Sample records pass schema and sanity checks
- Plan tier, rate limit, and quota reported by the vendor match the registered envelope
- Authentication failure modes (expired key, revoked key, exceeded quota) produce clear, recoverable error signals

The probe and its outputs shall be archived in `docs/superpowers/data-onboarding/<dataset_id>/<date>.md`.

## 7. Lineage and provenance

### 7.1 End-to-end traceability

For every datum consumed in a formal evaluation, it shall be possible to reconstruct:

- The originating source request
- The transport timestamp
- Every transformation applied (parse, normalise, classify, join, aggregate)
- The artefact written to disk and its content hash
- The reader and the consuming model run

### 7.2 Transformation logs

Each transformation step shall be either deterministic and reproducible from registered code, or logged in detail sufficient to reproduce the same transformation.

### 7.3 Vendor-side reproducibility

Where the vendor itself is non-deterministic (live feeds, mutable historical archives, vendor-side restatements), this fact shall be flagged in the inventory record and a snapshot strategy shall be defined.

A "live re-fetch" is not a reproducible read; only a frozen snapshot is.

## 8. Schema and contract validation

### 8.1 Schema contract

Every accepted dataset shall have a written schema contract specifying field names, types, units, allowed value ranges or enumerations, and required-vs-optional status.

### 8.2 Contract enforcement

Ingestion shall validate every record against the schema contract and reject or quarantine non-conforming records.

A silent contract violation is a control failure.

### 8.3 Contract evolution

Schema changes shall be versioned, dated, and recorded in the inventory record. Downstream consumers shall be notified before a breaking change ships.

## 9. Cleanliness gates

### 9.1 Mandatory cleanliness audit

Before a dataset is consumed by a backtest, hypothesis evaluation, or live decision system, a cleanliness audit shall be produced. The audit shall include, at minimum:

- Missing-record counts
- Duplicate-key counts
- Stale-observation counts (unchanged value beyond expected stationarity)
- Zero-or-negative counts where the field cannot legitimately take such values
- Zero-volume counts where trading or activity should have occurred
- Out-of-range counts versus the schema contract
- Null counts on required fields
- Cross-record inconsistency counts (e.g., open > high, close < low)

### 9.2 Acceptance thresholds

Each dataset and tier shall have explicit cleanliness thresholds defined at registration.

For Tier D1 datasets the default thresholds, unless the registration record establishes otherwise, are:

- > 1.0% records impaired: tag DATA-IMPAIRED (research-only; no deployment use without waiver)
- > 3.0% records impaired: auto-fail; cannot be used for any deployment-class evaluation under any waiver

### 9.3 Quarantine

Records failing cleanliness gates shall be quarantined separately from the accepted dataset. Quarantined records shall not silently re-enter the accepted dataset.

### 9.4 Repair log

Any repair, fill, splice, mapping, exclusion, manual override, or imputation shall be logged in `docs/superpowers/data-audits/<dataset_id>/<date>.md` with reason, method, and approver. Silent repair is prohibited.

## 10. Corporate action and adjustment integrity

### 10.1 Adjustment-mode declaration

For every dataset that depends on price-affecting events (splits, bonus, dividends, mergers), the adjustment mode shall be declared in the schema contract: `adjusted`, `unadjusted`, or `mixed-with-explicit-handling`.

### 10.2 Consistency

Within a single research artefact, model, or evaluation, only one adjustment mode shall be in use across entry, exit, labels, stops, targets, and reporting.

Mixed adjustment modes without a formal design document are prohibited.

### 10.3 Corporate-action ledger

A canonical corporate-action ledger shall be maintained, sourced from at least one authoritative provider, and reconciled against price-action discontinuities.

Unexplained price discontinuities exceeding registered tolerances shall raise an issue and block downstream use until resolved.

## 11. Point-in-time correctness

### 11.1 As-of-date discipline

Every historical extraction shall include the as-of timestamp it was generated. Re-extracting a historical query later may legitimately yield different values; this difference shall be tracked, not hidden.

### 11.2 Restatement handling

If the vendor restates historical values, both the original and the restated value shall be retained with their respective as-of timestamps. Backtests that simulate decisions made at time T shall use only values knowable at T.

### 11.3 Future-dated entries

Datasets that legitimately contain future-dated entries (earnings calendars, scheduled corporate actions, expiry calendars) shall flag those entries as `as_of` versus `event_date` and shall require a forward-only filter at consumption.

A backtest that selects events with `event_date > as_of_extraction` is leaking the future.

## 12. Survivorship and universe integrity

### 12.1 Point-in-time universe

For datasets keyed by a universe (e.g., F&O eligibility, sector membership), a point-in-time universe history shall be maintained with sufficient depth for the longest backtest window.

### 12.2 Mandatory disclosures

Each dataset whose universe membership matters shall, on consumption, be able to disclose:

- The universe size at any historical date
- Tickers added and removed between two dates
- Tickers fully delisted within the window

A dataset that silently uses today's universe in place of the historical universe shall be tagged SURVIVORSHIP-UNCORRECTED and is not acceptable for deployment-class evaluations.

## 13. Cross-source reconciliation

### 13.1 Independent corroboration

For any dataset whose values are decision-critical, at least one independent source shall be available for spot-check reconciliation.

Where no independent source exists, this shall be flagged as a single-source dependency with explicit risk acknowledgment.

### 13.2 Material divergence

Divergence between sources beyond registered tolerances shall raise an issue and block use until resolved.

Silent preference for the more convenient source is prohibited.

## 14. Noise and contamination diagnostics

This section is the data-side counterpart to the model policy's null-model and benchmark requirements. It specifically addresses datasets where the apparent signal can be confounded by event noise unrelated to the hypothesis.

### 14.1 Contamination map

For every dataset registered in support of an event-based hypothesis, the proposer shall produce a contamination map enumerating each known contaminating channel and its expected magnitude. Examples include:

- Result-day gap moves contaminating pre-event windows
- Concurrent corporate actions mixed with the event of interest
- Macro shocks affecting all events in a window simultaneously
- Sector-news contamination of stock-specific signals
- Intraday news contamination of options-based features (OI, PCR, IV)
- Quarter-end clustering effects
- Earnings-season cohort effects

### 14.2 Channel-by-channel mitigation

Each contaminating channel listed in §14.1 shall have a documented mitigation: exclusion, control variable, conditioning, or explicit acceptance with quantified residual risk.

### 14.3 Residual contamination test

After mitigations, the residual contamination shall be measurable. Where feasible, the dataset shall include a placebo test: events shifted to dates known not to carry the hypothesised signal should produce no edge after the same pipeline runs.

A pipeline whose placebo events also generate signal is a contaminated pipeline; the signal claim cannot be attributed to the hypothesised channel.

### 14.4 OI / PCR / options-derived data

Options-derived datasets are subject to additional contamination discipline because intraday news materially perturbs OI and PCR independent of the underlying hypothesis. Specifically:

- Every OI/PCR feature used in a backtest shall be regressed against contemporaneous news-impact scores; the residual is the feature available to the model.
- Lookback windows for OI/PCR features shall declare a news-event purge rule (e.g., exclude events within ±N hours of a high-impact news item).
- The user-emphasised "last 3 days into earnings" pattern is acknowledged as a high-contamination window; any feature drawn from this window shall be tagged `high_contamination` and require placebo evidence before use.

## 15. Monitoring, freshness, and drift

### 15.1 Freshness contract

Every accepted dataset shall declare a freshness contract: maximum acceptable age between the latest accepted record and the present time, by tier.

### 15.2 Watchdog enforcement

A watchdog process shall verify freshness contracts at the cadence required by the dataset tier. Stale datasets shall raise alerts at their declared severity.

### 15.3 Schema-drift monitoring

The watchdog shall additionally monitor schema fingerprints and raise an alert on any unannounced contract change.

### 15.4 Cleanliness drift

Cleanliness metrics (Section 9) shall be tracked over time. A statistically meaningful deterioration versus the onboarding baseline shall trigger reacceptance review.

## 16. Reproducibility

Every formal evaluation that consumes a dataset shall record, at minimum:

- Dataset ID
- Schema version
- Snapshot or content hash actually consumed
- As-of timestamp of the consumption
- Repair-log references for any cleanliness intervention applied
- Any waivers in force at the time of consumption

A reproducibility failure on a Tier D1 or D2 dataset is a governance failure.

## 17. Acceptance ladder

A dataset shall progress through controlled acceptance stages:

- **Proposed** — Inventory record created; live verification probe scheduled.
- **Vetted** — Live probe passed (Section 6.2); schema contract approved (Section 8); cleanliness baseline recorded (Section 9).
- **Approved-for-research** — Independent validator has accepted the dataset for research-class use; lineage and contamination map are complete.
- **Approved-for-deployment** — Dataset has demonstrated stable freshness, cleanliness, and lineage over a defined observation window appropriate to its tier; reconciliation against an independent source has been performed where required.

Progression and demotion criteria shall be mechanical and documented.

A dataset that fails the freshness, cleanliness, schema-drift, or contamination triggers shall be demoted, paused, or quarantined as the inventory record specifies.

## 18. Independent validation

Independent validation of a dataset shall assess at minimum:

- Authenticity and source identification
- Lineage completeness
- Schema contract correctness
- Cleanliness baseline and ongoing monitoring adequacy
- Point-in-time correctness
- Contamination map adequacy
- Reproducibility evidence
- Stated limitations

Validation shall conclude with one of:

- Approved
- Approved with limitations
- Remediation required
- Rejected

Only approved or approved-with-limitations datasets may proceed into authorized use at the corresponding tier.

## 19. Change management

### 19.1 Versioning

Every dataset shall have explicit schema and ingestion versions.

### 19.2 Material changes

The following are material unless formally classified otherwise:

- Source change or vendor swap
- Endpoint or API tier change that affects payload
- Schema field addition, removal, type change, or unit change
- Adjustment mode change
- Cleanliness threshold change
- Contamination map change
- Universe construction change
- Authentication or access scheme change

Material changes require reacceptance before continued use at the same tier.

### 19.3 Non-material changes

Non-material changes may be released under standard software controls but shall still be documented.

### 19.4 Retirement

Retired datasets shall remain in inventory with retirement date, reason, and terminal status. Retired dataset names shall not be silently recycled for new sources.

## 20. Issue management

All findings, breaches, waivers, reproducibility failures, contamination events, and exceptions shall be logged in a formal issue register.

Each issue record shall include at minimum:

- Issue ID
- Dataset ID
- Severity
- Date opened
- Owner
- Remediation plan
- Target date
- Closure date
- Evidence of fix

Open severe issues shall block promotion of dependent models and may trigger demotion or suspension of dependent strategies.

## 21. Interaction with the model policy

This policy operates upstream of `anka_backtesting_policy_global_standard.md`. Specifically:

- A model cannot enter §17-style "Approved" status under the model policy if any dataset it consumes is below "Approved-for-deployment" status under this policy at the corresponding tier.
- A model whose data dependency is downgraded under §17 of this policy shall be reviewed under the model policy and may be demoted accordingly.
- A model's reproducibility manifest shall list each dataset consumed and the dataset's acceptance status at consumption time.

A backtest that runs on an unaccepted or quarantined dataset is research evidence of nothing and shall not be cited as a basis for any model decision.

## 22. Waivers and exceptions

Any deviation from this policy shall require a dated waiver approved by the designated approving authority before the deviation takes effect.

Waivers shall include scope, reason, risk assessment, compensating controls, expiry date, and named approver.

Waivers shall not be retroactive.

The integrity principles in Section 3 shall not be waivable.

## 23. Oversight reporting

At a defined periodic cadence, governance oversight shall review at minimum:

- Tier D1 dataset inventory
- Newly accepted datasets
- Datasets under watch
- Open high-severity data issues
- Freshness and cleanliness drift events
- Active waivers
- Material data changes
- Retired datasets
- Acceptance status changes

Minutes or equivalent evidence of oversight shall be retained.

## 24. Definitions

### 24.1 Dataset

Any structured collection of values used as input to research, validation, decision-making, or reporting, regardless of source, format, or refresh cadence.

### 24.2 Data owner

The individual or function accountable for a dataset's acquisition, ingestion, ongoing operation, and limitation disclosure.

### 24.3 Independent data validator

An individual or function performing review and effective challenge of data acceptance evidence, independent of the data owner.

### 24.4 Snapshot

An immutable record of dataset content at a specific time, sufficient to reproduce any consumption that referenced it.

### 24.5 Lineage

The full reproducible chain from source request through every transformation to the bytes consumed by a model.

### 24.6 Cleanliness

The degree to which a dataset's values conform to its schema contract, lack improper nulls, lack duplicates, lack staleness, and pass cross-record consistency checks.

### 24.7 Contamination

Any unintended source of variation in a dataset that can confound a hypothesised signal, including event-noise channels, concurrent confounders, and pipeline artefacts.

### 24.8 Point-in-time correctness

The property that a historical extraction reflects only what was knowable at the simulated decision time.

### 24.9 Survivorship correction

The property that historical universe membership reflects what was actually tradeable at the simulated decision time, not today's universe.

### 24.10 Acceptance

The state in which a dataset has been registered, vetted, validated, and approved for use at a specified tier and intended use.

## 25. Minimum implementation requirements

To operationalize this policy, the organization shall maintain at minimum:

- A data inventory with tiering
- A source registry
- A data-validation record for each accepted dataset
- A reproducible ingestion manifest per Tier D1 and D2 dataset
- A contamination map per dataset registered in support of an event-based hypothesis
- A repair log
- A waiver register
- An issue register
- Version-controlled policy and dataset documentation
- A periodic oversight review process

## 26. Final rule

If a dataset cannot be authenticated, lineage-traced, cleanliness-audited, contamination-mapped, monitored, and governed, it shall not be trusted for backtesting, validation, or live decision use regardless of how attractive the apparent signal it produces.

A backtest that runs on data that has not satisfied this policy is not market-standard evidence and shall not be presented as such.
