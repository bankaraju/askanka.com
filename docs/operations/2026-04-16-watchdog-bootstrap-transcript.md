# Watchdog Bootstrap Transcript — 2026-04-16

**Spec:** `docs/superpowers/specs/2026-04-16-data-freshness-watchdog-design.md`
**Plan:** `docs/superpowers/plans/2026-04-16-data-freshness-watchdog.md`
**Branch:** `feat/data-freshness-watchdog`

## Bootstrap inventory

### Bootstrap output
```
Wrote C:\Users\Claude_Anka\askanka.com\pipeline\config\anka_inventory.json
  69 tasks total
  7 classified
  62 defaulted to info/daily (needs human review)
```

### Inventory size
tasks: 69

### Classification notes
- 7 of 8 `KNOWN_TASKS` entries matched live scheduler names.
- 1 `KNOWN_TASKS` entry did NOT match: `AnkaKiteRefresh` — the live task is actually named `AnkaRefreshKite`. Flagged for human review; left as-is so inventory accurately reflects live scheduler state.
- 62 tasks defaulted to `tier=info / cadence_class=daily / UNCLASSIFIED` pending human review.

## Unit test suite

<populated by Task 14>

## Dry-run smoke test

<populated by Task 14>

### Dry-run smoke test (T11)

```
🚨 Anka Watchdog — 2026-04-16 15:35 IST
Gate run • 70 issues

CRITICAL (1):
  • AnkaReverseRegimeProfile — output missing
    pipeline/tests/fixtures/does_not_exist_on_purpose.json  file does not exist

WARN (0):

DRIFT (69):
  • AnkaCorrelationBreaks — orphan task
    registered in scheduler but not in inventory
  • AnkaDailyArticles — orphan task
    registered in scheduler but not in inventory
  • AnkaDailyDump — orphan task
    registered in scheduler but not in inventory
  • AnkaEODNews — orphan task
    registered in scheduler but not in inventory
  • AnkaEODReview — orphan task
    registered in scheduler but not in inventory
  • AnkaEODTrackRecord — orphan task
    registered in scheduler but not in inventory
  • AnkaGapPredictor — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday0930 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday0945 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1000 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1015 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1030 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1045 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1100 — orphan task
    registered in scheduler but not in inventory
  • AnkaIntraday1115 — orphan task
    registered in scheduler but not in inventory
```

### Full watchdog test suite (T11)

```
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_persistent_issue_renders_compact_reminder PASSED [ 90%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_escalation_at_count_6 PASSED [ 91%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_escalation_refires_at_count_12 PASSED [ 92%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_resolved_tail_shows_recovered_keys PASSED [ 94%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_info_tier_not_rendered PASSED [ 95%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_happy_path_calls_send_alert PASSED [ 97%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_telegram_failure_writes_fallback_log PASSED [ 98%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_dry_run_skips_telegram PASSED [100%]

============================= 71 passed in 0.48s ==============================
```

## Scheduler registration

<populated by Task 15>

## Shadow-mode first run

<populated by Task 16>

## Canary drift acceptance test (spec §Acceptance #7)

<populated by Task 17>

### Fix: AnkaRefreshKite name drift

Bootstrap initially used `AnkaKiteRefresh` but live scheduler has `AnkaRefreshKite`. Renamed in KNOWN_TASKS; rerun. Classification count: 7 → 8.

### Code-review follow-up fixes

- Merge logic now upgrades UNCLASSIFIED rows when KNOWN_TASKS gains a matching entry (rows are only preserved when `notes` does not contain "UNCLASSIFIED").
- Duplicate `data/track_record.json` ownership resolved: **AnkaEODTrackRecord is the authoritative writer**. Evidence:
  - `pipeline/scripts/eod_review.bat` (AnkaEODReview) runs `run_signals.py --eod` which only prints the EOD dashboard and sends to Telegram (`run_signals.py:620 Running EOD review...`, `:635 print(eod_text)`, `:639 send_message(eod_text)`) — no file writes to `data/track_record.json`.
  - `pipeline/scripts/eod_track_record.bat` (AnkaEODTrackRecord) runs `run_eod_report.py` then `website_exporter.py`. The track_record JSON is written at `website_exporter.py:430 ("track_record.json", track)` → `:433 path.write_text(json.dumps(...))`.
  - Fix: AnkaEODReview `outputs` set to `[]` with clarifying note; AnkaEODTrackRecord keeps `data/track_record.json` as its sole output.
