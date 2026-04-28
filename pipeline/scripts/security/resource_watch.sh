#!/usr/bin/env bash
# Disk and memory thresholds. Alert when crossed.
set -euo pipefail
# shellcheck source=/dev/null
. /home/anka/askanka.com/pipeline/scripts/load_telegram_creds.sh

DISK_PCT_THRESHOLD=85
MEM_PCT_THRESHOLD=92

disk_pct=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
mem_pct=$(free | awk '/^Mem:/ {printf "%.0f", ($2-$7)/$2*100}')

alerts=()
if [ "$disk_pct" -ge "$DISK_PCT_THRESHOLD" ]; then
    alerts+=("disk: ${disk_pct}% (threshold ${DISK_PCT_THRESHOLD}%)")
fi
if [ "$mem_pct" -ge "$MEM_PCT_THRESHOLD" ]; then
    alerts+=("mem: ${mem_pct}% (threshold ${MEM_PCT_THRESHOLD}%)")
fi

if [ "${#alerts[@]}" -gt 0 ]; then
    body="📈 Anka VPS resource pressure: ${alerts[*]}"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$body" >/dev/null || true
    fi
    exit 1
fi

echo "[resource_watch] disk=${disk_pct}% mem=${mem_pct}% — OK"
