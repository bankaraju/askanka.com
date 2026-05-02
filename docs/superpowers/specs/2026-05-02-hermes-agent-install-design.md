# Hermes Agent — Install on Contabo VPS, backed by local Gemma 4

**Date:** 2026-05-02
**Status:** Install in progress — gating on user approval to execute `setup-hermes.sh` on the VPS (harness flagged "Untrusted Code Integration" on first attempt).
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

### 3. Wire model to local Gemma 4

Hermes accepts any OpenAI-compatible endpoint. Ollama's `/v1` route is OpenAI-compatible — no shim needed.

Preferred (declarative):
```bash
hermes config set provider openai-compatible
hermes config set base_url http://127.0.0.1:11434/v1
hermes config set model gemma4:26b
hermes config set api_key ollama   # Ollama ignores the key; any string works
```

Fallback (interactive, if `config set` keys differ from above):
```bash
hermes model     # walks through provider + endpoint + model picker
```

Exact key names will be confirmed against `hermes config --help` at install time; this spec records intent, not the literal CLI invocation.

### 4. Verify

```bash
hermes doctor                                    # all green
echo "Reply with PONG only." | hermes --no-tools # one-shot sanity prompt
```

Pass criteria: doctor green, sanity prompt returns "PONG" (or close) within ~30 s on Contabo CPU. If it stalls > 2 min, abort and check Ollama logs (`journalctl -u ollama -n 50`).

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

- [ ] `setup-hermes.sh` exits 0
- [ ] `which hermes` → `~/.local/bin/hermes`
- [ ] `hermes --version` prints a version
- [ ] `hermes doctor` → all green
- [ ] `hermes config get provider` → `openai-compatible` (or platform's equivalent)
- [ ] `hermes config get base_url` → `http://127.0.0.1:11434/v1`
- [ ] `hermes config get model` → `gemma4:26b`
- [ ] One-shot sanity prompt returns a Gemma-4-style answer within 60 s
- [ ] Memory file `memory/reference_hermes_agent_contabo.md` created

## Open questions (none blocking)

1. Do we want a `hermes` shortcut command on the laptop that SSHes into Contabo and starts a session? (Trivial bash alias; defer until first use.)
2. Do we want Hermes to read the askanka.com repo? (Defer — it's a separate workflow; we'd mount the repo or `cd ~/askanka.com` inside Hermes' terminal backend.)