- Minor: `from datetime import date` moved to module top (line 13); `load_existing_inventory` now prints a friendly message and exits 1 on malformed JSON.

### Verification
- Fix 1 simulated: added a fake `AnkaDailyArticles` entry to KNOWN_TASKS, re-ran bootstrap → classified jumped 8→9, inventory row was upgraded from UNCLASSIFIED default to the new classification. Fake entry reverted before commit.
- Fix 2: after removing stale AnkaEODReview/AnkaEODTrackRecord rows and re-running, `grep data/track_record.json` against `outputs` lists in the inventory returns exactly one owner (AnkaEODTrackRecord).
- Fix 3: `grep -n "from datetime import date" pipeline/bootstrap_watchdog_inventory.py` → line 13.
- Fix 4: writing a deliberately malformed JSON to `pipeline/config/anka_inventory.json` and re-running prints "existing inventory at ... is malformed" and exits 1 (file restored from backup afterwards).

### Final unit-suite run (T14, pre-registration)

Note: The plan listed `pipeline/tests/test_bootstrap_watchdog_inventory.py` in the sign-off suite, but that test file does not exist in the repo (never authored in earlier tasks). Running the five watchdog test files that do exist — all pass.

```
pipeline/tests/test_watchdog_drift.py::TestCheckTaskLiveness::test_never_ran_sentinel PASSED [ 69%]
pipeline/tests/test_watchdog_drift.py::TestCheckTaskLiveness::test_nonzero_result PASSED [ 70%]
pipeline/tests/test_watchdog_drift.py::TestCheckTaskLiveness::test_stale_run_time PASSED [ 71%]
pipeline/tests/test_watchdog_drift.py::TestCheckTaskLiveness::test_missing_last_run_time_is_never_ran PASSED [ 73%]
pipeline/tests/test_watchdog_dedup.py::TestStableKey::test_key_joins_three_parts_with_pipe PASSED [ 74%]
pipeline/tests/test_watchdog_dedup.py::TestStableKey::test_key_with_no_output_path PASSED [ 76%]
pipeline/tests/test_watchdog_dedup.py::TestStateIO::test_load_missing_state_returns_empty PASSED [ 77%]
pipeline/tests/test_watchdog_dedup.py::TestStateIO::test_load_malformed_state_returns_empty PASSED [ 78%]
pipeline/tests/test_watchdog_dedup.py::TestStateIO::test_save_and_reload_roundtrip PASSED [ 80%]
pipeline/tests/test_watchdog_dedup.py::TestStateIO::test_save_is_atomic_no_tmp_left_behind PASSED [ 81%]
pipeline/tests/test_watchdog_dedup.py::TestUpdateState::test_new_issue_gets_alert_count_1 PASSED [ 83%]
pipeline/tests/test_watchdog_dedup.py::TestUpdateState::test_persistent_issue_increments_count PASSED [ 84%]
pipeline/tests/test_watchdog_dedup.py::TestUpdateState::test_resolved_issue_returns_resolved_list PASSED [ 85%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_clean_digest_has_all_section_headers PASSED [ 87%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_new_critical_renders_loud_block PASSED [ 88%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_persistent_issue_renders_compact_reminder PASSED [ 90%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_escalation_at_count_6 PASSED [ 91%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_escalation_refires_at_count_12 PASSED [ 92%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_resolved_tail_shows_recovered_keys PASSED [ 94%]
pipeline/tests/test_watchdog_dedup.py::TestBuildDigest::test_info_tier_not_rendered PASSED [ 95%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_happy_path_calls_send_alert PASSED [ 97%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_telegram_failure_writes_fallback_log PASSED [ 98%]
pipeline/tests/test_watchdog_telegram_fallback.py::TestSendOrLogDigest::test_dry_run_skips_telegram PASSED [100%]

============================= 71 passed in 0.56s ==============================
```
