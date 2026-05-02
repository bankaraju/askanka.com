# Hermes System-FAQ — Week 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up Hermes' first production skill on Contabo — a system-FAQ knowledge agent that answers in-depth questions (especially Karpathy / Lasso / BH-FDR ML methodology) using only the local askanka.com repo, and produce a graded Week-1 report card that drives Week-2 scope per the acceleration mechanic.

**Architecture:** `~/askanka.com` cloned to Contabo (read-only, weekly sync). Hand-curated `docs/faq/INDEX.md` maps topics → source files. Hermes skill at `~/.hermes/skills/system-faq/SKILL.md` reads INDEX → reads sources → composes answer with verbatim quotes + path citations. Python runner executes 30 baseline questions; Python grader uses Gemini 2.5 Flash to score per the 4-dimension rubric; report card committed to repo.

**Tech Stack:** Hermes Agent (already installed) → Ollama OpenAI-compat → `gemma4:26b`. Python 3.11 (already on Contabo venv). Gemini 2.5 Flash via existing `pipeline/config/llm_routing.json` credentials. Bash for repo sync + audit. systemd for weekly timer.

**Spec:** `docs/superpowers/specs/2026-05-02-hermes-system-faq-design.md`
**Baseline:** `docs/research/hermes_baseline/2026-05-02-baseline.md`

---

## File structure

| Path | Lives | Purpose |
|---|---|---|
| `pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh` | Repo | Pre-clone secrets audit |
| `pipeline/scripts/hermes/index_link_check.py` | Repo | INDEX path validator |
| `pipeline/scripts/hermes/run_faq_baseline.py` | Repo | 30-question batch runner |
| `pipeline/scripts/hermes/grade_faq_answers.py` | Repo | Gemini auto-grader |
| `pipeline/scripts/hermes/parse_citations.py` | Repo | Pure-function citation extractor (testable separately) |
| `pipeline/tests/hermes/test_parse_citations.py` | Repo | Citation parser tests |
| `pipeline/tests/hermes/test_grade_faq_answers.py` | Repo | Grader schema + scoring tests |
| `docs/faq/INDEX.md` | Repo | Curated topic → source map (5 tiers) |
| `docs/faq/baseline_questions.json` | Repo | 30 baseline Qs (immutable after first run) |
| `docs/research/hermes_pilot/report_cards/2026-05-XX-week-1.md` | Repo | First report card |
| `~/askanka.com/` | Contabo | Read-only clone (sync via systemd Sun 04:00 IST) |
| `~/.hermes/skills/system-faq/SKILL.md` | Contabo | Skill instructions |
| `~/.hermes/skills/system-faq/examples/` | Contabo | 5 worked examples (one per tier) |
| `~/.hermes/data/faq_runs/<date>/<q_id>.json` | Contabo | Per-question raw output |
| `/etc/systemd/system/anka-faq-sync.{service,timer}` | Contabo | Weekly repo pull |

---

## Task 1 — Secrets audit script (pre-clone)

**Files:**
- Create: `pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh`

**Why:** Before cloning askanka.com to Contabo, verify nothing tracked-by-git contains real keys/tokens. The repo IS already on GitHub (public mirror), so the concern is finding leaks already shipped — and stopping the clone if any are found.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Pre-VPS-clone secrets audit. Greps tracked files for likely secret patterns.
# Prints suspicious files; exits non-zero if any are found.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Patterns that almost certainly indicate a real secret if present in tracked files
PATTERNS=(
  'sk-[A-Za-z0-9]{20,}'           # OpenAI / Anthropic style
  'AIza[A-Za-z0-9_-]{35}'         # Google API key prefix
  'AKIA[0-9A-Z]{16}'              # AWS access key
  '-----BEGIN .* PRIVATE KEY-----'
  '"api_key"\s*:\s*"[A-Za-z0-9_-]{16,}"'
  '"access_token"\s*:\s*"[A-Za-z0-9_-]{16,}"'
)

SUSPECT=$(mktemp)
trap 'rm -f "$SUSPECT"' EXIT

for pat in "${PATTERNS[@]}"; do
  git grep -l -E "$pat" -- ':(exclude)*.example' ':(exclude)*.template' ':(exclude)docs/**' ':(exclude)*.md' >> "$SUSPECT" 2>/dev/null || true
done

# Also check for tracked .env-like files
git ls-files | grep -E '(^|/)\.env($|\.)' | grep -v '\.example$' | grep -v '\.template$' >> "$SUSPECT" || true

# De-dup
sort -u "$SUSPECT" -o "$SUSPECT"

if [[ -s "$SUSPECT" ]]; then
  echo "FAIL: tracked files matched secret patterns:"
  cat "$SUSPECT"
  exit 1
fi

echo "PASS: no tracked secrets detected"
```

- [ ] **Step 2: Make executable + run**

Run:
```bash
chmod +x pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh
pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh
```

Expected: `PASS: no tracked secrets detected`. If FAIL, **stop the plan**, surface findings to the user, fix (rotate key + git filter-repo or BFG), then re-run.

- [ ] **Step 3: Commit**

```bash
git add pipeline/scripts/hermes/audit_secrets_for_vps_clone.sh
git commit -m "feat(hermes): pre-VPS-clone secrets audit script

Greps tracked files for OpenAI/Google/AWS key patterns and tracked .env files.
Excludes *.example, *.template, *.md (docs may show example keys).
Exits non-zero on any match — gates the askanka.com → Contabo clone."
```

---

## Task 2 — Clone askanka.com to Contabo + weekly sync timer

**Files (Contabo, not in repo):**
- Create: `~/askanka.com/` (clone target)
- Create: `/etc/systemd/system/anka-faq-sync.service`
- Create: `/etc/systemd/system/anka-faq-sync.timer`

- [ ] **Step 1: Clone the repo**

Run from laptop:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "git clone https://github.com/<user>/askanka.com.git ~/askanka.com && \
   cd ~/askanka.com && git rev-parse HEAD"
```

Expected: clone succeeds; HEAD prints a SHA.

If the repo URL needs auth (private), substitute SSH form: `git@github.com:<user>/askanka.com.git` and ensure Contabo's SSH key is in GitHub deploy keys.

- [ ] **Step 2: Create the systemd service**

Run from laptop:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "sudo tee /etc/systemd/system/anka-faq-sync.service > /dev/null" <<'EOF'
[Unit]
Description=Pull askanka.com to ~/askanka.com (FAQ source corpus)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=anka
WorkingDirectory=/home/anka/askanka.com
ExecStart=/usr/bin/git pull --ff-only
StandardOutput=journal
StandardError=journal
EOF
```

- [ ] **Step 3: Create the systemd timer (Sunday 04:00 IST = Sunday 22:30 Saturday UTC if IST is system TZ; verify with `timedatectl`)**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "sudo tee /etc/systemd/system/anka-faq-sync.timer > /dev/null" <<'EOF'
[Unit]
Description=Weekly FAQ source corpus sync (Sunday 04:00 IST)

[Timer]
OnCalendar=Sun 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

- [ ] **Step 4: Enable + start + verify**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "sudo systemctl daemon-reload && \
   sudo systemctl enable --now anka-faq-sync.timer && \
   systemctl list-timers anka-faq-sync.timer"
```

Expected: timer listed with next-fire time on the upcoming Sunday. Verify TZ=IST via `timedatectl | grep 'Time zone'`.

- [ ] **Step 5: Update CLAUDE.md scheduled-task list + anka_inventory.json (per doc-sync mandate)**

Add to CLAUDE.md "VPS Execution Foundation" section:
```
- Sun 04:00 IST — AnkaFAQSync: weekly git pull of ~/askanka.com on VPS, FAQ source corpus for Hermes system-faq skill (info)
```

Add to `pipeline/config/anka_inventory.json` (if not present):
```json
{
  "task": "AnkaFAQSync",
  "tier": "info",
  "cadence_class": "weekly",
  "expected_outputs": ["/home/anka/askanka.com/.git/FETCH_HEAD"],
  "grace_multiplier": 2.0
}
```

