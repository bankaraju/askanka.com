#!/usr/bin/env bash
# Weekly deep scan with lynis + rkhunter. One-line summary to Telegram, full
# logs kept under /var/log/anka-security/.
set -euo pipefail
# shellcheck disable=SC1091
source /home/anka/askanka.com/pipeline/.env 2>/dev/null || true

OUT_DIR=/var/log/anka-security
sudo mkdir -p "$OUT_DIR"
sudo chown anka:anka "$OUT_DIR" 2>/dev/null || true
ts=$(date +%Y-%m-%d)

lynis_log="$OUT_DIR/lynis-$ts.log"
sudo lynis audit system --quick --quiet --no-colors > "$lynis_log" 2>&1 || true
hardening=$(grep -oP 'Hardening index : \[\K\d+' "$lynis_log" 2>/dev/null | head -1 || echo "?")
warnings=$(grep -c '^Warning' "$lynis_log" 2>/dev/null || echo 0)
suggestions=$(grep -c '^Suggestion' "$lynis_log" 2>/dev/null || echo 0)

rkh_log="$OUT_DIR/rkhunter-$ts.log"
sudo rkhunter --check --skip-keypress --report-warnings-only > "$rkh_log" 2>&1 || true
rkh_warn=$(grep -c -i 'warning' "$rkh_log" 2>/dev/null || echo 0)

msg="🧪 Anka VPS weekly audit ($ts):
  lynis hardening=$hardening, warnings=$warnings, suggestions=$suggestions
  rkhunter warnings=$rkh_warn
  full: $lynis_log, $rkh_log"

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$msg" >/dev/null || true
fi

echo "$msg"
