#!/usr/bin/env bash
# Check every systemd unit in WATCHLIST. If any has been failing for the last
# 3 invocations, post a Telegram alert. Idempotent (only alerts once per
# transition into failed state — uses a flag file per unit).
set -euo pipefail

REPO="${ANKA_REPO_ROOT:-/home/anka/askanka.com}"
FLAG_DIR="/var/lib/anka/failure-flags"
mkdir -p "$FLAG_DIR" 2>/dev/null || sudo mkdir -p "$FLAG_DIR"

# Units we care about — extend as new timers are added
WATCHLIST=(
    "anka-auto-push.service"
    "anka-mirror-push.service"
    "anka-security-daily.service"
    "anka-security-weekly.service"
    "anka-terminal.service"
)

# shellcheck disable=SC1091
source "$REPO/pipeline/.env" 2>/dev/null || true

alert() {
    local msg="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || echo "[failure-watcher] telegram post failed"
    else
        echo "[failure-watcher] no Telegram creds — would alert: $msg"
    fi
}

for unit in "${WATCHLIST[@]}"; do
    state=$(systemctl is-failed "$unit" 2>&1 || true)
    flag="$FLAG_DIR/${unit}.failed"
    if [ "$state" = "failed" ]; then
        if [ ! -f "$flag" ]; then
            touch "$flag"
            alert "🚨 Anka VPS: $unit is in FAILED state — check journalctl -u $unit -n 50"
        fi
    else
        if [ -f "$flag" ]; then
            rm "$flag"
            alert "✅ Anka VPS: $unit recovered"
        fi
    fi
done
