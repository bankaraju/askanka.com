# Scheduler Debt Remediation — Design Spec

**Date:** 2026-04-16
**Author:** Bharat Ankaraju + Claude
**Status:** Design approved, ready for plan
**Follow-up of:** 2026-04-14 unified-repo-clockwork, 2026-04-14 Phase A/B/C reverse-regime suite, 2026-04-15 session-log parked triage items

---

## Context — The Apr 12–16 sequence

This remediation is not a new bug hunt. It closes debt accumulated across five days of progressive build:

- **Apr 12** — 7-layer pipeline foundation, terminal, narrative, spread composer. 284 tests. 30+ commits.
- **Apr 13** — Wired autoresearch + live Kite terminal. Absorbed the *USE EXISTING SYSTEMS* rule.
- **Apr 14** — Two big parallel builds on one day: repo unification (Documents\ → askanka.com) AND the Reverse Regime Engine (Phase A profile, Phase B ranker, Phase C correlation breaks). Scheduler grew and changed simultaneously; migration updated `.bat` files but not every `schtasks` Execute string; Phase A/B/C plans built code but didn't mandate "register as task + verify output" steps.
- **Apr 15** — Surface polish (website-cleanup-regime-score, website-recommendations-panel, article-grounding, trailing-stop-and-replay). Session log explicitly parked scheduler staleness as "new triage items" (fno_news, open_signals, msi_history). Chose surface ship over plumbing sweep.
- **Apr 16** — Parked triage compounded. Today's audit finds Phase A unscheduled (2-day-stale profile), Phase C CLI mismatch (never produces output), 28 Documents\ zombies, 27 embedded-quote-bug tasks, 5 never-ran tasks, ~20-file stale cluster at Apr 14 15:38, 11 untracked pipeline scripts.

**Framing:** This plan closes Apr 14's scheduler debt so Apr 15's downstream consumers (website, articles, recs panel, trail stop) can display the truth. The "same issues" feeling is exactly this — Apr 15 patched symptoms; we're now addressing producers.

---

## Section 1 — Scope

**In scope (7 gap categories):**