Run:
```bash
git add CLAUDE.md pipeline/config/anka_inventory.json
git commit -m "docs(hermes): register AnkaFAQSync (Sun 04:00 IST repo pull on Contabo)

Weekly git pull of ~/askanka.com — feeds Hermes system-faq skill's INDEX
+ source corpus. systemd-only (no laptop counterpart). info tier."
```

---

## Task 3 — Author docs/faq/INDEX.md (all 5 tiers, ≥30 topics)

**Files:**
- Create: `docs/faq/INDEX.md`

This is hand-authoring; no test step. The INDEX is a curated map and IS the system-faq scaffold. Quality here gates everything downstream.

- [ ] **Step 1: Draft INDEX with all 5 tiers**

Create `docs/faq/INDEX.md` with this skeleton (fill in every topic with description + sources):

```markdown
# askanka.com FAQ Index

Curated map of system topics → canonical source documents. Every Hermes FAQ
answer must read at least one source from this index. If a question's topic
is not in this index, Hermes refuses to answer and asks for an INDEX update.

Maintenance: every commit that adds a new spec, hypothesis, or research doc
must update this INDEX in the same commit (per `feedback_doc_sync_mandate.md`).

---

## Tier 1 — ML Methods (Karpathy, Lasso, BH-FDR, Deflated Sharpe, etc.)

### Karpathy random search
- One-line: Cell-level pooled random search over a hyperparameter grid; pick
  the cell whose walk-forward CV Sharpe survives BH-FDR multiple-testing
  correction. Used in per-stock TA Lasso (H-2026-04-29-ta-karpathy-v1) and
  the Phase-C MR (H-2026-05-01-phase-c-mr-karpathy-v1, which FAILED
  registration when 0/448 cells passed).
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
  - docs/superpowers/specs/backtesting-specs.txt  §10.4
  - memory/project_h_2026_04_29_ta_karpathy.md

### Lasso L1 regularization
- One-line: L1-penalized logistic regression; sparsity-inducing, picks ~5–10
  features out of ~60 daily TA features per stock.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md  (pooled-weight variant)

### BH-FDR multiple-testing correction
- One-line: Benjamini-Hochberg false-discovery-rate adjustment of per-cell
  p-values; required gate before any cell is accepted as a registered
  hypothesis. The killer of H-2026-05-01-phase-c-mr-karpathy-v1.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt  §6
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md  §9

### Deflated Sharpe
- One-line: Sharpe ratio adjusted for the multiple-trials selection bias
  inherent in random-search hyperparameter optimization. Report-only at
  v1, gate-blocking at v2 when n≥100 days (per H-2026-04-29-ta-karpathy-v1
  spec v1.1).
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md  v1.1 amendment
  - docs/superpowers/specs/backtesting-specs.txt  §6

### Walk-forward cross-validation
- One-line: Time-respecting CV — train on past, test on future, slide
  window forward; never train on data later than test. Anti-leakage core.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt  §5
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md  §7 (4-fold WF)

### Permutation null
- One-line: Shuffle-the-labels resampling to build the null distribution
  of "no edge"; p-value = fraction of nulls beating the model's metric.
  Composed with BH-FDR to control family-wise FDR across cells.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt  §6
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md  §8

---

## Tier 2 — Architecture

### 8-layer Golden Goose pipeline
- One-line: ETF regime → Trust Scores → Spread Intelligence → Reverse Regime
  → Technicals+OI → Conviction → Shadow PnL → Track Record. ETF regime is
  the upstream brain — stale here breaks all downstream.
- Sources:
  - CLAUDE.md  §"Architecture: The Golden Goose Pipeline"
  - docs/SYSTEM_OPERATIONS_MANUAL.md
  - memory/project_golden_goose.md

### ETF regime engine (v3-CURATED-30)
- One-line: 28 global ETFs, ML-optimized weights, 5 regimes (RISK-ON,
  CAUTION, NEUTRAL, RISK-OFF, CRISIS). v3+CURATED-30 won the 2026-04-26
  cycle-3 evaluation with +1.83pp edge over baseline; v2-faithful is dead.
- Sources:
  - memory/project_etf_v3_failed_2026_04_26.md
  - memory/project_etf_regime_engine.md
  - docs/SYSTEM_OPERATIONS_MANUAL.md  §"ETF Regime"

### OPUS ANKA Trust Scores
- One-line: Management-credibility grades (A+, A, B+, B, C, D, F) for the
  213 F&O universe. 207/210 scored as of 2026-04-11 Haiku fallback run; 3
  data-constrained.
- Sources:
  - memory/project_opus_anka.md
  - memory/project_opus_anka_iteration.md
  - memory/project_trust_score_coverage.md

### Spread Intelligence Engine
- One-line: 5-layer regime-gated pair-trade decision engine — sector rotation,
  scorecard alpha modifier, technicals confirmation, news adjustment,
  Karpathy per-spread sizing.
- Sources:
  - memory/project_spread_intelligence.md
  - docs/SYSTEM_OPERATIONS_MANUAL.md  §"Spread Intelligence"

### Reverse Regime Phase A/B/C
- One-line: A = playbook of regime-transition patterns; B = daily regime-
  conditional ranker; C = intraday correlation-break detection (LAG /
  OVERSHOOT routing per 2026-04-23 audit, only LAG goes live after kill).
- Sources:
  - memory/project_reverse_regime_analysis.md
  - memory/project_phase_c_follow_vs_fade_audit.md
  - memory/project_phase_c_kill_criteria.md

### Theme Detector v1
- One-line: Weekly Trendlyne snapshot → 12-theme lifecycle frames (B3 drift
  trajectory at 13w, FALSE_POSITIVE detection at 26w). Laptop-only;
  shadow-mode operational, NOT yet citable as evidence per data-policy §21.
- Sources:
  - docs/superpowers/specs/2026-05-01-theme-detector-design.md
  - docs/superpowers/plans/2026-05-01-theme-detector-elevation-plan.md

---

## Tier 3 — Operations

### 80+ scheduled tasks (clockwork)
- One-line: Windows Task Scheduler (laptop) + VPS systemd timers (Contabo)
  fire ~80 daily/weekly/intraday tasks. Canonical inventory in
  `pipeline/config/anka_inventory.json`; CLAUDE.md "Clockwork Schedule"
  is the human-readable map.
- Sources:
  - CLAUDE.md  §"Clockwork Schedule (IST)"
  - pipeline/config/anka_inventory.json
  - docs/SYSTEM_OPERATIONS_MANUAL.md

### Data-freshness watchdog
- One-line: Reads anka_inventory.json + checks output-file mtimes against
  per-task grace_multiplier; alerts via Telegram on stale critical tasks.
- Sources:
  - memory/project_data_freshness_watchdog.md
  - pipeline/watchdog.py

### 14:30 IST new-signal cutoff
- One-line: No live engine OPENs new positions after 14:30 IST. Mechanical
  TIME_STOPs run at 14:30 — anything opened later has under 60 min before
  forced close. Enforced at source in run_signals.py +
  break_signal_generator.py + arcbe_signal_generator.py.
- Sources:
  - CLAUDE.md  §"14:30 IST New-Signal Cutoff"
  - memory/feedback_1430_ist_signal_cutoff.md

### Kill-switch (strategy-pattern gate)
- One-line: Pre-commit hook + CI workflow refuse to merge a new
  `*_strategy.py`/`*_signal_generator.py`/`*_backtest.py`/etc. unless the
  same commit registers it in hypothesis-registry.jsonl. Patterns canonical
  at `pipeline/scripts/hooks/strategy_patterns.txt`.
- Sources:
  - CLAUDE.md  §"Kill Switch: No Un-Registered Trading Rules"
  - pipeline/scripts/hooks/strategy_patterns.txt

### anka_inventory.json
- One-line: Source-of-truth registry of every Anka* scheduled task with
  tier, cadence_class, expected outputs, grace_multiplier. Watchdog reads
  this; missing entry → ORPHAN_TASK alert.
- Sources:
  - CLAUDE.md  §"Scheduler Inventory (Canonical)"
  - pipeline/config/anka_inventory.json

### VPS execution foundation
- One-line: Contabo VPS (anka@185.182.8.107) runs all heavy/sensitive
  scheduled tasks via systemd; laptop holds context (Obsidian, memory,
  PDFs). Hardened 2026-04-25 (root disabled, ufw, fail2ban, IST tz).
- Sources:
  - memory/reference_contabo_vps.md
  - memory/project_vps_phase1.md
  - memory/feedback_laptop_context_vps_execution.md

---

## Tier 4 — Active hypotheses

### H-2026-04-25-002 (etf-stock-tail-classifier)
- Status: FAILED 2026-04-26 on §9A FRAGILE (0/6) + §9B.1 margin -0.0090 +
  §11B. Single-touch consumed; A1.1–A1.5 amendments in force.
- Sources:
  - memory/project_etf_stock_tail_h_2026_04_25_002.md
  - docs/superpowers/specs/2026-04-25-etf-stock-tail-classifier-design.md
  - docs/superpowers/hypothesis-registry.jsonl

### H-2026-04-29-ta-karpathy-v1 (per-stock TA Lasso, top-10 NIFTY)
- Status: Holdout 2026-04-29 → 2026-05-28. v1.1 Deflated Sharpe report-only
  at v1, gate-blocking at v2 when N≥100 days. Honest expectation: 0–3
  stocks qualify.
- Sources:
  - docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
  - memory/project_h_2026_04_29_ta_karpathy.md

### H-2026-04-29-intraday-data-driven-v1 (twin: stocks + indices)
- Status: Holdout 2026-04-29 → 2026-06-27, verdict by 2026-07-04. On pass:
  kills news-driven framework (V2 cross-class long-short pairing spec).
  On fail: news-driven incumbent stays running.
- Sources:
  - docs/superpowers/specs/2026-04-29-data-driven-intraday-framework-design.md
  - docs/superpowers/plans/2026-04-29-intraday-v1-framework.md

### H-2026-04-27-003 SECRSI (sector RS intraday pair)
- Status: PRE_REGISTERED 2026-04-27; full 5y 5m replay 2026-05-01 STRONG
  NEGATIVE PRIOR (mean +0.68 bps vs ≥+30 needed; hit 50.3% vs ≥55%;
  Sharpe 0.26 vs ≥1.0). Holdout 2026-04-28 → 2026-07-31 untouched per §10.4.
- Sources:
  - docs/superpowers/specs/2026-04-27-intraday-sector-rs-pair-design.md
  - memory/project_secrsi_h_2026_04_27_003.md

### H-2026-05-01-EARNINGS-DRIFT-LONG-v1
- Status: PRE_REGISTERED 2026-05-01. Quad-filter LONG (vol_z, short_mom,
  realized_vol, regime). Single-touch holdout 2026-05-04 → 2026-08-01,
  auto-extend until n≥20 OR 2026-10-31. Tasks pending registration.
- Sources:
  - docs/superpowers/specs/2026-05-01-earnings-drift-long-v1-design.md
  - docs/superpowers/specs/2026-05-01-earnings-data-source-audit.md

### H-2026-05-01-phase-c-mr-karpathy-v1
- Status: REGISTRATION_FAIL 2026-05-01 — 0/448 cells passed BH-FDR (best
  in-sample Sharpe 3.44 with p=0.30, n=70 too thin). Predecessor LAG-routed
  Phase C stays live. Re-attempt requires fresh registration.
- Sources:
  - docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md

---

## Tier 5 — Standards

### backtesting-specs.txt
- One-line: 16-section governance spec for every backtest and strategy
  launch. §0 (no waivers), §6 (statistical rigor), §9 (pass criteria),
  §9A (fragility), §9B (margin), §10.4 (no parameter retries on same
  registration).
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt

### anka_data_validation_policy_global_standard.md
- One-line: 26-section data-governance policy. Every dataset must be
  registered (§6), have schema contract (§8), pass cleanliness gates (§9),
  declare adjustment mode (§10), be PIT-correct (§11), have contamination
  map (§14). §21 binds dataset acceptance to model approval ladder.
- Sources:
  - docs/superpowers/specs/anka_data_validation_policy_global_standard.md
  - CLAUDE.md  §"Data Validation Gate (CRITICAL)"

### Doc-sync mandate
- One-line: Every code change updates ALL of: code, SYSTEM_OPERATIONS_MANUAL,
  anka_inventory.json (if scheduled), CLAUDE.md (if architecture), memory.
  Same commit, no exceptions.
- Sources:
  - CLAUDE.md  §"Documentation Sync Rule (CRITICAL)"
  - memory/feedback_doc_sync_mandate.md

### No-hallucination mandate
- One-line: Absolute rule — slow and correct beats fast and wrong. Zero
  fabricated numbers; failed lookups print "—", never a guessed value.
- Sources:
  - memory/feedback_no_hallucination_mandate.md

### Single-touch holdout (§10.4 strict)
- One-line: Once a holdout window opens, no parameter changes, no re-runs
  on the same registration. Failure → fresh hypothesis-registry row, longer
  training window, new holdout.
- Sources:
  - docs/superpowers/specs/backtesting-specs.txt  §10.4
  - memory/reference_backtest_standards.md

### Subscriber language (plain English)
- One-line: No jargon, no internal numbering. "n=10" → "worked 7 of 10".
- Sources:
  - memory/feedback_subscriber_language.md
  - memory/feedback_no_hallucination_mandate.md
```

