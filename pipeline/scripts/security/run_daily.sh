#!/usr/bin/env bash
# Daily security cadence master runner — sequence all the small checks,
# emit a single Telegram green-tick when everything passes.
set -uo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

S=/home/anka/askanka.com/pipeline/scripts/security
errors=0

run() {
    local name="$1"; shift
    if "$@"; then
        :
    else
        echo "[run_daily] FAIL: $name"
        errors=$((errors+1))
    fi
}

run apt_status      "$S/../report_apt_status.sh"
run auth_triage     sudo "$S/auth_triage.sh"
run port_audit      sudo "$S/port_audit.sh"
run ssh_keys_audit  "$S/ssh_keys_audit.sh"
run resource_watch  "$S/resource_watch.sh"

if [ "$errors" -eq 0 ]; then
    msg="✅ Anka VPS daily security check: all green ($(date '+%Y-%m-%d %H:%M IST'))"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || true
    fi
fi
exit "$errors"
