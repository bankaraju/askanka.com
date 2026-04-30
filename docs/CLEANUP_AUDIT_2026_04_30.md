# Cleanup Audit — 2026-04-30

> **Pre-LIVE inventory of removal/archival candidates.** Review-list only — nothing deleted yet. Bharat to mark each item GO / KEEP / DEFER over the weekend.

---

## How to use this

Each item below has:
- **What** — the file / directory / system
- **Why** — why it's a removal candidate
- **Impact** — what breaks if removed
- **Action** — proposed disposition (delete / archive / consolidate / git-lfs / keep)

After Bharat reviews, GO items get a single follow-up commit that executes them. KEEP items get a one-line note in this file recording why they stay.

---

## A. Duplicate / superseded article generators

**What:** `pipeline/gen_*.py` — 7 scripts:
- `gen_today_5articles.py`
- `gen_remaining_articles.py`
- `gen_fresh_articles.py`
- `gen_epstein_today.py`
- `gen_verified_epstein.py`
- `gen_ceasefire_article.py`
- `gen_unified_paper.py`

**Why:** Article generation evolved over multiple sessions. `pipeline/daily_articles.py` and `pipeline/daily_articles_v2.py` are the canonical drivers. The `gen_*.py` files appear to be one-off scripts from earlier iterations.

**Impact:** Need to verify which (if any) is referenced by a scheduled task. If none, all 7 are removable.

**Action proposed:** **AUDIT FIRST** — grep `pipeline/scripts/*.bat` and `anka_inventory.json` for references. Any not referenced → archive to `pipeline/_archive/2026-04/`. Any referenced → keep but add inline doc-comment "production owner of <task>".

---

## B. Archived articles directory

**What:** `articles/_archive/` — 32 HTML files from 2026-04-08 → 2026-04-23.

**Why:** Already explicitly archived. Disk usage modest (~12MB total for `articles/`). Question is whether to keep in repo at all.

**Impact:** Removing breaks any `git log` / blame trail on archived articles. If referenced by old social-media posts (Twitter / LinkedIn), removing kills those links.

**Action proposed:** **KEEP in repo**. The 12MB cost is fine. Move to consideration only if repo size becomes a CI/CD bottleneck.

---

## C. Large media files in docs/

**What:** four files >15MB tracked in git:
| File | Size |
|---|---|
| `docs/The_self-correcting_Anka_Research_Golden_Goose.m4a` | 38MB |
| `docs/Engineering_The_Golden_Goose.mp4` | 21MB |
| `videos/week-006-war-part3.mp4` | 20MB |
| `docs/superpowers/specs/Anka_Trading_Terminal_UI_Architecture.pptx` | 19MB |
| `docs/superpowers/specs/Anka_Alpha_Extraction.pdf` | 18MB |
| `docs/superpowers/specs/Anka_Trading_Terminal_UI_Architecture.pdf` | 16MB |
| `docs/Anka_Research_Trading_Infrastructure.pdf` | 15MB |
| `docs/superpowers/specs/The_Anka_Clockwork.pdf` | 15MB |

**Why:** Total ~160MB of binary media in git. Slows `git clone`, bloats `.git/objects`. These rarely change after first commit, so they're pure repo weight.

**Impact:** Keeping them in git is fine until you onboard a teammate or run CI on a fresh clone — then it's painful.

**Action proposed:** **MOVE to git-LFS** or to a separate `assets/` repository. The PDFs are reference material, not active source. Keep in working tree but exclude from main repo's git history.

---

## D. Dead retired hypothesis ledgers

**What:** Per memory files, these hypotheses are DEAD / RETIRED:
- H-2026-04-24-001 (TA-Karpathy RELIANCE) — DEAD 2026-04-23
- H-2026-04-24-003 (persistent-break v2) — DEAD 2026-04-24
- H-2026-04-25-001 (earnings-decoupling) — DEAD 2026-04-25
- H-2026-04-25-002 (etf-stock-tail) — DEAD 2026-04-26
- ETF v2 (62.3% claim) — RETIRED 2026-04-26

**Search result:** **No matching files found** in `pipeline/data/research/` for these hypothesis IDs (already cleaned up earlier). Active research dirs only:
- `h_2026_04_26_001` (active forward holdout)
- `h_2026_04_26_003_neutral_long`
- `h_2026_04_29_intraday_v1` (postponed)
- `h_2026_04_29_ta_karpathy_v1` (active forward holdout)

**Action proposed:** **NO ACTION** — already clean. Add note to `ANALYSIS_CATALOG.md` confirming retired ledgers are not on disk.

---

## E. Calendar bug — replay engine fires on holidays

**What:** `pipeline/autoresearch/mechanical_replay/phase_c.py:77` uses `pd.bdate_range()` which excludes weekends but not Indian holidays.

**Why:** Bit us 2026-04-29 — 248 of 636 phase_c replay rows tagged FETCH_FAILED were market-holiday phantoms. Documented in `memory/reference_replay_calendar_bug_2026_04_29.md`.

**Impact:** Future replays will keep generating phantom signals on holidays unless patched. Low blast radius (FETCH_FAILED rows already drop out of analysis), but cleanup is mandatory before anyone trusts replay output unconditionally.

**Action proposed:** **FIX** — patch `phase_c.py:77` to consult `pipeline/data/trading_calendar.json` and exclude any date not marked as a trading day. Add a unit test that replays 2026-03-03 (Holi) and asserts zero rows fire.