- [ ] **Step 2: Verify INDEX has ≥ 30 topics across 5 tiers**

Run:
```bash
grep -c '^### ' docs/faq/INDEX.md
```

Expected: count ≥ 30.

- [ ] **Step 3: Commit**

```bash
git add docs/faq/INDEX.md
git commit -m "docs(faq): author INDEX.md — 5 tiers, ≥30 topics

Curated topic → source map for Hermes system-faq skill. Tier 1 (ML methods)
deepest per user emphasis on Karpathy/Lasso/BH-FDR. Every topic has a
one-line description + 1-3 canonical source files.

Maintenance follows doc-sync mandate: any new spec/research/hypothesis
ships with INDEX update in same commit."
```

---

## Task 4 — INDEX link-check script

**Files:**
- Create: `pipeline/scripts/hermes/index_link_check.py`

- [ ] **Step 1: Write the link-check script**

```python
#!/usr/bin/env python3
"""Validate every source path in docs/faq/INDEX.md resolves to an existing file.

Exit 0 if all OK; exit 1 if any path is broken (with list).
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INDEX = REPO_ROOT / "docs" / "faq" / "INDEX.md"

# Match lines like:  "  - docs/foo/bar.md  §X"  or  "  - memory/foo.md"
SOURCE_RE = re.compile(r'^\s*-\s+([\w./_-]+\.(?:md|txt|jsonl|json|py))(?:\s+§[\w.]+)?\s*$')

def main() -> int:
    if not INDEX.exists():
        print(f"FAIL: {INDEX} not found", file=sys.stderr)
        return 1

    broken: list[tuple[int, str]] = []
    in_sources_block = False

    for lineno, line in enumerate(INDEX.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("- Sources:"):
            in_sources_block = True
            continue
        if line.strip().startswith("###") or line.strip().startswith("##"):
            in_sources_block = False
            continue
        if not in_sources_block:
            continue

        m = SOURCE_RE.match(line)
        if not m:
            continue
        path = REPO_ROOT / m.group(1)
        if not path.exists():
            broken.append((lineno, m.group(1)))

    if broken:
        print(f"FAIL: {len(broken)} broken source path(s) in INDEX.md:")
        for lineno, path in broken:
            print(f"  L{lineno}: {path}")
        return 1
    print(f"PASS: all source paths in {INDEX} resolve")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the INDEX written in Task 3**

Run:
```bash
python pipeline/scripts/hermes/index_link_check.py
```

Expected: `PASS: all source paths in ... resolve`. If FAIL, fix broken paths in INDEX.md (typo, renamed file) and re-run.

- [ ] **Step 3: Commit**

```bash
git add pipeline/scripts/hermes/index_link_check.py
git commit -m "feat(faq): INDEX link-checker — validates every source path resolves

