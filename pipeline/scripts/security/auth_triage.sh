#!/usr/bin/env bash
# Summarize last 24h of auth.log for failed SSH attempts and suspicious sudo.
# Alerts if failed-SSH count is anomalous OR if a sudo command appears from a
# user other than 'anka'.
set -euo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

LOG=/var/log/auth.log
[ -f "$LOG" ] || { echo "no /var/log/auth.log"; exit 0; }

failed_ssh=$(grep -E "Failed password|Invalid user" "$LOG" \
    | awk -v cutoff="$(date -d '-24 hours' '+%b %_d %H:%M')" '$0 >= cutoff' \
    | wc -l || true)
failed_ssh=${failed_ssh:-0}

top_ips=$(grep -E "Failed password|Invalid user" "$LOG" \
    | grep -oP 'from \K[\d.]+' \
    | sort | uniq -c | sort -rn | head -5 || true)

suspect_sudo=$(grep -E "sudo:" "$LOG" \
    | grep -v "USER=anka" \
    | grep -v "sudo: pam_unix" \
    | awk -v cutoff="$(date -d '-24 hours' '+%b %_d %H:%M')" '$0 >= cutoff' \
    | head -5 || true)

banned=$(sudo fail2ban-client status sshd 2>/dev/null | grep "Banned IP list" || echo "fail2ban: n/a")

msg="🔐 Anka VPS auth (24h): failed_ssh=$failed_ssh | suspect_sudo=$([ -z "$suspect_sudo" ] && echo none || echo PRESENT) | $banned"

if [ "$failed_ssh" -gt 50 ] || [ -n "$suspect_sudo" ]; then
    body="$msg

Top source IPs:
$top_ips"
    if [ -n "$suspect_sudo" ]; then
        body="$body

Suspect sudo:
$suspect_sudo"
    fi
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=⚠️ $body" >/dev/null || true
    fi
fi

echo "$msg"
