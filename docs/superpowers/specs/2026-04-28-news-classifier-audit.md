# News Classifier Audit — 2026-04-28

**Backlog:** #37 (news_backtest impact classification audit)
**Status:** Audit complete; fix proposed; not yet implemented.

---

## The symptom

The terminal `News` tab has been empty for the last several scheduled `AnkaEODNews` runs. The website news card has likewise been showing zero rows. Investigation found that `pipeline/data/news_verdicts.json` contains 300 rows for 2026-04-27, **all** classified `NO_IMPACT` → `NO_ACTION`. The downstream filter in `pipeline/website_exporter.py` (HIGH_IMPACT + MODERATE × ADD/CUT) drops every row, leaving an empty `data/fno_news.json`.

The terminal News tab now correctly explains this empty state with a reference to this audit (commit 69c23af, `pages/news.js`). But the underlying classifier is still mis-grading every event.

## The classifier

`pipeline/news_backtest.py:98-112` — `classify_verdict`:

```python
if   ret_1d > 3.0:                                            impact = HIGH_IMPACT
elif ret_1d > 1.5:                                            impact = MODERATE
elif avg_5d > 2.0 and hit_rate > 0.6:                         impact = HIGH_IMPACT
elif avg_5d > 1.0:                                            impact = MODERATE
else:                                                         impact = NO_IMPACT
```

For an event to be classified anything other than NO_IMPACT, **either** `ret_1d` (the actual T+1 close return at run-time) **or** `avg_5d` (average of past T+5 returns from precedent history) must be defined.

## The bug

`avg_5d` is computed by `lookup_historical_precedent` (lines 76-95) from `news_events_history.json`. The precedent filter requires:

```python
past_events = [e for e in history
               if symbol in e.get("matched_stocks", [])
               and category in e.get("categories", [])
               and e.get("outcome")]
```

The `outcome` field is the price-reaction dict (`ret_1d`, `ret_3d`, `ret_5d`).

**Audit finding (verified 2026-04-28):**

```
$ history = json.load(open("pipeline/data/news_events_history.json"))
  events:                  3689
  with outcome field:         0
```

Zero of the 3,689 historical events have an `outcome` field. The producer in `pipeline/news_intelligence.py:359-369` writes events to history but never populates `outcome`. There is no back-fill job that walks the history and writes `outcome` once T+5 has elapsed.

Result: `avg_5d` is always `None`, so the second and fourth branches of the classifier are dead code.

## Why `ret_1d` doesn't save us

`AnkaEODNews` runs at 16:20 IST on the same day the event is detected. `compute_forward_returns` (lines 55-73) requires `t0_loc + 1 < len(df)` to compute `ret_1d`. The next trading day's bar does not exist yet at 16:20. So `ret_1d` is also `None` for the same-day classification path.

Both inputs to the classifier are `None`, every event falls through to NO_IMPACT, every row is dropped by the downstream filter. The system has been logging "0 actionable verdicts" for weeks.

## Confirmation

A spot-check of `pipeline/data/news_verdicts.json` for 2026-04-27 shows:

```
HIGH_IMPACT: 0
MODERATE:    0
NO_IMPACT:   300
ADD: 0  |  CUT: 0
```

No row has `historical_avg_5d` or `precedent_count >= 2`.

## Proposed fix (not yet implemented)

Add a `backfill_outcomes()` pass to `news_backtest.run_backtest`. Before the verdict loop, walk `news_events_history.json` and for any event where:

1. `detected_at` is at least 5 calendar days old, **and**
2. `outcome` field is missing or empty,

compute `(ret_1d, ret_3d, ret_5d)` against the symbol's `fno_historical/<SYM>.csv` and write back. After the back-fill, the precedent lookup will find non-empty `outcome` rows and `avg_5d` will be computable, unblocking the classifier.

Secondary improvement: the next-day classifier path (`AnkaEODNews` at T+1, run against T-1's events) would also fire `ret_1d` correctly, since by then the next bar exists. Splitting the `EVENTS_TODAY` cursor into "today's freshly-detected events" + "yesterday's events that now have a `ret_1d`" gives a second path into MODERATE/HIGH_IMPACT.

These two changes together should produce 5-15 non-NO_IMPACT verdicts per day in normal market conditions, which is what the original spec assumed.

## Out of scope for this audit

- Threshold tuning (`3.0` / `1.5` / `2.0` / `1.0`) — leave as-is until the back-fill is producing real distributions.
- Hit-rate gate (currently `hit_rate > 0.6` only on the HIGH_IMPACT branch) — revisit after first 30 days of post-fix verdicts.
- `news_alerter.py` Telegram routing — orthogonal; depends on classifier output, not vice versa.

## Next step

User decision required. Options:

1. **Implement the back-fill + T+1 classifier in this branch** (~4-6 hours: data audit, two TDD steps, smoke run on 30-day window, watchdog inventory entry).
2. **Spec-only deliverable** — register a follow-up backlog ticket and revisit later when News-driven trading is closer on the roadmap.
3. **Drop news entirely** — the system already reads news in three other places (corp announcements via news_intelligence, news_alerter for Telegram, gap_predictor). The verdict layer may be redundant.

Recommendation: option 2 in this branch (just keep the audit + the explained empty state on the terminal). News-driven verdicts are not currently consumed by any live engine for trade decisions, only displayed. Time is better spent on the open governance and Phase C × FCS items.