Exits non-zero on any broken link. Run after every INDEX edit; will be
wired into pre-commit + Sun 04:00 IST sync alongside git pull."
```

---

## Task 5 — Author SKILL.md + 5 worked examples on Contabo

**Files (Contabo, not in repo):**
- Create: `~/.hermes/skills/system-faq/SKILL.md`
- Create: `~/.hermes/skills/system-faq/examples/tier1_karpathy.md`
- Create: `~/.hermes/skills/system-faq/examples/tier2_etf_regime.md`
- Create: `~/.hermes/skills/system-faq/examples/tier3_1430_cutoff.md`
- Create: `~/.hermes/skills/system-faq/examples/tier4_h_2026_04_29_ta_karpathy.md`
- Create: `~/.hermes/skills/system-faq/examples/tier5_backtesting_specs.md`

- [ ] **Step 1: Create skill directory + SKILL.md**

Run from laptop:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "mkdir -p ~/.hermes/skills/system-faq/examples && \
   cat > ~/.hermes/skills/system-faq/SKILL.md" <<'EOF'
---
name: system-faq
description: Answer questions about the askanka.com pipeline — architecture, ML
  methods, operations, active hypotheses, governance — using ONLY content from
  the local repo at ~/askanka.com. Cite source files. Refuse to answer outside
  indexed scope.
---

# System FAQ

You are the system-FAQ agent for askanka.com. Your job is to answer questions
about the pipeline using ONLY content from `~/askanka.com/`.

## Procedure (must follow exactly)

1. Read `~/askanka.com/docs/faq/INDEX.md`.
2. Match the user's question against INDEX topics. Use keyword + semantic matching.
3. If matched: read 1–3 source files listed for that topic.
4. Compose your answer with these requirements:
   - Begin with a one-sentence direct answer.
   - Then provide depth using **at least one verbatim quote** from a cited source.
     Format each quote as `> "..."` followed by `— <source path>` on the next line.
   - Tier 1 (ML methods) requires **AT LEAST TWO** verbatim quotes from different
     sources.
   - End with a "Sources:" section listing every file you read.
5. If no INDEX match: respond with one sentence — "This is outside the current FAQ
   index — escalate to Claude. Suggest adding it to docs/faq/INDEX.md." Do not
   attempt to answer from general knowledge.

## Hard rules

- NEVER state a fact about the system that you cannot back with a verbatim quote
  from a source file in `~/askanka.com/`.
- NEVER use general training-data knowledge to fill gaps. If the source doesn't
  say it, you don't know it.
- NEVER show your reasoning, planning, or self-correction in the final output.
  Final answer only.
- ALWAYS cite the source path. Relative paths (e.g.
  `docs/superpowers/specs/foo.md`) are acceptable.
- If multiple source files contradict each other, surface the contradiction
  explicitly and cite both.

## Style

- Direct, technical, no preamble like "Great question!".
- Match the depth of the source. ML-method answers should be detailed; operations
  answers can be one paragraph.
- Plain English over jargon when both work equally well.
EOF
```

- [ ] **Step 2: Author 5 worked examples (one per tier)**

Each example shows a sample question, the SKILL-compliant answer with quotes + citations. These prime Hermes by demonstrating the expected output shape.

For brevity, here is the Tier 1 example; author the other 4 in the same form:

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cat > ~/.hermes/skills/system-faq/examples/tier1_karpathy.md" <<'EOF'
**Q:** What is Karpathy random search and how is it used in H-2026-04-29-ta-karpathy-v1?

**A:** Karpathy random search is a cell-level pooled hyperparameter search where each cell
is a (window × feature_subset × regularization) combination, scored by walk-forward
cross-validation Sharpe and gated by BH-FDR multiple-testing correction.

> "Per-stock Lasso L1 logistic regression on ~60 daily TA features, 4-fold
> walk-forward + BH-FDR permutation null + qualifier gate."
> — docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md

> "the Karpathy 28×4×4=448-cell grid was run on the 2021-05 → 2024-04 training
> window on VPS on 2026-05-01: 0 of 448 cells passed BH-FDR"
> — docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md

In H-2026-04-29-ta-karpathy-v1 the search is per-stock across 10 frozen NIFTY
names; honest expectation is 0–3 stocks qualify after BH-FDR. The same engine
applied to Phase-C MR (H-2026-05-01) failed registration when 0/448 cells
survived — n=70 in-sample candidates was too thin to reject the null.

Sources:
- docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md
- docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
EOF
```

Repeat for tier2/3/4/5 (each one a representative question + SKILL-compliant answer).

- [ ] **Step 3: Verify Hermes registers the skill**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "~/.local/bin/hermes skills list 2>&1 | grep -i system-faq"
```

Expected: `system-faq` appears in the list. If absent, inspect `~/.hermes/logs/agent.log` for skill-load errors.

- [ ] **Step 4: Hand-test 1 question per tier (sanity)**

