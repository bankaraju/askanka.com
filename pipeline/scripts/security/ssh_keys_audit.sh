#!/usr/bin/env bash
# Alert if ~anka/.ssh/authorized_keys changes from baseline hash.
set -euo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

BASELINE_FILE=/home/anka/askanka.com/pipeline/config/security/authorized_keys.sha256
KEYS_FILE=/home/anka/.ssh/authorized_keys

if [ ! -f "$BASELINE_FILE" ]; then
    echo "[ssh_keys_audit] no baseline — capturing current"
    sha256sum "$KEYS_FILE" | awk '{print $1}' > "$BASELINE_FILE"
    echo "[ssh_keys_audit] baseline created — review and commit"
    exit 0
fi

current=$(sha256sum "$KEYS_FILE" | awk '{print $1}')
expected=$(cat "$BASELINE_FILE")

if [ "$current" != "$expected" ]; then
    msg="🚨 Anka VPS: ~anka/.ssh/authorized_keys changed.
Expected $expected
Got      $current

Verify: cat $KEYS_FILE
Update baseline if intentional: $BASELINE_FILE"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || true
    fi
    exit 1
fi
echo "[ssh_keys_audit] OK"
