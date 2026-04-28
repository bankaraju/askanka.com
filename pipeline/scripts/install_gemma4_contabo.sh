#!/usr/bin/env bash
# One-shot Contabo bootstrap for Gemma 4 26B-A4B Q4_K_M via Ollama.
# Idempotent: safe to re-run.
#
# Spec: docs/superpowers/specs/2026-04-28-gemma4-pilot-design.md
# Plan: docs/superpowers/plans/2026-04-28-gemma4-pilot.md (Task 0)
set -euo pipefail

LOG_PREFIX="[install_gemma4_contabo]"
log() { echo "${LOG_PREFIX} $*"; }

# 1. Verify hardware preconditions
TOTAL_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
if [ "${TOTAL_GB}" -lt 40 ]; then
    log "FAIL: need >= 40 GB RAM, have ${TOTAL_GB} GB"
    exit 1
fi
log "RAM OK: ${TOTAL_GB} GB"

DISK_GB=$(df -BG /root 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G' || true)
if [ -z "${DISK_GB:-}" ]; then
    DISK_GB=$(df -BG / | awk 'NR==2 {print $4}' | tr -d 'G')
fi
if [ "${DISK_GB}" -lt 30 ]; then
    log "FAIL: need >= 30 GB free disk, have ${DISK_GB} GB"
    exit 1
fi
log "Disk OK: ${DISK_GB} GB free"

# 2. Install ollama if not present
if ! command -v ollama >/dev/null 2>&1; then
    log "Installing ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    log "ollama already installed: $(ollama --version 2>&1 | head -1)"
fi

# 3. Ensure systemd unit is enabled and running
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 2
if ! systemctl is-active --quiet ollama; then
    log "FAIL: ollama systemd service did not start"
    sudo systemctl status ollama --no-pager | tail -20 || true
    exit 1
fi
log "ollama service active"

# 4. Pull Gemma 4 26B-A4B Q4_K_M (~16 GB)
# Tag verified at https://ollama.com/library — confirm exact tag at runtime.
MODEL_TAG="${GEMMA4_TAG:-gemma4:26b-a4b-q4_k_m}"
if ! ollama list 2>/dev/null | grep -q "${MODEL_TAG}"; then
    log "Pulling ${MODEL_TAG} (~16 GB, may take 10-30 min on Contabo network)..."
    ollama pull "${MODEL_TAG}"
else
    log "${MODEL_TAG} already pulled"
fi

# 5. Smoke test
log "Running smoke test..."
RESPONSE=$(ollama run "${MODEL_TAG}" "Reply with exactly the single word: PONG" 2>&1 | head -5)
if echo "${RESPONSE}" | grep -qi "pong"; then
    log "Smoke test PASS"
else
    log "Smoke test FAIL -- got: ${RESPONSE}"
    exit 1
fi

log "DONE -- ollama + ${MODEL_TAG} ready on $(hostname) at $(date --iso-8601=seconds)"