Run from laptop:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/hermes-agent && timeout 600 ~/.local/bin/hermes -z 'What is BH-FDR and why did H-2026-05-01-phase-c-mr-karpathy-v1 fail it?' --skills system-faq 2>&1"
```

Expected: an answer that (a) cites `2026-05-01-phase-c-mr-karpathy-v1-design.md` and/or `backtesting-specs.txt`, (b) includes ≥ 1 verbatim quote in `> "..."` form, (c) does not invent details.

If the answer hallucinates or skips citations, **stop here**, patch SKILL.md, re-run. Do NOT proceed to author 30 questions until 5/5 hand-tests are clean.

---

## Task 6 — Author 30 baseline questions JSON

**Files:**
- Create: `docs/faq/baseline_questions.json`

- [ ] **Step 1: Author all 30 questions, 6 per tier**

Create `docs/faq/baseline_questions.json`:

```json
{
  "schema_version": "1.0",
  "frozen_at": "2026-05-02",
  "note": "IMMUTABLE after first run. Do not edit. Future report cards compare against this exact set.",
  "questions": [
    {"id": "T1Q1", "tier": 1, "topic": "Karpathy random search", "q": "What is Karpathy random search and how is it used in H-2026-04-29-ta-karpathy-v1?"},
    {"id": "T1Q2", "tier": 1, "topic": "Lasso L1", "q": "Why does H-2026-04-29-ta-karpathy-v1 use Lasso L1 logistic regression instead of OLS, and what are its inputs?"},
    {"id": "T1Q3", "tier": 1, "topic": "BH-FDR", "q": "Define Benjamini-Hochberg FDR correction and explain the concrete failure mode that killed H-2026-05-01-phase-c-mr-karpathy-v1."},
    {"id": "T1Q4", "tier": 1, "topic": "Deflated Sharpe", "q": "What is Deflated Sharpe, and at what point in the H-2026-04-29-ta-karpathy-v1 lifecycle does it become gate-blocking?"},
    {"id": "T1Q5", "tier": 1, "topic": "Walk-forward CV", "q": "Describe the 4-fold walk-forward cross-validation used in H-2026-04-29-ta-karpathy-v1 and explain why time-respecting CV is required."},
    {"id": "T1Q6", "tier": 1, "topic": "Permutation null", "q": "What is a permutation null, and how does it compose with BH-FDR in the qualifier-gate stack?"},

    {"id": "T2Q1", "tier": 2, "topic": "Golden Goose", "q": "List the 8 layers of the Golden Goose pipeline in order and explain why ETF regime is the upstream brain."},
    {"id": "T2Q2", "tier": 2, "topic": "ETF regime v3-CURATED-30", "q": "What is v3-CURATED-30, what edge did it show in cycle-3 evaluation 2026-04-26, and why is v2-faithful dead?"},
    {"id": "T2Q3", "tier": 2, "topic": "OPUS ANKA Trust Scores", "q": "What does an OPUS ANKA Trust Score grade and how complete is coverage of the 213 F&O universe?"},
    {"id": "T2Q4", "tier": 2, "topic": "Spread Intelligence", "q": "Name the 5 layers of the Spread Intelligence Engine and explain how regime gates the spread set."},
    {"id": "T2Q5", "tier": 2, "topic": "Reverse Regime A/B/C", "q": "Distinguish Reverse Regime Phase A, B, and C — what does each produce, and what was the LAG vs OVERSHOOT decision in the 2026-04-23 audit?"},
    {"id": "T2Q6", "tier": 2, "topic": "Theme Detector v1", "q": "What does the Theme Detector v1 produce weekly, and why is it not yet citable as evidence per the data-validation policy §21?"},

    {"id": "T3Q1", "tier": 3, "topic": "Clockwork", "q": "Where is the canonical inventory of Anka* scheduled tasks, and what fields does it record per task?"},
    {"id": "T3Q2", "tier": 3, "topic": "Watchdog", "q": "How does the data-freshness watchdog detect stale tasks, and what does it do on a critical-tier stall?"},
    {"id": "T3Q3", "tier": 3, "topic": "14:30 cutoff", "q": "Why is no new live shadow position opened after 14:30 IST, and which three engines enforce it at the source?"},
    {"id": "T3Q4", "tier": 3, "topic": "Kill-switch", "q": "What does the kill-switch / strategy-pattern gate enforce, and where is the regex of guarded file patterns?"},
    {"id": "T3Q5", "tier": 3, "topic": "anka_inventory.json", "q": "What happens if a new Anka* scheduled task is added without an entry in anka_inventory.json?"},
    {"id": "T3Q6", "tier": 3, "topic": "VPS execution foundation", "q": "What is the architectural split between the laptop and the Contabo VPS, and what was hardened on 2026-04-25?"},

    {"id": "T4Q1", "tier": 4, "topic": "H-2026-04-25-002", "q": "Why did H-2026-04-25-002 (etf-stock-tail-classifier) fail on 2026-04-26, citing the specific §-references from the verdict?"},
    {"id": "T4Q2", "tier": 4, "topic": "H-2026-04-29-ta-karpathy-v1", "q": "What is the holdout window for H-2026-04-29-ta-karpathy-v1, and what is the honest expectation for stocks that qualify?"},
    {"id": "T4Q3", "tier": 4, "topic": "H-2026-04-29-intraday-data-driven-v1", "q": "What does H-2026-04-29-intraday-data-driven-v1 do on PASS vs FAIL of its §9/§9A/§9B verdict?"},
    {"id": "T4Q4", "tier": 4, "topic": "H-2026-04-27-003 SECRSI", "q": "Why does H-2026-04-27-003 SECRSI carry a STRONG NEGATIVE PRIOR after the 2026-05-01 5y replay, and why is its holdout still untouched?"},
    {"id": "T4Q5", "tier": 4, "topic": "H-2026-05-01-EARNINGS-DRIFT-LONG-v1", "q": "What is the quad-filter for H-2026-05-01-EARNINGS-DRIFT-LONG-v1, and what auto-extension rule applies if the holdout doesn't reach n≥20?"},
    {"id": "T4Q6", "tier": 4, "topic": "H-2026-05-01-phase-c-mr-karpathy-v1", "q": "Why is H-2026-05-01-phase-c-mr-karpathy-v1 marked REGISTRATION_FAIL, and what would a re-attempt require per backtesting-specs §10.4?"},

    {"id": "T5Q1", "tier": 5, "topic": "backtesting-specs §0", "q": "What does §0 of backtesting-specs.txt say about waivers, and why is it load-bearing?"},
    {"id": "T5Q2", "tier": 5, "topic": "Single-touch holdout §10.4", "q": "Explain the single-touch holdout rule (§10.4) — what does 'no parameter changes during holdout' mean concretely, and what triggers a fresh registration?"},
    {"id": "T5Q3", "tier": 5, "topic": "Data-validation §21", "q": "What does §21 of the data-validation policy bind together, and how does it gate model approval?"},
    {"id": "T5Q4", "tier": 5, "topic": "Doc-sync mandate", "q": "List the artifacts that must update in the same commit when the system changes, per the doc-sync mandate."},
    {"id": "T5Q5", "tier": 5, "topic": "No-hallucination mandate", "q": "What is the no-hallucination mandate, and what is the operational behavior when a number cannot be looked up?"},
    {"id": "T5Q6", "tier": 5, "topic": "Subscriber language", "q": "How should 'n=10, 7 wins' be phrased to a subscriber per the plain-English mandate?"}
  ]
}
```

- [ ] **Step 2: Validate JSON parses + has 30 entries**

Run:
```bash
python -c "
import json
d = json.load(open('docs/faq/baseline_questions.json'))
qs = d['questions']
print('count:', len(qs))
assert len(qs) == 30
for tier in (1,2,3,4,5):
    n = sum(1 for q in qs if q['tier'] == tier)
    print(f'tier {tier}: {n} questions')
    assert n == 6
print('OK')
"
```

Expected: `OK` after printing 30 / 6 each tier.

- [ ] **Step 3: Commit**

```bash
git add docs/faq/baseline_questions.json
git commit -m "docs(faq): freeze 30 baseline questions across 5 tiers

IMMUTABLE after first run. Tier 1 (ML methods, 6 deep questions on Karpathy /
Lasso / BH-FDR / Deflated Sharpe / walk-forward CV / permutation null) is the
hardest tier and gates the Week-1 verdict. Tier 5 (governance) checks the
agent can quote standards correctly.

Future report cards compare against this exact JSON. Schema-versioned
to surface accidental edits."
```

---

## Task 7 — Citation parser (TDD)

**Files:**
- Create: `pipeline/scripts/hermes/parse_citations.py`
- Test: `pipeline/tests/hermes/test_parse_citations.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/hermes/test_parse_citations.py
from pipeline.scripts.hermes.parse_citations import extract_citations, extract_quotes

def test_extracts_inline_citations():
    answer = """BH-FDR is a multiple-testing correction.

> "0 of 448 cells passed BH-FDR"
— docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md

Sources:
- docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
- docs/superpowers/specs/backtesting-specs.txt
"""
    cites = extract_citations(answer)
    assert "docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md" in cites
    assert "docs/superpowers/specs/backtesting-specs.txt" in cites
    assert len(cites) == 2  # de-duped


def test_extracts_quotes():
    answer = '''
> "Per-stock Lasso L1 logistic regression on ~60 daily TA features"
— docs/superpowers/specs/2026-04-29-ta-karpathy-v1-design.md

> "0 of 448 cells passed BH-FDR"
— docs/superpowers/specs/2026-05-01-phase-c-mr-karpathy-v1-design.md
'''
    quotes = extract_quotes(answer)
    assert len(quotes) == 2
    assert quotes[0]["text"].startswith("Per-stock Lasso L1")
    assert quotes[0]["source"].endswith("ta-karpathy-v1-design.md")


def test_no_citations_returns_empty():
    cites = extract_citations("just a plain answer with no sources")
    assert cites == []


def test_quote_without_dash_source_is_skipped():
    """A bare blockquote without a `— path` line is not a SKILL-compliant quote."""
    answer = '> "hello world"\n\nno source line'
    quotes = extract_quotes(answer)
    assert quotes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python -m pytest pipeline/tests/hermes/test_parse_citations.py -v
```

Expected: `ModuleNotFoundError` or `AttributeError` (not implemented yet).

- [ ] **Step 3: Implement the parser**

```python
# pipeline/scripts/hermes/parse_citations.py
"""Extract citations and verbatim-quote blocks from a SKILL-compliant answer.

A SKILL-compliant quote looks like:
    > "the quoted text"
    — docs/path/to/source.md

A SKILL-compliant Sources section looks like:
    Sources:
    - docs/path/one.md
    - docs/path/two.md
"""
from __future__ import annotations
import re

QUOTE_RE = re.compile(
    r'^\s*>\s*"(?P<text>.+?)"\s*\n\s*[—-]\s*(?P<source>[\w./_-]+\.(?:md|txt|jsonl|json|py))',
    re.MULTILINE,
)
SOURCE_LINE_RE = re.compile(
    r'^\s*-\s+([\w./_-]+\.(?:md|txt|jsonl|json|py))(?:\s+§[\w.]+)?\s*$',
    re.MULTILINE,
)


def extract_quotes(answer: str) -> list[dict]:
    """Return list of {text, source} for every SKILL-compliant quote block."""
    return [
        {"text": m.group("text"), "source": m.group("source")}
        for m in QUOTE_RE.finditer(answer)
    ]