---

## F. Stale data files in `data/` root that scheduler also writes to

**What:** Root-level `data/` files modified by today's scheduler runs: `articles_index.json`, `gap_risk.json`, `global_regime.json`, `live_status.json`, `today_recommendations.json`, `track_record.json`. Show up as modified in every `git status`.

**Why:** These files are written by scheduled tasks and intentionally not committed (per `feedback_website_trade_publish_blocked.md` deployment is muted). But they sit in the working tree and pollute `git status`.

**Impact:** Confuses any future automated commit step. Easy to accidentally commit one of these.

**Action proposed:** **ADD to .gitignore** OR move them out of the worktree to a sibling `runtime/` directory. Recommendation: gitignore is simpler.

---

## G. Empty / dead news pipeline

**What:** Per `SYSTEM_FAQ.md §5`, the news pipeline is structurally broken:
- `data/fno_news.json` is 2 bytes (`[]`)
- `pipeline/data/fno_news.json` is stale 6 days
- `pipeline/data/news_verdicts.json` has 314/314 NO_ACTION verdicts

**Why:** The classifier in `political_signals.py` grades every event NO_IMPACT — has been broken for weeks. The 04-27 spread trades that fired came from cached/fixture data, not the live classifier.

**Impact:** None to live trading (we kill-switched the news framework). But the dead pipeline is still wired up — daily Telegram has empty news cards, terminal has empty news tabs. Adds confusion.

**Action proposed:** **DECIDE**:
- (a) Repair the classifier (fix prompt, fix routing, restart shadow data)
- (b) Wire kill-switch — disable the broken classifier, stop scheduled tasks that feed it, hide news cards on terminal
- (c) Replace with the new Gemma-shadowed classifier wired tonight

Recommend (c) — once Gemma shadow data starts flowing 2026-04-30, judge by 2026-05-07 whether the new classifier produces meaningful verdicts. If yes, retire the old `political_signals.py:generate_signal_card` path. If no, kill-switch via (b).

---

## H. Repeat / overlapping scheduled tasks

**What:** Some VPS systemd timers and Windows scheduled tasks may overlap:
- `AnkaEarningsCalendarFetch` (Windows 08:00) AND `anka-earnings-calendar-fetch.service` (VPS 08:00) — both run, both write to the same parquet
- `AnkaDailyDump` (Windows DISABLED) and `anka-daily-dump.service` (VPS active) — Windows correctly disabled, but verify

**Why:** Per `feedback_prefer_vps_systemd_over_windows_scheduler.md`, VPS is the preferred execution layer. Windows duplicates create race conditions on shared output files.

**Action proposed:** **AUDIT** — for each VPS systemd timer, verify the corresponding Windows task is `Disabled`. Disable any Windows duplicates of VPS-active timers. Document in `CLAUDE.md` clockwork section which engine owns each task.

---

## I. Old test fixtures / mock data

**What:** Tests create fixture data; some leak to `pipeline/tests/fixtures/` and `pipeline/data/research/` paths. Need to grep.

**Why:** Risk: a "real" backtest accidentally reads test fixture data.

**Impact:** Worth a 30-min audit pre-LIVE.

**Action proposed:** **AUDIT** — grep for `fixture` / `mock` / `test_data` paths in `pipeline/data/research/`. Move any test artifacts to `pipeline/tests/fixtures/` exclusively.

---

## J. Pipeline test coverage gaps

**What:** 323 test files exist. Coverage is unknown. Per Section 3 of `GOVERNANCE_INDEX.md`, no CI runs them on PR.

**Why:** Pre-LIVE, you want a green-button confirmation that touching a file doesn't break anything.

**Action proposed:** **NEW WORK** (not cleanup):
1. Add CI workflow `.github/workflows/pytest.yml` that runs `pytest pipeline/tests/` on every PR
2. Run `pytest --cov=pipeline pipeline/tests/` once locally; record current coverage % as a baseline; commit `coverage_baseline_2026_04_30.txt`
3. Set CI to fail if coverage drops below baseline

---

## Summary triage table

| # | Item | Severity | Action proposed |
|---|---|---|---|
| A | gen_*.py duplicates | Med | Audit → archive |
| B | articles/_archive/ | Low | Keep |
| C | Large binaries in git | Med | Move to git-LFS |
| D | Dead hypothesis ledgers | Low | Already clean — note only |
| E | Replay calendar bug | **High** | Fix + test |
| F | Stale data files in worktree | Low | Add to .gitignore |
| G | Dead news pipeline | **High** | Repair via Gemma shadow OR kill-switch |
| H | Overlapping VPS+Windows tasks | Med | Audit + disable Windows duplicates |
| I | Test fixtures leaking | Low | Audit |
| J | No PR-level test CI | **High** | Add CI workflow |

**Recommended order before LIVE cutover:**
1. **E** (replay calendar bug) — small, mechanical fix; data integrity matters
2. **J** (PR-level test CI) — biggest leverage on code-governance gap
3. **G** (decide news pipeline fate) — depends on week-1 Gemma shadow data
4. **H** (Windows/VPS overlap audit) — prevents race conditions
5. **A**, **C**, **F**, **I** — incremental cleanup, no urgency

---

## Next step for Bharat

Read the items, mark each GO / KEEP / DEFER. I'll execute GO items in a single weekend cleanup commit. Items marked KEEP get a one-line annotation here recording the decision so we don't re-audit them next month.
