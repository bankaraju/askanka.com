# Unified Repo + Clockwork Operations — Design Spec

**Date:** 2026-04-14
**Status:** Approved (user mandate: "fix it yourself")
**Problem:** Two diverged repos causing lost code, stale data, confusion. Must be ONE repo, ONE truth, clockwork from 4:30 AM tomorrow.

## 1. Single Source of Truth

**Winner:** `C:/Users/Claude_Anka/askanka.com/` (the git repo)
**Killed:** `C:/Users/Claude_Anka/Documents/askanka.com/` (archived then deleted)

### Merge Rules
- Files only in Documents → copy to askanka.com
- Files in both, diverged → Documents wins (production-tested), EXCEPT:
  - `index.html` → askanka.com wins (has news scroll fix)
  - `pipeline/autoresearch/reverse_regime_*.py` → take BEST of both (Documents has tests, askanka.com has std fixes)
- `pipeline/.env` → merge (Documents has INDIANAPI_KEY)
- `pipeline/config.py` → Documents wins (has TMPV fix, 32 spreads)
- All data directories (signals/, daily/, india_historical/, etc.) → copy from Documents
- All test files → copy from Documents
- All logs/ → copy from Documents

### Path Update
Every .bat file updated: `Documents\askanka.com` → `askanka.com`

## 2. Clockwork Schedule (IST)

| Time | Script | What |
|------|--------|------|
| 04:30 | overnight_global.bat | EODHD global dump, Asian correlations, regime computation |
| 04:45 | daily_articles.bat | Generate war + epstein articles from overnight YouTube |
| 09:00 | refresh_kite.bat | Kite session refresh |
| 09:15 | premarket.bat | Pre-market briefing → Telegram |
| 09:25 | morning_scan.bat | Regime scanner, technicals, OI, news, spread intelligence, Phase B ranker |
| 09:30-15:30 (15min) | intraday_scan.bat | Technical + OI + news + spread intelligence + Phase C breaks |
| 09:30-15:30 (15min) | signals.bat | Signal generation + tracking |
| 15:30 | open_capture.bat | Capture closing prices |
| 16:00 | eod_track_record.bat | EOD P&L, track record update |
| 16:30 | website_export + fno_news | Export all data to website JSON + refresh news |
| Sunday 22:00 | weekly_stats.bat | Weekly spread statistics |

## 3. YouTube Watch History Auto-Sync

New channels the user watches get automatically added to the research pipeline.
- Google Takeout exports watch history as JSON
- Script parses new channels not already in config
- Adds to video_pipeline.py source list
- Syncs to Obsidian _inbox/

## 4. Sync Chain

```
askanka.com/ (git repo, single truth)
  ↓ git push
GitHub (remote backup)
  ↓ post-commit hook  
ObsidianVault/_claude_sessions/ (session logs)
  ↓ /wrapup skill
NotebookLM AI Brain (session summaries)
```

No conflicts possible — one repo, one direction.
