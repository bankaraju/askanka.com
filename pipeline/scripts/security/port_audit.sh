#!/usr/bin/env bash
# Compare current listening ports against baseline. Alert on diff.
set -euo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

BASELINE=/home/anka/askanka.com/pipeline/config/security/baseline_listening_ports.txt
if [ ! -f "$BASELINE" ]; then
    echo "[port_audit] no baseline file — capturing current state as baseline"
    sudo ss -tlnpH | awk '{print $4, $6}' | sort -u > "$BASELINE"
    echo "[port_audit] baseline created at $BASELINE — review and commit"
    exit 0
fi

current=$(sudo ss -tlnpH | awk '{print $4, $6}' | sort -u)
diff_out=$(diff <(echo "$current") "$BASELINE" || true)

if [ -n "$diff_out" ]; then
    msg="🛡️ Anka VPS port audit: drift from baseline detected

$diff_out

Update baseline if intentional: $BASELINE"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || true
    fi
    echo "[port_audit] DRIFT detected — see above"
    exit 1
fi

echo "[port_audit] OK — listening ports match baseline"