def extract_citations(answer: str) -> list[str]:
    """Return de-duped, order-preserving list of all cited source paths.

    Includes paths from blockquote `— path` lines AND from the Sources: bullet list.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in QUOTE_RE.finditer(answer):
        path = m.group("source")
        if path not in seen:
            seen.add(path)
            out.append(path)
    in_sources = False
    for line in answer.splitlines():
        if line.strip().lower().startswith("sources:"):
            in_sources = True
            continue
        if in_sources:
            sm = SOURCE_LINE_RE.match(line)
            if sm:
                p = sm.group(1)
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            elif line.strip() == "":
                continue
            else:
                # leaving the sources block on first non-bullet, non-blank line
                in_sources = False
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest pipeline/tests/hermes/test_parse_citations.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/hermes/parse_citations.py pipeline/tests/hermes/test_parse_citations.py
git commit -m "feat(faq): citation + quote parser for SKILL-compliant Hermes answers

extract_quotes -> [{text, source}, ...] from SKILL-format blockquote+dash-source.
extract_citations -> de-duped path list from quotes + Sources: bullets.

4 tests cover: inline cites, quote extraction, empty input, malformed quote
(missing source line is correctly skipped — important for grading)."
```

---

## Task 8 — Runner script (Python, runs on Contabo via SSH from laptop)

**Files:**
- Create: `pipeline/scripts/hermes/run_faq_baseline.py`

This script runs LOCALLY on Contabo. We invoke it from the laptop via SSH.

- [ ] **Step 1: Write the runner**

```python
#!/usr/bin/env python3
"""Run all 30 baseline FAQ questions through Hermes on Contabo.

Reads:  ~/askanka.com/docs/faq/baseline_questions.json
Writes: ~/.hermes/data/faq_runs/<YYYY-MM-DD>/<question_id>.json
        + ~/.hermes/data/faq_runs/<YYYY-MM-DD>/_summary.json

Each per-question JSON has: id, tier, topic, q, answer_text, citations,
quotes, latency_seconds, hermes_exit_code, started_at, ended_at.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "askanka.com"
QUESTIONS = REPO / "docs" / "faq" / "baseline_questions.json"
HERMES = Path.home() / ".local" / "bin" / "hermes"
OUT_BASE = Path.home() / ".hermes" / "data" / "faq_runs"

# Re-use the parse_citations module shipped in the repo
sys.path.insert(0, str(REPO / "pipeline" / "scripts" / "hermes"))
from parse_citations import extract_citations, extract_quotes  # noqa: E402


def run_one(question: dict, out_dir: Path) -> dict:
    qid = question["id"]
    out_path = out_dir / f"{qid}.json"
    if out_path.exists():
        print(f"[{qid}] already done — skipping")
        return json.loads(out_path.read_text())

    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()
    print(f"[{qid}] tier={question['tier']} starting at {started_iso}")

    try:
        proc = subprocess.run(
            [str(HERMES), "-z", question["q"], "--skills", "system-faq"],
            capture_output=True, text=True, timeout=900,  # 15-min ceiling per question
        )
        exit_code = proc.returncode
        answer = (proc.stdout or "") + (proc.stderr if proc.returncode != 0 else "")
    except subprocess.TimeoutExpired:
        exit_code = -1
        answer = "TIMEOUT after 900s"

    latency = time.time() - started
    cites = extract_citations(answer)
    quotes = extract_quotes(answer)

    record = {
        "id": qid,
        "tier": question["tier"],
        "topic": question["topic"],
        "q": question["q"],
        "answer_text": answer,
        "citations": cites,
        "quotes": quotes,
        "n_quotes": len(quotes),
        "latency_seconds": round(latency, 1),
        "hermes_exit_code": exit_code,
        "started_at": started_iso,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(record, indent=2))
    print(f"[{qid}] done in {latency:.0f}s, {len(cites)} citations, {len(quotes)} quotes")
    return record


