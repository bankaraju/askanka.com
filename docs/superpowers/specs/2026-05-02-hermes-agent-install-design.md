# Hermes Agent — Install on Contabo VPS, backed by local Gemma 4

**Date:** 2026-05-02
**Status:** ✅ Installed and wired to local Gemma 4 (2026-05-02 13:46 IST). Sanity prompt verified end-to-end.
**Author:** Claude (auto mode) on Bharat's instruction
**License of installed software:** MIT (Hermes Agent), Apache 2.0 (Gemma 4 — already running)

## What

Install [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (commit `f98b5d00a49b01fb833deecace78656035bc6f6d`, cloned 2026-05-02 13:18 IST) on the Contabo VPS (`anka@185.182.8.107`) and configure it to use the **local Gemma 4 26B-A4B** model already serving on Ollama at `127.0.0.1:11434`. No external LLM provider, no per-token cost, no Telegram/Discord/Slack gateway, no autonomous cron.

Hermes Agent is a self-improving agent runtime: TUI + skill creation from experience + FTS5 session search + (optional) messaging gateways + (optional) cron scheduler. We're installing the runtime only; gateway and cron features are out of scope for this install.

## Why

Bharat asked for an agentic shell on Contabo that talks to local Gemma 4. Rationale matches existing posture:

- **Cost discipline** (`memory/feedback_cost_discipline.md`) — local model = $0/token.
- **Laptop = context, VPS = execution** (`memory/feedback_laptop_context_vps_execution.md`) — Hermes runs on VPS, doesn't compete with laptop pipeline tasks.
- **Apache 2.0 + MIT** — both permissive, no vendor lock-in, aligned with the Gemma 4 Pilot's licensing rationale.

This is **not** a substitute for the Gemma 4 Pilot. The Pilot is forward-only shadow evaluation of Gemma 4 against Gemini for four mundane production tasks (trust score concall supplement, news classification, EOD narrative, markets article). Hermes is a separate user-facing agent — Bharat's interactive shell on the VPS — not a production pipeline component. **Pilot routing is unchanged.**

## Architecture

```
Contabo VPS (anka@185.182.8.107)
├── /usr/bin/python3              (3.x system)
├── ollama.service (active)
│   └── 127.0.0.1:11434  ← gemma4:26b (5571076f3d70, 17 GB)
└── ~/hermes-agent/                (this install)
    ├── .git → github.com/NousResearch/hermes-agent (HEAD f98b5d0)
    ├── venv/  (uv-managed Python 3.11, created by setup-hermes.sh)
    ├── setup-hermes.sh
    └── pyproject.toml             (.[all] extras pulled by setup)

Symlink: ~/.local/bin/hermes → ~/hermes-agent/hermes
Config:  ~/.hermes/config.toml    (created by `hermes setup` / `hermes config set`)
State:   ~/.hermes/                (skills, memory, FTS5 sessions DB)
```

**Data flow at runtime:**
```
Bharat (laptop SSH) ──► hermes (TUI on VPS) ──► OpenAI-compatible client
                                                  │
                                                  ▼
                                          http://127.0.0.1:11434/v1
                                                  │
                                                  ▼
                                           Ollama → gemma4:26b
```

## Pre-install recon (verified 2026-05-02)

| Item | Status |
|---|---|
| Disk free on `/` | 450 GB / 484 GB total (7% used) |
| `ollama.service` | active |
| Model `gemma4:26b` | present, 17 GB |
| Ollama API `/api/version` | 200 → 0.21.2 |
| `git`, `python3`, `pip` | present |
| `gh`, `pipx` | not installed (not required) |
| Hermes repo cloned | yes, `~/hermes-agent` HEAD `f98b5d0` |

## Install steps

### 1. Run installer (manual contributor path)

```bash
cd ~/hermes-agent
./setup-hermes.sh
# answer N to the optional ripgrep sudo prompt (we don't need it)
```

The script (audited via raw GitHub fetch on 2026-05-02):
- installs `uv` from `https://astral.sh/uv/install.sh` (the only `curl | sh`, official Astral)
- creates `venv/` with Python 3.11
- runs `uv pip install -e ".[all]"`
- symlinks `~/.local/bin/hermes` → repo's hermes launcher
- writes shell-config snippets to `~/.bashrc` so `hermes` is on `$PATH`

All writes confined to `~/.local/bin`, `~/.hermes/`, `~/.{bashrc,zshrc,bash_profile}`, and the cloned repo. **No system-dir writes outside the optional ripgrep `apt install` (which we skip).**

### 2. Reload shell + sanity

```bash
source ~/.bashrc
hermes --version
hermes doctor
```

### 3. Wire model to local Gemma 4 (as actually shipped 2026-05-02)

Hermes accepts any OpenAI-compatible endpoint. Ollama's `/v1` route is OpenAI-compatible. The CLI has no `hermes config set` subcommand — config is file-based at `~/.hermes/config.yaml` (canonical user config, takes precedence over project-local `cli-config.yaml`).

`~/.hermes/config.yaml`:
```yaml
model:
  default: "gemma4:26b"
  provider: "custom"          # alias "ollama" was NOT honored; "custom" works
  base_url: "http://127.0.0.1:11434/v1"

providers:
  custom:
    request_timeout_seconds: 600
    stale_timeout_seconds: 1200
```

`~/.hermes/.env` (chmod 600):
```
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=ollama
```

The `OPENAI_API_KEY` is a placeholder string — Ollama ignores Authorization headers but Hermes' OpenAI client requires the variable to be non-empty.

**Failure mode observed during install:** with `provider: "ollama"` (the alias the example claims maps to "custom"), Hermes silently fell through to its `auto` provider chain and tried OpenRouter, returning empty output and writing 401 dumps under `~/.hermes/sessions/request_dump_*.json`. Setting `provider: "custom"` explicitly fixed it.

**Token budget gotcha:** Gemma 4 emits its answer in two fields, `reasoning` and `content`. With small `max_tokens`, Gemma fills `reasoning` and leaves `content` empty — Hermes prints nothing. Don't cap `max_tokens` low; the default (model native ceiling) is correct.

**Context-window gotcha (discovered 2026-05-02 15:30 IST during system-faq skill bring-up):** Ollama loads Gemma 4 with the model-default 4K context. Hermes Agent hard-requires ≥64K context and refuses to start any skill-driven run otherwise (`ValueError: Model X has a context window of 4,096 tokens, which is below the minimum 64,000 required by Hermes Agent`). Fix without sudo by creating a per-model variant via Modelfile:

```bash
cat > /tmp/Modelfile.gemma4_64k <<'EOF'
FROM gemma4:26b
PARAMETER num_ctx 65536
EOF
ollama create gemma4-64k -f /tmp/Modelfile.gemma4_64k
sed -i 's/gemma4:26b/gemma4-64k/' ~/.hermes/config.yaml
```

Memory cost: KV cache at 64K context is ~12 GB extra RAM (within Contabo's 64 GB). Latency cost: prefill scales linearly with input — first answer at full skill-context (~10–20K input tokens) takes 5–15 min on CPU. Plan budgets reflect this.

### 4. Verify (actually run 2026-05-02 13:46 IST)

```bash
~/.local/bin/hermes doctor       # all critical checks green
~/.local/bin/hermes -z 'In one short sentence: what is 2 plus 2?'
# → "2 + 2 = 4."
```

Confirmed in `~/.hermes/sessions/session_20260502_134651_b74e5e.json`:
- `base_url`: `http://127.0.0.1:11434/v1`
- `model`: `gemma4:26b`
- assistant content: `2 + 2 = 4.`

Pass criteria met: doctor green on critical sections (Python/venv/config files/core tools), sanity prompt routed through local Ollama, response < 60 s.

## Out of scope (deferred, easy to add later)

| Feature | Status | Why deferred |
|---|---|---|
| Telegram gateway | OFF | We already have a Telegram pipeline; no need to multi-publish. |
| Discord/Slack/WhatsApp/Signal gateways | OFF | Not requested. |
| Hermes built-in cron scheduler | OFF | We use systemd timers on VPS — single source of truth. |
| Routing pipeline tasks through Hermes | OFF | Gemma 4 Pilot stays in shadow mode untouched. |
| MCP integrations | OFF | Default empty — re-evaluate after first session. |
| Voice/TTS deps | Pulled by `.[all]` but unused | `.[all]` is the documented path; size cost is acceptable on a 484 GB disk. |
| Honcho user modeling backend | OFF (default) | Optional component; off by default. |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `setup-hermes.sh` blocked by Claude Code harness as "Untrusted Code Integration" | Documented; user runs once locally OR adds permission rule. |
| `.[all]` pulls voice deps that are heavy | Disk has 450 GB free; install footprint expected < 2 GB. |
| Gemma 4 CPU inference slow (5–10× vs frontier APIs per `CLAUDE.md` Pilot note) | Expected. Hermes is interactive, not latency-critical. |
| Hermes' agentic loop calls `gemma4:26b` heavily, starves the Gemma 4 Pilot's shadow tasks | Pilot tasks run at fixed times via systemd; Hermes runs only when Bharat is in a session. Collision risk = Bharat happens to be chatting at exactly the same minute as a pilot run. Acceptable; revisit if observed. |
| Hermes writes to `~/.hermes/` — if disk fills it could affect Ollama | 450 GB free; trivial. |
| Hermes self-modifying skills could create surprising behavior | All skill writes go to `~/.hermes/skills/`; no auto-execution outside of explicit user prompts. Telegram gateway is OFF so no remote actuation. |

## Rollback

Total reversion is one command:
```bash
rm -rf ~/hermes-agent ~/.hermes ~/.local/bin/hermes
# then strip the Hermes block from ~/.bashrc (search for 'hermes')
```
Ollama and `gemma4:26b` are not touched by this install or rollback.

No systemd unit is registered by this install. Nothing in `pipeline/config/anka_inventory.json` changes. No cron jobs land in the scheduler. The watchdog has nothing new to monitor.

## Documentation sync (per CLAUDE.md doc-sync mandate)

This install does **not** add a scheduled task, change the clockwork schedule, or alter the Golden Goose pipeline. Therefore:

- `pipeline/config/anka_inventory.json` — **no change** (nothing scheduled)
- `docs/SYSTEM_OPERATIONS_MANUAL.md` — **no change** (no pipeline impact)
- `CLAUDE.md` — **no change** (no architecture impact)
- Memory: a short reference memory will be added pointing at this spec so future sessions know Hermes exists on the VPS.

If/when a Hermes-driven pipeline task is added later, that future change ships with the doc-sync update.

## Verification checklist

- [x] `setup-hermes.sh` exits 0 (run prior to this session)
- [x] `which hermes` → `~/.local/bin/hermes` (symlink, target `~/hermes-agent/venv/bin/hermes`)
- [x] `hermes doctor` → all critical checks green (Python/venv/config/core tools); optional warnings ignored (no Discord/Telegram/OpenRouter — by design)
- [x] `~/.hermes/config.yaml` set: `provider: custom`, `base_url: http://127.0.0.1:11434/v1`, `default: gemma4:26b`
- [x] `~/.hermes/.env` set: `OPENAI_BASE_URL`, `OPENAI_API_KEY=ollama` (chmod 600)
- [x] One-shot sanity prompt routed through local Ollama, returned `2 + 2 = 4.` within seconds
- [x] Memory file `memory/reference_hermes_agent_contabo.md` created

## Strategic split — Claude = teacher, Hermes = operator (user-stated 2026-05-02)

This install is step 1 of a longer-term split between two agents:

| Agent | Role | Tasks |
|---|---|---|
| **Claude Code (4.7)** | Teacher / designer | Deep research, system design, hard debugging, architecture decisions, writing/refining Hermes skills, fixing Hermes failures |
| **Hermes (on Contabo, Gemma 4 backend)** | Operator | Run repeatable workflows, store memory, evolve skill files over time |
| **Gemma 4 (local Ollama)** | Cheap worker model | Default for routine generation tasks |

**What Hermes can learn:** procedures and skill files. It does **not** train Gemma's weights.

**Tasks to shift off Claude (routine):** summaries, file organization, daily reports, research collection, note cleanup, routine coding chores.

**Tasks Claude keeps:** deep research, system design, hard debugging, architecture decisions.

**Rule of thumb:**
- If task is repeatable → teach Hermes.
- If task is high-stakes or novel → use Claude.

**30-day ramp:**
- **Week 1** — Use Claude to author 5–10 Hermes skills for repetitive tasks.
- **Week 2** — Let Hermes run them; correct mistakes manually.
- **Week 3** — Move low-risk daily tasks fully to Hermes + Gemma 4.
- **Week 4** — Use Claude only when Hermes gets stuck or for high-value thinking.

**Hard boundary:** Hermes does **not** replace the scheduler. Windows Task Scheduler + VPS systemd timers stay authoritative for clockwork firing (09:16 open capture, 14:30 close, etc.). Hermes orchestrates the **content** of LLM-shaped tasks the scheduler triggers — it does not fire them itself. Backtests stay pure code (numpy/pandas) gated through `backtesting-specs.txt`; Hermes can propose hypotheses but cannot promote them.

**Gemma 4 Pilot relationship:** the existing Gemma 4 Pilot (CLAUDE.md, 2026-04-29 → 2026-05-19) is a parallel experiment. Pilot routing through `pipeline/config/llm_routing.json` is unchanged by this install. If a Pilot task graduates to `live` post-2026-05-19, that's the natural moment to evaluate routing it through Hermes-as-operator instead of direct provider calls.

## Open questions (none blocking)

1. Do we want a `hermes` shortcut command on the laptop that SSHes into Contabo and starts a session? (Trivial bash alias; defer until first use.)
2. Do we want Hermes to read the askanka.com repo? (Defer — it's a separate workflow; we'd mount the repo or `cd ~/askanka.com` inside Hermes' terminal backend.)
3. Cloud fallback (e.g. OpenRouter) when Gemma 4 is unreachable? Out of scope for this install — defeats the $0/token rationale unless we cap usage. Revisit only after we have a real failure mode to design against.
