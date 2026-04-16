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
