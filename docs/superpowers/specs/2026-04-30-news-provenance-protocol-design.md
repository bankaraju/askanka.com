# News provenance + data-primary trigger protocol — design (2026-04-30)

**Status:** PRE_REGISTERED design. Implementation pending.
**Author:** Bharat Ankaraju + Claude
**Predecessor:** `pipeline/news_scanner.py`, `pipeline/political_signals.py`, `pipeline/watchdog_content_audits.py:audit_news_feed_today`.

## Motivation

Two lived incidents on 2026-04-30 forced this protocol:

1. **Stale news bug** — `website_exporter.export_fno_news` overwrote morning headlines with `[]` at 16:00 EOD because the verdicts filter yielded zero rows; the terminal news API then fell through to yesterday's `news_verdicts.json`. We were displaying yesterday's news as today's. Fixed in commit `64a5f99` and a `audit_news_feed_today` watchdog audit was added.

2. **Trade-trigger fragility audit** — the 13 INDIA_SPREAD_PAIRS baskets fire on news-keyword classification with no record of *which headline* fired the trigger, *whether the URL is still resolvable*, *whether the headline body has changed since fetch*. The most-consistent paper earner ("PSU Commodity vs Banks") has been firing for weeks with this gap.

Per user directive 2026-04-30: *"we need to be sure if was that day news and have a proof of the news — it needs to be recorded else we can be hallucinating."*

## What this protocol does NOT do

- **Does not** ban news from the system. News remains a useful confirmation signal.
- **Does not** halt the 13 spread baskets — those keep paper-trading until the backtest verdict (Task #24) reaches them.
- **Does not** require a news classifier change — the existing `political_signals.py` keyword vocabulary stays.

## What this protocol DOES require

### 1. Trade trigger contract

Every promoted trading rule must declare:

```yaml
hypothesis_id: H-YYYY-MM-DD-NNN
data_primary_trigger:
  description: "≥2σ correlation break vs 30-day rolling sector mean"
  computable_from: ["price", "volume", "OI", "regime_tape"]
  required: true                           # data signal alone fires the trade
news_confirmation:
  description: "headline classified as one of {oil_up, hormuz, escalation}"
  required: false                          # news is reassurance only
  contradicts:                             # if these classifications fire, BLOCK trade
    - de_escalation
    - diplomacy
```

The data signal is required. News is optional and can only **confirm** or **block** — never trigger.

### 2. Mandatory news provenance fields

When a news headline is cited in any trade row (even as confirmation), the following must be persisted at the moment of trade open, immutable, and re-verifiable:

| Field | Description |
|---|---|
| `url` | The actual source link (resolvable HTTP) |
| `source` | NewsAPI / Google News / RSS feed name / etc. |
| `fetched_at` | UTC timestamp the headline entered the system |
| `published_at` | The headline's claimed publication time |
| `classifier_score` | Output of `political_signals.py` for this headline |
| `matched_trigger_keyword` | The keyword that fired (e.g., `escalation`) |
| `headline_text_sha256` | sha256(headline_title + first 500 chars of body) |
| `verified_today` | `published_at` is within 24h of trade open |

Storage: append to `pipeline/data/research/news_provenance/<YYYY-MM-DD>/<trade_id>.json`. Atomic write, no overwrites.

### 3. Anti-stale guard

A headline whose `published_at` is more than 24 hours before the trade open MUST NOT count as confirmation. The basket fires on the data signal alone or not at all. Implementation: `verified_today=False` blocks confirmation.

### 4. Anti-contradiction guard

When the data-primary trigger fires LONG and the news classifier flags an opposing-direction event (e.g., data says LONG ONGC, news says `de_escalation`), the trade is BLOCKED, not opened. Implementation: each hypothesis declares `news_confirmation.contradicts: [...]`; if any contradiction keyword has fired in the last 24h with `verified_today=True`, the trade does not open.

### 5. Retroactive auditability

At trade close (and on any post-mortem), the persisted `url` + `headline_text_sha256` must still resolve. If the URL 404s or the body has changed beyond a tolerance:
- Trade flagged "EVIDENCE_VANISHED" in track record
- Excluded from any backtest aggregation
- Logged to `pipeline/logs/news_evidence_vanished.log`
- Triggers an `EVIDENCE_VANISHED` watchdog alert at next intraday cycle

### 6. The 13 INDIA_SPREAD_PAIRS — interim handling

Until Task #24 backtest verdict reaches them:
- Paper trades continue firing
- BUT every news headline that fires a trigger must now be persisted with the 8 provenance fields above (retrofit `news_scanner.py` + `political_signals.py`)
- Existing trade rows without provenance are flagged "PROVENANCE_RETROFIT_PENDING" — not retroactively certified
- New rows after this protocol's implementation date are properly recorded

### 7. Watchdog extensions

`pipeline/watchdog_content_audits.py:audit_news_feed_today` already catches stale `fno_news.json`. Add three more audits:

- `audit_news_provenance_recorded` — for every trade row OPENED today, verify it has a corresponding `news_provenance/<date>/<trade_id>.json` file (or `news_required=False` flag). Otherwise: `NEWS_PROVENANCE_MISSING` alert.
- `audit_news_url_still_resolves` — sample 10 random news-cited trades from the past week; verify URLs return 200 OK. Otherwise: `NEWS_EVIDENCE_VANISHED` alert.
- `audit_news_hash_unchanged` — for the same sample, fetch the live page and re-compute `headline_text_sha256`; compare to recorded hash. Otherwise: `NEWS_BODY_DRIFT` alert.

## Implementation phases

### Phase 1 — Persist provenance (≤ 1 day build)
- Extend `political_signals.py` to return all 8 fields per matched headline
- Extend `news_scanner.py` to write `news_provenance/<date>/<trade_id>.json` atomically
- Extend `run_signals._run_once_inner` and `arcbe_signal_generator.py` to emit `news_provenance_path` in the trade row

### Phase 2 — Anti-stale + anti-contradiction guards (≤ 1 day build)
- Hypothesis declarations carry `news_confirmation.required` + `news_confirmation.contradicts`
- `run_signals._run_once_inner` blocks open if `verified_today=False`
- `run_signals._run_once_inner` blocks open if any contradiction keyword has `verified_today=True`

### Phase 3 — Retroactive verification + watchdog (≤ 1 day build)
- Add 3 audits to `watchdog_content_audits.py`
- Add `news_evidence_vanished.log` rotation
- Add daily 22:00 IST scan that randomly samples 10 trades from the last week and re-verifies URL + hash

### Phase 4 — Trade trigger contract enforcement (≤ 1 day build)
- Hypothesis registry entries declare `data_primary_trigger` + `news_confirmation`
- New strategy files refuse to register without these fields
- Pre-commit hook (`pipeline/scripts/hooks/strategy_patterns.txt`) extended to enforce this

## Decision tree at completion

| State | Outcome |
|---|---|
| All 4 phases shipped | News-trigger anti-pattern eliminated. The 13 baskets become candidates for proper registration if Task #24 also passes them. |
| Only phases 1-2 shipped | Provenance recorded going forward; retroactive verification missing. Half-fix. |
| Phase 1 only | Bare minimum — at least we know which headlines fired which trades. Not enough. |

## Honest expectation

Some news sources (especially Google News aggregator links) have URLs that drift quickly — they redirect through trackers and the original article URL changes. The `EVIDENCE_VANISHED` rate may be 5-15% per week even for legitimate news. Tolerance for this should be:
- Per-trade: tagged but not auto-rejected
- Per-aggregate: if >25% of trades in a backtest have EVIDENCE_VANISHED, the backtest is invalidated
