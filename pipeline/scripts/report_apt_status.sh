#!/usr/bin/env bash
# Daily apt status reporter — only alerts when there are upgradable packages.
set -euo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

apt list --upgradable 2>/dev/null | tail -n +2 > /tmp/apt-upgradable.txt
n_upgradable=$(wc -l < /tmp/apt-upgradable.txt)
sec_upgradable=$(grep -c -i 'security' /tmp/apt-upgradable.txt 2>/dev/null || true)
sec_upgradable=${sec_upgradable:-0}

last_run="$(stat -c %y /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null || echo 'never')"

if [ "$n_upgradable" -gt 0 ] || [ "$sec_upgradable" -gt 0 ]; then
    msg="📦 Anka VPS apt: $n_upgradable upgradable ($sec_upgradable security). Last unattended run: $last_run"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || true
    fi
    echo "$msg"
fi
echo "apt_status: ok ($n_upgradable upgradable)"