def main() -> int:
    data = json.loads(QUESTIONS.read_text())
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = OUT_BASE / today
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {"date": today, "results": []}
    for q in data["questions"]:
        rec = run_one(q, out_dir)
        summary["results"].append({
            "id": rec["id"], "tier": rec["tier"],
            "latency_seconds": rec["latency_seconds"],
            "n_citations": len(rec["citations"]),
            "n_quotes": rec["n_quotes"],
            "exit_code": rec["hermes_exit_code"],
        })

    (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"DONE: 30 questions written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Push to repo + sync to Contabo**

Run from laptop:
```bash
git add pipeline/scripts/hermes/run_faq_baseline.py
git commit -m "feat(faq): baseline runner — 30 Qs through Hermes, captures citations+latency

Resumable (skips question_id JSONs already written), 15-min timeout per Q,
writes per-Q JSON + _summary.json. Reuses parse_citations module from same
script dir. Idempotent — safe to re-run mid-batch if interrupted."
```

Then sync to Contabo (Sun 04:00 IST timer hasn't fired yet, so manual pull):
```bash
git push  # to whatever branch you're on
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && git fetch && git checkout <branch> && git pull --ff-only"
```

- [ ] **Step 3: Smoke-test runner against question T1Q3 only**

Run from laptop:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && python3 -c \"
import json, subprocess, sys
sys.path.insert(0, 'pipeline/scripts/hermes')
from run_faq_baseline import run_one
qs = json.load(open('docs/faq/baseline_questions.json'))['questions']
q = next(q for q in qs if q['id'] == 'T1Q3')
import os
from pathlib import Path
out = Path.home() / '.hermes' / 'data' / 'faq_runs' / 'smoke'
out.mkdir(parents=True, exist_ok=True)
rec = run_one(q, out)
print('citations:', rec['citations'])
print('n_quotes:', rec['n_quotes'])
print('latency:', rec['latency_seconds'])
\""
```

Expected: a citation list including `2026-05-01-phase-c-mr-karpathy-v1-design.md` and `backtesting-specs.txt`, n_quotes ≥ 2 (Tier 1 requirement), latency 200–600 s. If n_quotes == 0, **stop**, patch SKILL.md to enforce quote requirement, re-test.

- [ ] **Step 4: Run the full 30-question batch (overnight)**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && nohup python3 pipeline/scripts/hermes/run_faq_baseline.py > /tmp/faq_runner.log 2>&1 &"
```

Wall-clock ETA: 30 × ~290 s = ~145 min. Leave it overnight.

- [ ] **Step 5: Verify completion**

Run from laptop the next morning:
```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "ls ~/.hermes/data/faq_runs/$(date -I)/ | wc -l && \
   tail -5 /tmp/faq_runner.log"
```

Expected: 31 files (30 question JSONs + `_summary.json`), log ends with `DONE`. If fewer, identify which questions failed and re-run runner (resumable).

---

## Task 9 — Auto-grader script (TDD)

**Files:**
- Create: `pipeline/scripts/hermes/grade_faq_answers.py`
- Test: `pipeline/tests/hermes/test_grade_faq_answers.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/hermes/test_grade_faq_answers.py
from pipeline.scripts.hermes.grade_faq_answers import (
    build_grader_prompt,
    parse_grader_response,
    score_record,
)

def test_grader_prompt_includes_question_and_answer():
    record = {
        "id": "T1Q3", "tier": 1, "topic": "BH-FDR",
        "q": "What is BH-FDR?",
        "answer_text": "BH-FDR is...",
        "citations": ["docs/superpowers/specs/backtesting-specs.txt"],
        "quotes": [{"text": "0/448 passed", "source": "x.md"}],
    }
    sources_content = {"docs/superpowers/specs/backtesting-specs.txt": "section §6 BH-FDR..."}
    prompt = build_grader_prompt(record, sources_content)
    assert "What is BH-FDR?" in prompt
    assert "BH-FDR is..." in prompt
    assert "section §6" in prompt
    assert "JSON" in prompt  # asks for JSON output


def test_parse_grader_response_extracts_scores():
    raw = """Some preamble.
{"citation": 1, "faithfulness": 2, "completeness": 1, "no_hallucination": 1,
 "notes": "Tier 1 needed 2 quotes; got 2."}
Trailing text."""
    r = parse_grader_response(raw)
    assert r["citation"] == 1
    assert r["faithfulness"] == 2
    assert r["completeness"] == 1
    assert r["no_hallucination"] == 1
    assert "2 quotes" in r["notes"]


def test_score_record_returns_per_dim_max_6():
    scored = {
        "citation": 1, "faithfulness": 2, "completeness": 2, "no_hallucination": 1,
        "notes": "clean"
    }
    record = {"id": "T1Q3", "tier": 1, "n_quotes": 2}
    out = score_record(record, scored)
    assert out["score"] == 6
    assert out["max"] == 6
    assert out["pass"] is True


def test_tier1_zero_quotes_forces_zero_citation():
    """Tier 1 with <2 quotes -> automatic 0 on citation regardless of grader."""
    scored = {"citation": 1, "faithfulness": 2, "completeness": 2, "no_hallucination": 1, "notes": ""}
    record = {"id": "T1Q5", "tier": 1, "n_quotes": 1}  # only 1 quote, Tier 1 needs ≥2
    out = score_record(record, scored)
    assert out["citation_override"] == 0
    assert out["score"] == 5  # citation forced to 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python -m pytest pipeline/tests/hermes/test_grade_faq_answers.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the grader**

```python
# pipeline/scripts/hermes/grade_faq_answers.py
"""Auto-grade FAQ baseline runs using Gemini 2.5 Flash.

Reads:   ~/.hermes/data/faq_runs/<date>/*.json
         ~/askanka.com/docs/faq/baseline_questions.json (for question text)
         ~/askanka.com/<source files referenced by citations>
Writes:  docs/research/hermes_pilot/report_cards/<date>-week-1.md
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path.home() / "askanka.com"
RUNS_BASE = Path.home() / ".hermes" / "data" / "faq_runs"
REPORT_DIR = REPO / "docs" / "research" / "hermes_pilot" / "report_cards"

GRADER_TEMPLATE = """You are grading an answer from a Hermes/Gemma-4 system-FAQ agent
that must answer ONLY from cited source files in the askanka.com repo.

Score on these 4 dimensions and return ONLY a JSON object with these keys:
  citation: 0 or 1 (1 if at least one source file from INDEX is cited; 0 otherwise)
  faithfulness: 0, 1, or 2 (0=contradicts source, 1=mostly aligned but one wrong claim, 2=every claim traceable to cited source)
  completeness: 0, 1, or 2 (0=doesn't address question, 1=partial, 2=addresses fully and at appropriate depth)
  no_hallucination: 0 or 1 (1=clean, only source-grounded claims; 0=invented at least one fact)
  notes: 1-2 sentences justifying the scores

QUESTION (Tier {tier}):
{q}

HERMES ANSWER:
---
{answer_text}
---

CITED SOURCE FILES (verbatim content):
---
{sources_content}
---

Return JSON ONLY. No prose, no markdown fences, no commentary."""


def load_source_content(citations: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in citations:
        full = REPO / path
        if full.exists():
            try:
                # Cap each source at 8 KB to fit grader context
                out[path] = full.read_text(encoding="utf-8", errors="replace")[:8000]
            except Exception as e:
                out[path] = f"<read-error: {e}>"
        else:
            out[path] = "<missing-file>"
    return out


def build_grader_prompt(record: dict, sources_content: dict[str, str]) -> str:
    sources_block = "\n\n".join(
        f"### {path}\n{content}" for path, content in sources_content.items()
    ) or "(no sources cited)"
    return GRADER_TEMPLATE.format(
        tier=record["tier"], q=record["q"],
        answer_text=record["answer_text"][:6000],
        sources_content=sources_block,
    )


def parse_grader_response(raw: str) -> dict:
    """Extract the LAST JSON object from grader output."""
    matches = list(re.finditer(r"\{[^{}]*\}", raw, re.DOTALL))
    if not matches:
        raise ValueError(f"No JSON object found in grader response: {raw[:200]}")
    return json.loads(matches[-1].group(0))


def score_record(record: dict, scored: dict) -> dict:
    cite = int(scored["citation"])
    faith = int(scored["faithfulness"])
    comp = int(scored["completeness"])
    halluc = int(scored["no_hallucination"])
    citation_override = None

    # Tier 1 requires ≥2 quotes; if not met, force citation = 0
    if record["tier"] == 1 and record.get("n_quotes", 0) < 2:
        citation_override = 0
        cite = 0

    score = cite + faith + comp + halluc
    return {
        "id": record["id"], "tier": record["tier"],
        "citation": cite, "faithfulness": faith,
        "completeness": comp, "no_hallucination": halluc,
        "score": score, "max": 6,
        "pass": score >= 5 and halluc == 1,  # per-question pass: ≥5/6 and no hallucination
        "citation_override": citation_override,
        "notes": scored.get("notes", ""),
    }


def call_gemini(prompt: str) -> str:
    """Call Gemini 2.5 Flash via the existing pipeline routing."""
    from pipeline.llm.gemini_client import call as gemini_call  # adjust import to actual module
    return gemini_call(prompt, model="gemini-2.5-flash", temperature=0.0, max_output_tokens=600)


def main(date_str: str | None = None) -> int:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    runs_dir = RUNS_BASE / date_str
    if not runs_dir.exists():
        print(f"FAIL: no runs at {runs_dir}", file=sys.stderr)
        return 1

    scored_records: list[dict] = []
    for path in sorted(runs_dir.glob("T*Q*.json")):
        record = json.loads(path.read_text())
        sources = load_source_content(record["citations"])
        prompt = build_grader_prompt(record, sources)
        try:
            raw = call_gemini(prompt)
            scored = parse_grader_response(raw)
        except Exception as e:
            scored = {"citation": 0, "faithfulness": 0, "completeness": 0,
                      "no_hallucination": 0, "notes": f"GRADER ERROR: {e}"}
        scored_records.append(score_record(record, scored))

    write_report_card(date_str, scored_records, runs_dir)
    return 0


def write_report_card(date_str: str, records: list[dict], runs_dir: Path) -> None:
    """Render the markdown report card per the spec format."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{date_str}-week-1.md"
    by_tier = {t: [r for r in records if r["tier"] == t] for t in (1, 2, 3, 4, 5)}

    total = sum(r["score"] for r in records)
    max_total = 6 * len(records)
    pct = round(100 * total / max_total, 1) if max_total else 0
    halluc_clean = sum(1 for r in records if r["no_hallucination"] == 1)
    halluc_pct = round(100 * halluc_clean / len(records), 1) if records else 0
    cite_pct = round(100 * sum(1 for r in records if r["citation"] == 1) / len(records), 1) if records else 0

    summary_path = runs_dir / "_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        latencies = [r["latency_seconds"] for r in summary["results"]]
        avg_latency_min = round(sum(latencies) / len(latencies) / 60, 1) if latencies else 0
    else:
        avg_latency_min = 0

    pass_overall = pct >= 85 and halluc_pct == 100 and cite_pct >= 80 and avg_latency_min <= 5
    if pass_overall:
        verdict = "PASS"
    elif halluc_pct < 100:
        verdict = "FAIL"
    else:
        verdict = "DWELL"

    lines = [
        f"# Hermes Pilot — Week 1 Report Card",
        "",
        f"**Date run:** {date_str}",
        "**Skills under test:** system-faq",
        f"**Total questions:** {len(records)}",
        f"**Aggregate score:** {total} / {max_total} ({pct}%)",
        "",
        "**Per-tier:**",
    ]
    for t in (1, 2, 3, 4, 5):
        rs = by_tier[t]
        if not rs:
            continue
        ts = sum(r["score"] for r in rs)
        tm = 6 * len(rs)
        lines.append(f"- Tier {t}: {ts}/{tm} ({round(100 * ts/tm, 1)}%)")

    lines += [
        "",
        "**Per-criterion:**",
        f"- Citation (a): {cite_pct}%",
        f"- Faithfulness (b): {sum(r['faithfulness'] for r in records)}/{2 * len(records)}",
        f"- Completeness (c): {sum(r['completeness'] for r in records)}/{2 * len(records)}",
        f"- Hallucination (d): {halluc_pct}% **(must be 100%)**",
        f"- Avg latency: {avg_latency_min} min/q (budget ≤ 5)",
        "",
        f"**Verdict:** {verdict}",
        "",
        "**Per-question:**",
        "| ID | Tier | Cite | Faith | Compl | NoHall | Score | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['id']} | {r['tier']} | {r['citation']} | {r['faithfulness']} | "
            f"{r['completeness']} | {r['no_hallucination']} | {r['score']}/6 | "
            f"{r['notes'][:80].replace('|', ' ')} |"
        )
    lines += [
        "",
        "**Bharat spot-check:** [TODO — review 5 random questions, note any disagreements with grader]",
        "",
        "**Triggered action:** [TODO — fill per acceleration table once spot-check complete]",
    ]
    out.write_text("\n".join(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python -m pytest pipeline/tests/hermes/test_grade_faq_answers.py -v
```

Expected: 4 passed. (The `call_gemini` import is mocked away — tests only cover prompt/parse/score logic, not the network call.)

- [ ] **Step 5: Adjust Gemini import to the real client**

Inspect `pipeline/llm/` (or wherever the existing Gemini client lives). If the import path differs from `pipeline.llm.gemini_client`, update `call_gemini` to use the actual module. Look for files matching `*gemini*.py` under `pipeline/`.

Run:
```bash
grep -r "def call" pipeline/ --include='*gemini*.py' | head
```

Use the existing function signature.

- [ ] **Step 6: Smoke-test grader on T1Q3 only**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && python3 -c \"
import json
from pathlib import Path
import sys
sys.path.insert(0, 'pipeline/scripts/hermes')
from grade_faq_answers import build_grader_prompt, call_gemini, parse_grader_response, score_record, load_source_content
import os
date = os.environ.get('TODAY', __import__('datetime').date.today().isoformat())
rec_path = Path.home() / '.hermes' / 'data' / 'faq_runs' / date / 'T1Q3.json'
rec = json.loads(rec_path.read_text())
sources = load_source_content(rec['citations'])
prompt = build_grader_prompt(rec, sources)
raw = call_gemini(prompt)
print('GRADER RAW:', raw[:400])
scored = parse_grader_response(raw)
final = score_record(rec, scored)
print('SCORED:', json.dumps(final, indent=2))
\""
```

Expected: a JSON-shaped grader response, a final score 0–6 with sane reasoning. If the grader returns broken JSON or scores feel off, iterate on `GRADER_TEMPLATE`.

- [ ] **Step 7: Run grader against the full batch + write report card**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && python3 pipeline/scripts/hermes/grade_faq_answers.py"
```

Expected: report card written to `docs/research/hermes_pilot/report_cards/<date>-week-1.md`.

- [ ] **Step 8: Commit grader + first report card**

```bash
ssh -i ~/.ssh/contabo_vmi3256563 anka@185.182.8.107 \
  "cd ~/askanka.com && git add docs/research/hermes_pilot/report_cards/*.md && \
   git commit -m 'docs(hermes): Week-1 report card — system-faq baseline' && \
   git push"
```

(Pull on laptop afterwards.)

```bash
git add pipeline/scripts/hermes/grade_faq_answers.py pipeline/tests/hermes/test_grade_faq_answers.py
git commit -m "feat(faq): Gemini-Flash auto-grader + Week-1 report card renderer

4-dimension rubric (citation, faithfulness, completeness, no-hallucination),
Tier-1 zero-quote override, verdict logic per acceleration mechanic.
4 tests cover prompt build, response parse, score compute, Tier-1 override."
```

---

## Task 10 — Spot-check protocol + Week-1 verdict + memory update

**Files:**
- Modify: `docs/research/hermes_pilot/report_cards/<date>-week-1.md` (Bharat spot-check section + Triggered action)
- Create: `memory/project_hermes_week1_<date>.md`

- [ ] **Step 1: Bharat picks 5 random question IDs and re-grades manually**

The user reads the per-question rows in the report card, picks any 5 by hand, opens each `<question_id>.json` in `~/.hermes/data/faq_runs/<date>/`, reads the answer + cites + quotes, and scores against the same 4-dim rubric. Any disagreement with the Gemini grader on a dimension is recorded in the report-card "Bharat spot-check" section.

- [ ] **Step 2: Decide verdict**

| Aggregate result | Verdict |
|---|---|
| ≥85% AND halluc=100% AND cite≥80% AND avg latency ≤ 5 min/q | **PASS** |
| Halluc < 100% (any fabricated fact) | **FAIL** |
| Otherwise | **DWELL** |

If Bharat's spot-check disagrees with grader on ≥ 2 of 5 questions in a way that flips the verdict, the verdict is downgraded one step (PASS→DWELL or DWELL→FAIL) and the disagreement is logged.

- [ ] **Step 3: Trigger Week-2 action per acceleration table**

| Verdict | Week-2 action |
|---|---|
| PASS + faithfulness 100% | Migrate next 2 free-form skills (daily Gemma 4 Pilot report card narrative + EOD Telegram one-liner) AND draft strict-JSON scaffold spec |
| PASS | Migrate next 1 skill (Gemma 4 Pilot report card narrative) |
| DWELL — fail on (a) | Patch SKILL.md to enforce stricter citation, no scope change |
| DWELL — fail on (b) or (c) | Expand INDEX.md (likely missing topic), no scope change |
| FAIL | Re-author SKILL.md with stricter "no general-knowledge" prompt; if 3rd FAIL across re-runs, escalate the entire FAQ approach |

Edit the report card's "Triggered action" line to record the chosen action.

```bash
git add docs/research/hermes_pilot/report_cards/<date>-week-1.md
git commit -m "docs(hermes): Week-1 verdict + Bharat spot-check + triggered action

Verdict: <PASS/DWELL/FAIL>. Spot-check disagreement: <0/5, 1/5, ...>.
Triggered: <chosen Week-2 action>."
```

- [ ] **Step 4: Save memory entry**

Create `memory/project_hermes_week1_<date>.md`:

```markdown
---
name: Hermes Week 1 — system-faq verdict
description: Outcome of the system-faq Week-1 baseline (30 questions, 5 tiers).
  Verdict <PASS/DWELL/FAIL>; aggregate <X%>; Tier-1 (Karpathy/ML) <X%>; hallucination
  <X%>; triggered action <next step>. Reference for Week-2 scope decisions.
type: project
---

[fill in numbers from the report card]

**Why this matters:** First production verdict on Hermes-as-operator. Drives the
Week-2 scope per the acceleration mechanic in
`docs/superpowers/specs/2026-05-02-hermes-system-faq-design.md`.

**How to apply:**
- Week-2 task selection follows the verdict's triggered-action line.
- Any future change to SKILL.md or INDEX.md must record the diff and a
  re-run report card; do NOT mutate the Week-1 baseline_questions.json.
- If the verdict was FAIL, do NOT proceed to Spec B (commercialization) until
  re-run scores PASS.
```

Add to `memory/MEMORY.md` index (one-line entry under ~150 chars).

```bash
# memory lives outside the repo; commit only the index update
```

(Memory dir is in `~/.claude/projects/...`, not committed to repo.)

---

## Self-review

**Spec coverage:**
- ✅ Secrets audit (Task 1)
- ✅ Repo clone + sync timer + inventory update (Task 2)
- ✅ INDEX.md authorship (Task 3)
- ✅ INDEX link-checker (Task 4)
- ✅ SKILL.md + 5 worked examples (Task 5)
- ✅ 30 baseline questions (Task 6)
- ✅ Citation parser (Task 7)
- ✅ Runner script (Task 8)
- ✅ Gemini auto-grader (Task 9)
- ✅ First report card run (Task 9 step 7)
- ✅ Spot-check + verdict + triggered action + memory (Task 10)

**Placeholder scan:**
- One `[fill in numbers from the report card]` in the memory-entry template (Task 10) — that's the user's input after the run, not a plan placeholder, OK.
- One `[TODO — review 5 random questions, note any disagreements with grader]` in the report card render — that's an explicit hand-off point for the spot-check, OK.

**Type consistency:** `extract_citations` and `extract_quotes` consistent across Task 7 (definition) and Task 8 (runner import). `score_record`, `parse_grader_response`, `build_grader_prompt` consistent in Task 9. Tier-1-quote-requirement check is `n_quotes < 2` consistently in runner and grader.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-02-hermes-system-faq-week1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good fit for the bulk-authoring tasks (INDEX, baseline questions, SKILL.md examples) and the TDD tasks (parser, grader).
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good fit if you want to watch each step land before the next.

Which approach?