1. Phase A (`reverse_regime_analysis.py`) not scheduled → `reverse_regime_profile.json` 2 days stale; Phase B's input contract broken.
2. `AnkaCorrelationBreaks` CLI mismatch — `.bat` passes `--day 1 --no-telegram`; `reverse_regime_breaks.py` argparse expects `--regime / --transition / --dry-run / --verbose`. Phase C never produces output.
3. 28 scheduled tasks pointing to retired `C:\Users\Claude_Anka\Documents\askanka.com\` path (migration zombies).
4. 27 tasks with embedded `""` double-quote bugs in Execute strings — some never launch.
5. 5 tasks never ran (`LastTaskResult=267011`, `LastRunTime=1999-12-30`): `AnkaEODNews` (registered today 16:20 — likely fine), `AnkaGapPredictor`, `AnkaPruneArticles`, `AnkaSpreadStats`, `AnkaWeeklyStats`.
6. ~20-file stale cluster at Apr 14 15:38 in `pipeline/data/*.json` — symptom of a single master EOD job silently failing since Apr 14.
7. 2 untracked pipeline scripts that own stale-cluster files: `options_monitor.py` (owns `oi_history.json`), and `gamma_scanner.py` if it turns out to write `gamma_result.json` (grep came up empty — orphan suspected).

**Out of scope (deferred, each gets own future brainstorm):**

- Structural "scheduler has no git" problem — `scheduled_tasks_inventory.json` + health-check cron for file-age invariants.
- 9 other untracked pipeline scripts (`regime_playbook`, `sector_rotation`, `unified_regime_engine`, `pinning_*`, `expiry_monitor`, `data_validator`, `video_pipeline`, `regime_signals`) — judgment-per-file, not pure cleanup.
- Task Scheduler Operational log enable (needs UAC, can't resolve in-session).
- Phase A *design* improvements — this plan schedules Phase A as interim cron; proper design is fresh brainstorm.
- Investor deck review (separate artifact).
- Any algorithm / new signal work.

**Anchoring documents:**

- `docs/superpowers/specs/2026-04-14-unified-repo-clockwork-design.md` (proves Documents\ was archived + deleted → zombies safe to delete)
- `docs/superpowers/plans/2026-04-14-correlation-break-detector.md` (Phase C authoritative CLI)
- `docs/superpowers/plans/2026-04-14-reverse-regime-stock-analysis.md` (Phase A expected cadence)
- `docs/superpowers/plans/2026-04-14-daily-regime-stock-ranker.md` (Phase B input contract)
- `docs/superpowers/plans/2026-04-15-website-cleanup-regime-score.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-website-recommendations-panel.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-article-grounding.md` (downstream consumer)
- `docs/superpowers/plans/2026-04-15-trailing-stop-and-replay.md` (downstream consumer)
- `memory/project_session_2026_04_15.md` (parked triage items this plan closes)

---

## Section 2 — The diagnose artifact

A single mapping table embedded at the top of the implementation plan. One row per gap. Six columns:

| Gap | Evidence (file / task — what's wrong) | Bucket | Parent plan + § | Drift note | Remediation action |
|-----|---------------------------------------|--------|-----------------|------------|---------------------|

**Buckets:**
- **(i) Re-run** — parent plan exists; live state drifted; re-execute a specific plan step.
- **(ii) Hygiene** — parent plan says this should not exist or should look different; delete or rewrite.
- **(iii) NEW** — no parent plan covers this; flag for future brainstorm; do NOT fix in this plan.

**Seed rows (drafted now; plan produces the full table):**

| Gap | Evidence | Bucket | Parent plan + § | Drift note | Remediation action |
|-----|----------|--------|-----------------|------------|---------------------|
| 28 Documents\ zombies | `schtasks /query` shows Execute=`C:\Users\Claude_Anka\Documents\askanka.com\...` on 28 tasks | (ii) | `2026-04-14-unified-repo-clockwork` §Migration | Spec says Documents\ "archived then deleted" — these are post-migration leftovers | Batch B1: Unregister-ScheduledTask on all 28 after XML backup |
| AnkaCorrelationBreaks CLI | `.bat` passes `--day 1 --no-telegram`; script argparse rejects | (i) | `2026-04-14-correlation-break-detector` §CLI | `.bat` written against earlier CLI spec | Batch C1: rewrite `.bat` per §CLI, run once manually, confirm output file produced |
| Phase A not scheduled | No Anka* task executes `reverse_regime_analysis.py`; `reverse_regime_profile.json` = Apr 14 | (iii) interim (i) | — | Phase B runs anyway with 2-day-stale profile — *live data-integrity issue* | Batch C2: schedule `AnkaReverseRegimeProfile` @ 04:45 IST as INTERIM-BEFORE-BRAINSTORM |
| 27 quote-bug Execute strings | `Actions[0].Execute` contains `""...""` | (ii) | `2026-04-14-unified-repo-clockwork` §Migration | Re-registration side-effect during migration | Batch B2: per-task Unregister + Register with clean `New-ScheduledTaskAction -Execute` |
| 5 never-ran tasks | `LastTaskResult=267011`, `LastRunTime=1999-12-30` | (ii) | overlap with B2 | Quote-bug-class; re-registration clears both | Batch B3: re-register from XML backup, Start-ScheduledTask manually, confirm LastTaskResult=0 |
| Apr 14 15:38 cluster (~20 files) | 20+ `pipeline/data/*.json` share exact mtime Apr 14 15:38 | (i) master-job | `2026-04-14-unified-repo-clockwork` (task registry) | Single master EOD job wrote them all, stopped firing cleanly after Apr 14 | Batch C3: identify master job (likely `eod_track_record.bat` / `run_eod_report.py`), diagnose why it stopped, fix once |
| gamma_result.json orphan | File exists (231 bytes); no writer in codebase; `gamma_scanner.py` untracked | (ii) hygiene | — | Either orphan (delete) or writer is in untracked `gamma_scanner.py` (commit-or-delete) | Batch C3.x: grep untracked writer; if orphan, delete file; if untracked writer, decide commit / delete |
| 2 untracked writers (options_monitor, gamma_scanner?) | `git status` shows untracked; owns stale-cluster files | (ii) hygiene | — | Single-repo mandate violation | Batch C3.x: commit or delete per judgment after reading the scripts |
| 9 other untracked scripts | `git status` — 9 files unrelated to stale cluster | (iii) NEW | — | Single-repo mandate; judgment-per-file | Flag in mapping; defer to own mini-plan |

**Why this is the anchor artifact:** every Batch-B and Batch-C step cites a row number in this table. If a step has no row, it's out of scope. If a row has no Remediation-action, the plan is not complete.

### Full mapping table (populated 2026-04-16 Batch A6)

Row counts reconciled with `/tmp/audit_out.txt` (committed to transcript A1):
- **29 zombies** = 4 unquoted-Documents\ (AnkaARCBE2300, AnkaEOD1630, AnkaWeeklyVideo, OpenCapture) + 24 quoted-Documents\ intraday slots + AnkaSpreadStats (Documents\, quoted) = 29
- **28 Anka-scope quote-bugs** = 3 askanka.com (AnkaCorrelationBreaks, AnkaGapPredictor, AnkaPruneArticles) + 24 intraday (Documents\) + AnkaSpreadStats (Documents\) = 28. UpdateLibrary is a Windows Media Player system task — out of scope.
- **5 Anka-scope never-ran** = AnkaEODNews, AnkaGapPredictor, AnkaPruneArticles, AnkaSpreadStats, AnkaWeeklyStats. The other 33 never-ran tasks are Windows system tasks unrelated to this plan.

Overlap: AnkaGapPredictor and AnkaPruneArticles appear in both quote-bug and never-ran buckets; AnkaSpreadStats appears in all three (zombie + quote-bug + never-ran). Remediation order: B1 delete first, then B2 rewrite, then B3 re-register only what remains.

| # | Gap | Evidence | Bucket | Parent plan + § | Drift note | Remediation action | Status |
|---|-----|----------|--------|-----------------|------------|---------------------|--------|
| 1 | Zombie: AnkaARCBE2300 | Execute=`C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\arcbe_scan.bat` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover | Unregister (Batch B1) | DONE |
| 2 | Zombie: AnkaEOD1630 | Execute=`C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\eod_track_record.bat` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover; likely the master EOD job (C3 scope) | Unregister (Batch B1); re-register fresh from askanka.com path in C3 | DONE |
| 3 | Zombie: AnkaIntraday0940 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 4 | Zombie: AnkaIntraday0955 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 5 | Zombie: AnkaIntraday1010 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 6 | Zombie: AnkaIntraday1025 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 7 | Zombie: AnkaIntraday1040 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 8 | Zombie: AnkaIntraday1055 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 9 | Zombie: AnkaIntraday1110 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 10 | Zombie: AnkaIntraday1125 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 11 | Zombie: AnkaIntraday1140 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 12 | Zombie: AnkaIntraday1155 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 13 | Zombie: AnkaIntraday1210 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 14 | Zombie: AnkaIntraday1225 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 15 | Zombie: AnkaIntraday1240 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 16 | Zombie: AnkaIntraday1255 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 17 | Zombie: AnkaIntraday1310 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 18 | Zombie: AnkaIntraday1325 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 19 | Zombie: AnkaIntraday1340 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 20 | Zombie: AnkaIntraday1355 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 21 | Zombie: AnkaIntraday1410 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 22 | Zombie: AnkaIntraday1425 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 23 | Zombie: AnkaIntraday1440 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 24 | Zombie: AnkaIntraday1455 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 25 | Zombie: AnkaIntraday1510 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 26 | Zombie: AnkaIntraday1525 | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\intraday_scan.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover + quote-bug | Unregister (Batch B1) | DONE |
| 27 | Zombie + Quote-bug + Never-ran: AnkaSpreadStats | Execute=`"C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_stats.bat"`; LastResult=267011 | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Triple-hit: Documents\ + quote-wrap + never-ran | Unregister (B1); task AnkaWeeklyStats already holds the askanka.com cron slot | DONE |
| 28 | Zombie: AnkaWeeklyVideo | Execute=`C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\weekly_video.bat` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover | Unregister (Batch B1) | DONE |
| 29 | Zombie: OpenCapture (TaskPath=\Anka\) | Execute=`C:\Users\Claude_Anka\Documents\askanka.com\pipeline\scripts\open_capture.bat` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Post-migration leftover under \Anka\ folder | Unregister (Batch B1) | DONE |
| 30 | Quote-bug: AnkaCorrelationBreaks | Execute=`"C:\Users\Claude_Anka\askanka.com\pipeline\scripts\correlation_breaks.bat"` | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Re-registration side-effect (askanka.com path — legit target, quotes wrong) | Unregister+Register clean (Batch B2); also C1 CLI fix to the .bat | DONE (B2 re-register; C1 still PENDING) |
| 31 | Quote-bug + Never-ran: AnkaGapPredictor | Execute=`"C:\Users\Claude_Anka\askanka.com\pipeline\scripts\gap_predictor.bat"`; LastResult=267011 | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Quote-bug caused never-ran | Unregister+Register clean (B2); verified manual run in B3 (LastResult=0 @ 2026-04-16 12:20:50) | DONE |
| 32 | Quote-bug + Never-ran: AnkaPruneArticles | Execute=`"C:\Users\Claude_Anka\askanka.com\pipeline\scripts\prune_articles.bat"`; LastResult=267011 | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Quote-bug caused never-ran | Unregister+Register clean (B2); verified manual run in B3 (LastResult=0 @ 2026-04-16 12:20:50) | DONE |
| 33 | Quote-bug (quoted Documents\): AnkaIntraday0940 | Overlap with row 3 (zombie) | (ii) | — | Deleted via row 3 | N/A — subsumed by B1 row 3 | PENDING (subsumed) |
| 34 | Quote-bug (quoted Documents\): AnkaIntraday0955 | Overlap with row 4 (zombie) | (ii) | — | Deleted via row 4 | N/A — subsumed by B1 row 4 | PENDING (subsumed) |
| 35 | Quote-bug (quoted Documents\): AnkaIntraday1010 | Overlap with row 5 (zombie) | (ii) | — | Deleted via row 5 | N/A — subsumed by B1 row 5 | PENDING (subsumed) |
| 36 | Quote-bug (quoted Documents\): AnkaIntraday1025 | Overlap with row 6 (zombie) | (ii) | — | Deleted via row 6 | N/A — subsumed by B1 row 6 | PENDING (subsumed) |
| 37 | Quote-bug (quoted Documents\): AnkaIntraday1040 | Overlap with row 7 (zombie) | (ii) | — | Deleted via row 7 | N/A — subsumed by B1 row 7 | PENDING (subsumed) |
| 38 | Quote-bug (quoted Documents\): AnkaIntraday1055 | Overlap with row 8 (zombie) | (ii) | — | Deleted via row 8 | N/A — subsumed by B1 row 8 | PENDING (subsumed) |
| 39 | Quote-bug (quoted Documents\): AnkaIntraday1110 | Overlap with row 9 (zombie) | (ii) | — | Deleted via row 9 | N/A — subsumed by B1 row 9 | PENDING (subsumed) |
| 40 | Quote-bug (quoted Documents\): AnkaIntraday1125 | Overlap with row 10 (zombie) | (ii) | — | Deleted via row 10 | N/A — subsumed by B1 row 10 | PENDING (subsumed) |
| 41 | Quote-bug (quoted Documents\): AnkaIntraday1140 | Overlap with row 11 (zombie) | (ii) | — | Deleted via row 11 | N/A — subsumed by B1 row 11 | PENDING (subsumed) |
| 42 | Quote-bug (quoted Documents\): AnkaIntraday1155 | Overlap with row 12 (zombie) | (ii) | — | Deleted via row 12 | N/A — subsumed by B1 row 12 | PENDING (subsumed) |
| 43 | Quote-bug (quoted Documents\): AnkaIntraday1210 | Overlap with row 13 (zombie) | (ii) | — | Deleted via row 13 | N/A — subsumed by B1 row 13 | PENDING (subsumed) |
| 44 | Quote-bug (quoted Documents\): AnkaIntraday1225 | Overlap with row 14 (zombie) | (ii) | — | Deleted via row 14 | N/A — subsumed by B1 row 14 | PENDING (subsumed) |
| 45 | Quote-bug (quoted Documents\): AnkaIntraday1240 | Overlap with row 15 (zombie) | (ii) | — | Deleted via row 15 | N/A — subsumed by B1 row 15 | PENDING (subsumed) |
| 46 | Quote-bug (quoted Documents\): AnkaIntraday1255 | Overlap with row 16 (zombie) | (ii) | — | Deleted via row 16 | N/A — subsumed by B1 row 16 | PENDING (subsumed) |
| 47 | Quote-bug (quoted Documents\): AnkaIntraday1310 | Overlap with row 17 (zombie) | (ii) | — | Deleted via row 17 | N/A — subsumed by B1 row 17 | PENDING (subsumed) |
| 48 | Quote-bug (quoted Documents\): AnkaIntraday1325 | Overlap with row 18 (zombie) | (ii) | — | Deleted via row 18 | N/A — subsumed by B1 row 18 | PENDING (subsumed) |
| 49 | Quote-bug (quoted Documents\): AnkaIntraday1340 | Overlap with row 19 (zombie) | (ii) | — | Deleted via row 19 | N/A — subsumed by B1 row 19 | PENDING (subsumed) |
| 50 | Quote-bug (quoted Documents\): AnkaIntraday1355 | Overlap with row 20 (zombie) | (ii) | — | Deleted via row 20 | N/A — subsumed by B1 row 20 | PENDING (subsumed) |
| 51 | Quote-bug (quoted Documents\): AnkaIntraday1410 | Overlap with row 21 (zombie) | (ii) | — | Deleted via row 21 | N/A — subsumed by B1 row 21 | PENDING (subsumed) |
| 52 | Quote-bug (quoted Documents\): AnkaIntraday1425 | Overlap with row 22 (zombie) | (ii) | — | Deleted via row 22 | N/A — subsumed by B1 row 22 | PENDING (subsumed) |
| 53 | Quote-bug (quoted Documents\): AnkaIntraday1440 | Overlap with row 23 (zombie) | (ii) | — | Deleted via row 23 | N/A — subsumed by B1 row 23 | PENDING (subsumed) |
| 54 | Quote-bug (quoted Documents\): AnkaIntraday1455 | Overlap with row 24 (zombie) | (ii) | — | Deleted via row 24 | N/A — subsumed by B1 row 24 | PENDING (subsumed) |
| 55 | Quote-bug (quoted Documents\): AnkaIntraday1510 | Overlap with row 25 (zombie) | (ii) | — | Deleted via row 25 | N/A — subsumed by B1 row 25 | PENDING (subsumed) |
| 56 | Quote-bug (quoted Documents\): AnkaIntraday1525 | Overlap with row 26 (zombie) | (ii) | — | Deleted via row 26 | N/A — subsumed by B1 row 26 | PENDING (subsumed) |
| 57 | Quote-bug (quoted Documents\): AnkaSpreadStats | Overlap with row 27 | (ii) | — | Deleted via row 27 | N/A — subsumed by B1 row 27 | PENDING (subsumed) |
| 58 | Never-ran: AnkaEODNews | LastResult=267011; Execute=`C:\Users\Claude_Anka\askanka.com\pipeline\scripts\overnight_news.bat` (clean path, no quote-bug) | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Recently registered; needs first successful run to flip flag | Verified via manual Start-ScheduledTask in B3 — LastResult=0 @ 2026-04-16 12:19:49 | DONE |
| 59 | Never-ran: AnkaGapPredictor | Overlap with row 31 | (ii) | — | Fixed in row 31's B2 re-register; B3 manual run PASS | N/A — subsumed by row 31 | DONE (subsumed) |
| 60 | Never-ran: AnkaPruneArticles | Overlap with row 32 | (ii) | — | Fixed in row 32's B2 re-register; B3 manual run PASS | N/A — subsumed by row 32 | DONE (subsumed) |
| 61 | Never-ran: AnkaSpreadStats | Overlap with row 27 | (ii) | — | Deleted via row 27; AnkaWeeklyStats is the askanka.com-path replacement; B3 skipped (.bat no longer exists post-B1) | N/A — subsumed by row 27 | DONE (subsumed) |
| 62 | Never-ran: AnkaWeeklyStats | LastResult=267011; Execute=`C:\Users\Claude_Anka\askanka.com\pipeline\scripts\weekly_stats.bat` (clean path, no quote-bug) | (ii) | 2026-04-14-unified-repo-clockwork §Migration | Needs first successful run to flip flag | Verified via manual Start-ScheduledTask in B3 — LastResult=0 @ 2026-04-16 12:20:50 (transient 267009 mid-run cleared after extended poll) | DONE |
| 63 | Phase A not scheduled | No task runs `reverse_regime_analysis.py`; `reverse_regime_profile.json` = Apr 14 (2-day stale) | (iii) interim (i) | — | Phase B runs with stale profile — live data-integrity issue | Schedule AnkaReverseRegimeProfile @ 04:45 IST (Batch C2) as INTERIM | PENDING |
| 64 | AnkaCorrelationBreaks CLI | `correlation_breaks.bat` passes `--day 1 --no-telegram` which argparse rejects | (i) | 2026-04-14-correlation-break-detector §CLI | `.bat` written against older CLI | Strip those args from .bat (Batch C1) | PENDING |
| 65 | Apr 14 15:38 cluster | 18 `pipeline/data/*.json` files share exact mtime Apr 14 15:38 (snapshotted in A3) | (i) master-job | 2026-04-14-unified-repo-clockwork (task registry) | Master EOD job stopped firing — almost certainly AnkaEOD1630 which points to Documents\eod_track_record.bat (zombie row 2) | Identify + diagnose + fix master (Batch C3); re-register AnkaEOD1630 fresh at askanka.com path | PENDING |
| 66 | gamma_result.json orphan | 231 bytes; no committed writer in codebase | (ii) hygiene | — | Delete or resolve via gamma_scanner.py untracked script | Resolve in Batch C3.x | PENDING |
| 67 | options_monitor.py untracked | `git status` shows untracked; writes oi_history.json | (ii) hygiene | — | Single-repo mandate violation | Commit or delete in Batch C3.x | PENDING |
| 68 | 9 other untracked scripts | `git status`: daily_articles_v2, data_validator, expiry_monitor, gen_*, pinning_*, regime_*, sector_rotation, unified_regime_engine, video_pipeline, list_gemini_models | (iii) NEW | — | Judgment-per-file | Defer to future mini-plan | DEFERRED-NEW |

**Row totals:** 68 rows. Breakdown: 29 zombie (rows 1–29, including 25 overlap-to-quote-bug and 1 triple-hit AnkaSpreadStats), 3 askanka.com quote-bugs (30, 31, 32), 25 quote-bug subsumed (33–57), 5 never-ran (58 + 3 subsumed 59–61 + 62), 5 "fixed" categories (63 Phase A interim, 64 Phase C CLI, 65 master job, 66 orphan, 67 options_monitor), 1 deferred (68).

---

## Section 3 — Batch A: Backup + verification (zero destructive ops)

**Goal:** Produce the mapping table. Make every destructive step in Batch B/C reversible. No scheduler state changes.

**Steps:**

1. **Export XML for every affected scheduled task** via `Export-ScheduledTask` → `pipeline/backups/scheduled_tasks/2026-04-16/*.xml`. Covers: 28 zombies, 27 quote-bug tasks, 5 never-ran tasks, `AnkaCorrelationBreaks`, plus any task touched by Batch C. Deduplicated.

2. **Produce the full mapping table** — populate every row for all 7 gap categories + the orphan/untracked rows. Write to this spec's implementation plan.

3. **Dry-run every deletion and re-registration.** For each zombie: re-confirm Documents\ in Execute. For each quote-bug fix: print proposed-clean vs current-broken Execute. For each never-ran task: confirm target `.bat` exists on disk.

4. **Verify the 2026-04-14-unified-repo-clockwork spec claim.** Re-read §Migration, confirm "archived then deleted." If spec says anything else, STOP and escalate.

5. **Snapshot current stale intermediates** to `pipeline/backups/data_snapshots/2026-04-16/` before any Batch-C re-run that could overwrite.

6. **Commit XML backups + mapping-table spec** on dedicated branch `remediate/scheduler-debt-2026-04-16`. One commit per logical group.

**Exit gate:**

- XML backups exist for every affected task
- Mapping table written, self-reviewed for placeholders/contradictions, committed
- Dry-run transcript captured in `docs/operations/2026-04-16-batch-a-transcript.md` (committed)
- Snapshot of stale intermediates in place

**Blast radius:** zero. Read-only + file writes to backup/spec/transcript paths.

---

## Section 4 — Batch B: Hygiene (highest blast radius)

**Precondition:** Batch A exit gate passed.

**Step B1 — Delete 28 Documents\ zombies.**
- Re-read `2026-04-14-unified-repo-clockwork-design.md` §Migration (confirmation gate).
- For each of 28: `Unregister-ScheduledTask -TaskName <n> -Confirm:$false`.
- Per-task, not batched; log each to transcript.
- **Verify:** `Get-ScheduledTask | ? { $_.Actions[0].Execute -like '*Documents\askanka*' }` returns 0 rows.

**Step B2 — Fix 27 quote-bug Execute strings.**
- Strategy: `Unregister` + `Register-ScheduledTask` with clean `New-ScheduledTaskAction -Execute <path>`.
- Preserve trigger / settings / RunLevel / user from XML backup.
- Per-task, not batched (different API surface per task makes one-error-kills-run risk in batched mode).
- **Verify per task:** new Execute has zero embedded `"`; `Get-ScheduledTaskInfo` shows populated NextRunTime.

**Step B3 — Re-register the 5 never-ran tasks.**
- List: `AnkaEODNews`, `AnkaGapPredictor`, `AnkaPruneArticles`, `AnkaSpreadStats`, `AnkaWeeklyStats`.
- For each: confirm target `.bat` exists; if it does, re-registration from XML backup typically clears the quote-bug class (overlap with B2).
- `AnkaEODNews` exception: registered today, just verify state=Ready + clean action.
- **Run once manually** via `Start-ScheduledTask` inside this batch; confirm `LastTaskResult=0` within 2 min.
- If any target `.bat` missing OR manual run non-zero: do NOT re-schedule; log as (iii) NEW and escalate.

**Step B4 — Post-Batch-B sweep.**
- Re-run Batch A audit queries:
  - 0 tasks with Documents\ path
  - 0 tasks with `""` in Execute
  - 0 tasks with `LastTaskResult=267011` or `LastRunTime=1999`
  - Task count decreased by exactly 28 minus any legitimate B3 adds
- Commit transcript to `docs/operations/2026-04-16-batch-b-transcript.md`.

**Exit gate:**
- Sweep passes all four invariants
- Transcript committed
- Every re-registered task either ran clean (LastTaskResult=0) or is queued with valid NextRunTime

**Blast radius:** moderate. ~55 total ops (28 deletions + ~27 re-registrations). Reversible via `Register-ScheduledTask -Xml (Get-Content <backup>.xml | Out-String)`.

---

## Section 5 — Batch C: Wiring & freshness (master-job lens)

**Precondition:** Batch B exit gate passed.

**Step C1 — Fix AnkaCorrelationBreaks CLI.**
- Rewrite `pipeline/scripts/correlation_breaks.bat` to pass the args that `reverse_regime_breaks.py` actually accepts per `2026-04-14-correlation-break-detector.md` §CLI.
- **Verify:** manual run; script returns 0; expected output file written.

**Step C2 — Schedule Phase A (interim-before-brainstorm).**
- Register `AnkaReverseRegimeProfile`:
  - Action: `pipeline/scripts/reverse_regime_profile.bat` (create thin wrapper around `python reverse_regime_analysis.py`)
  - Trigger: Daily @ 04:45 IST
  - Settings: canonical Anka defaults (WakeToRun, AllowStartIfOnBatteries, StartWhenAvailable, MultipleInstances IgnoreNew, ExecutionTimeLimit 2h)
- Description field: `INTERIM — pending fresh brainstorm 2026-04-17+`.
- **Verify:** `Start-ScheduledTask` immediately; within 5 min confirm `pipeline/data/reverse_regime_profile.json` mtime = today + LastTaskResult=0.

**Step C3 — Master EOD job: identify, diagnose, fix once.**
- **Identify:** grep pipeline/ for writers of the Apr-14-15:38 cluster files (beyond the 6 we already owner-mapped). Candidates: `eod_track_record.bat`, `run_eod_report.py`, `eod_review.bat`. Cross-reference schtasks for a task that matches the 15:38 cadence.
- **Diagnose:** inspect the master task's logs + last run result. Likely root causes: quote-bug (→ fixed in B2 if task was in that set), .bat points to missing script, upstream data source change.
- **Fix once:** apply root-cause fix, manual run, confirm cluster files refresh to today's mtime.
- If master turns out to be *multiple* jobs: handle each; abandon "one master" framing; document in transcript.

**Step C3.x — Orphan / untracked writer resolution.**
- `gamma_result.json`: grep untracked `gamma_scanner.py` for the filename; if writer found, decide commit / delete per judgment; if orphan, delete `gamma_result.json`.
- `options_monitor.py` (untracked, owns `oi_history.json`): read the script, decide commit / delete. If committing, ensure a scheduled task exists and is healthy (may overlap with B2).

**Step C4 — Downstream Apr 15 consumer verification.**
- Run `pipeline/website_exporter.py` manually; confirm `live_status.json`, `global_regime.json`, `articles_index.json`, recommendations panel all render with today's timestamps.
- Run article grounding self-test against today's war article — confirm no `MarketDataMissing` exception.
- Run one full `intraday_scan.bat` cycle; confirm trail_stop telemetry populated on each open signal.
- Fresh `data/*.json` → auto-deploy commit + push (already wired in `website_exporter.py`).

**Step C5 — Post-Batch-C health check.**
- `pipeline/data/reverse_regime_profile.json` mtime = today
- Apr-14-15:38 cluster: files refreshed to today OR master-job fate documented in mapping table as NEW
- Mapping table: every row's Remediation-action = DONE or DEFERRED-NEW (no pending rows)
- Transcript committed to `docs/operations/2026-04-16-batch-c-transcript.md`

**Exit gate:** all of C5 above.

**Blast radius:** low. One CLI rewrite (reversible via git), one new task (reversible via Unregister), one-shot job re-runs (no state change).

---

## Section 6 — Acceptance criteria, rollback, risks, testing

**Acceptance criteria (measurable end-state invariants):**

1. `Get-ScheduledTask` returns 0 tasks whose Execute contains `Documents\askanka.com` or `""`.
2. 0 tasks with `LastTaskResult=267011` or `LastRunTime=1999-12-30`.
3. `pipeline/data/reverse_regime_profile.json` mtime = today.
4. Master EOD job identified + re-run successfully → Apr 14 15:38 cluster refreshed to today (OR master-job fate documented in mapping table as NEW if irrecoverable).
5. AnkaCorrelationBreaks manual run produces non-empty expected output file.
6. Mapping table: every row's Remediation-action = DONE or DEFERRED-NEW.
7. All three batch transcripts committed to `docs/operations/`.
8. No drive-by code changes outside the plan's batches.

**Rollback strategy:**

- Per-batch: every destructive op reversible via XML re-import from `pipeline/backups/scheduled_tasks/2026-04-16/`.
- Meta-rollback: entire plan runs on branch `remediate/scheduler-debt-2026-04-16`. Go off-rails → `git branch -D` + re-register from XML backups. Zero lasting damage.
- Snapshot intermediates in `pipeline/backups/data_snapshots/2026-04-16/` enable diff against re-run output.

**Risks + mitigations:**

| Risk | Likelihood | Blast | Mitigation |
|------|------------|-------|-----------|
| XML re-register changes task ID / GUID breaks downstream consumers | low | medium | Rollback-test on `AnkaGapPredictor` (already broken) before production-critical tasks |
| Master EOD turns out to be N > 1 jobs, not one | medium | low-medium | Handle each; abandon "one master" framing; document |
| Re-run writes worse output than stale | low | low | Snapshots in place |
| Hidden load-bearing Documents\ task | very low | high | §Migration spec re-read gate in Batch A — STOP if spec says keep anything |
| PowerShell encoding / special-char task names | low | low | `-FilePath` with UTF-8 `.ps1` files, not inline `-Command` |
| Plan execution spans sessions, context lost | medium | medium | Checkbox-task format per superpowers:writing-plans; each step independently re-runnable |

**Testing approach:**

- No new unit tests — ops remediation, not code.
- "Test" = each step has a verify command whose output goes to the batch transcript.
- End-to-end smoke at Batch C4: `website_exporter.py` + article grounding self-check + one full `intraday_scan.bat` cycle. All green → plan complete.

**Deferred (flagged, not in this plan):**

- `scheduled_tasks_inventory.json` in git + health-check cron (structural fix for "scheduler has no git")
- 9 other untracked pipeline scripts (judgment-per-file mini-plan)
- Task Scheduler Operational log enable (UAC blocker)
- Phase A *design* improvements (fresh brainstorm after interim cron lands)

---

## Self-review

**Placeholder scan:** None. Every section has concrete commands, paths, and verify steps. "TBD" absent.

**Internal consistency:**
- Batch A creates XML backups → Batch B uses them for rollback. ✓
- Batch A produces mapping table → Batches B/C cite row numbers. ✓
- Batch B fixes quote-bugs → Batch B3 notes overlap with B2 instead of duplicating. ✓
- Master-job lens in C3 is the single root-cause fix for the 20-file cluster, not 20 separate re-runs. ✓
- Acceptance criteria #4 explicitly allows "documented as NEW" escape hatch if master job is irrecoverable. ✓

**Scope check:** Focused. 7 in-scope gap categories, 4 explicit deferrals. Not mixing algorithm changes, not mixing UI work, not re-brainstorming Phase A design.

**Ambiguity:** The 27-vs-28 accounting in Batch B is clear (28 deletions + some overlap with B2/B3 re-registrations, tracked per-task in transcript). "Master EOD job" is hypothesis-framed, with explicit fallback if it turns out to be multiple.
