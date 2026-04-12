# Context Autowrap Skill — Design Spec

**Date:** 2026-04-12
**Status:** Reviewed — code-reviewer feedback applied

## Problem

Long Claude Code sessions lose context when the conversation auto-compacts. Valuable session state (decisions, in-progress work, memory updates) can be lost if not persisted before compaction. The existing `/wrapup` skill handles end-of-session saves but is designed for terminal wrap-up, not mid-session checkpoints.

## Solution

A new `/autowrap` command skill that performs a lightweight mid-session checkpoint. Unlike `/wrapup`, it is designed to be invoked multiple times per session without disrupting workflow.

## Trigger Mechanism

Claude Code has no native "context usage %" hook event. Instead:
- Add a CLAUDE.md instruction telling Claude to self-invoke `/autowrap` when context feels heavy or after 2+ hours of continuous work.
- This is advisory, not automatic. The user can also invoke `/autowrap` manually at any time.

## What `/autowrap` Does (5 steps)

### Step 1: Session Snapshot
Scan the conversation for:
- Work completed since last autowrap (or session start)
- Decisions made
- Open threads / in-progress work
- Any user feedback or preferences revealed

### Step 2: Save/Update Memories
Write or update memory files following the existing memory system rules:
- Only save non-obvious, cross-session-useful information
- Don't duplicate what's in code/git
- Update existing memories rather than creating duplicates
- Update MEMORY.md index

### Step 3: Commit Dirty Files
```bash
cd <working-directory>
git add -u  # tracked files only — never bulk-add untracked scripts
git status --short
# If there are staged changes:
git commit -m "autowrap: mid-session checkpoint <timestamp>"
```
- Use `git add -u` (tracked modified/deleted only) — NEVER `git add -A` which would stage untracked experimental scripts
- Skip commit entirely if `git status --short` shows no staged changes after `git add -u`
- If commit fails (e.g., pre-commit hook rejects), warn the user and continue to Step 4 — do not abort
- Use a recognizable `autowrap:` prefix so these commits are identifiable
- Post-commit hook (Task 4) automatically copies to Obsidian vault

### Step 4: Push to NotebookLM Brain
- Read Brain notebook ID from `memory/reference_brain_notebook.md`
- Write checkpoint summary to `$TEMP/autowrap-YYYY-MM-DD-HHMMSS.md` (Windows: `C:\Users\Claude_Anka\AppData\Local\Temp`)
- Push via `notebooklm source add`
- If auth fails or CLI missing, skip and print "NotebookLM: skipped (auth/CLI unavailable)" — local saves are the priority

### Step 5: Write Resume Prompt
Generate a paste-ready resume prompt and display it to the user:
```
> Read memory/project_next_session_scope.md. Continue from: <current task>.
> Context so far: <1-2 sentence summary>. Next: <what was about to happen>.
```
Also save this to `$TEMP/autowrap-resume-YYYY-MM-DD.md` (Windows: `C:\Users\Claude_Anka\AppData\Local\Temp`) so it survives session death.

## Differences from `/wrapup`

| Aspect | /wrapup | /autowrap |
|---|---|---|
| When | End of session | Mid-session, repeatable |
| Tone | Terminal — "here's everything" | Checkpoint — "saving progress" |
| Git | No commit behavior defined | Commits dirty files with `autowrap:` prefix |
| Resume prompt | Written to memory file | Displayed inline + saved to /tmp |
| NotebookLM | Required (warns on failure) | Optional (skips silently on failure) |
| Disruption | High — reviews entire session | Low — only scans since last checkpoint |

## File Location

`C:\Users\Claude_Anka\.claude\commands\autowrap.md`

This makes it available as `/autowrap` in any Claude Code session.

## CLAUDE.md Addition

Add to the project CLAUDE.md:
```
## Context Management
When context is getting heavy or you've been working for 2+ hours continuously,
invoke /autowrap to checkpoint progress before continuing. This saves memories,
commits dirty files, and writes a resume prompt. It's safe to invoke multiple times.
```

## Non-Requirements
- No automatic triggering — Claude self-monitors
- No context usage percentage calculation
- No destructive operations (no `git reset`, no file deletion)
- No interruption of in-progress tool calls — do NOT invoke autowrap while a plan step is actively executing
- Does not replace `/wrapup` — both can coexist

## Testing Plan
1. Invoke `/autowrap` in the current session
2. Verify: memory file created/updated, MEMORY.md index updated
3. Verify: git commit created with `autowrap:` prefix
4. Verify: Obsidian post-commit hook fired (file appears in `_claude_sessions/`)
5. Verify: resume prompt displayed and saved to /tmp
6. Verify: NotebookLM push attempted (success or graceful skip)
