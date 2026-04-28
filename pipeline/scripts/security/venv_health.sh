#!/usr/bin/env bash
# Verify the production venv at /home/anka/askanka.com/.venv is intact and
# that core deps import. Catches the silent class of failure where .venv/bin
# disappears (or pip metadata gets nuked) and every systemd service that
# references .venv/bin/python starts failing without anyone noticing for
# hours. Belongs in the daily security cadence.
set -uo pipefail
# shellcheck source=/dev/null
. /home/anka/askanka.com/pipeline/scripts/load_telegram_creds.sh

VENV=/home/anka/askanka.com/.venv
errors=()

if [ ! -x "$VENV/bin/python" ]; then
    errors+=("$VENV/bin/python is missing or not executable")
fi
if [ ! -f "$VENV/pyvenv.cfg" ]; then
    errors+=("$VENV/pyvenv.cfg is missing — venv is corrupt")
fi

if [ ${#errors[@]} -eq 0 ]; then
    if ! "$VENV/bin/python" -c "
import sys
mods = ['pandas', 'numpy', 'fastapi', 'uvicorn', 'requests', 'yfinance', 'kiteconnect']
missing = []
broken = []
for m in mods:
    try:
        mod = __import__(m)
        if getattr(mod, '__file__', None) is None and not getattr(mod, '__path__', None):
            broken.append(m)
    except Exception as exc:
        missing.append(f'{m}: {exc.__class__.__name__}')
if missing or broken:
    print('MISSING=' + ','.join(missing), file=sys.stderr)
    print('BROKEN=' + ','.join(broken), file=sys.stderr)
    sys.exit(1)
print('OK')
" 2>/tmp/venv_health.err; then
        errors+=("import probe failed: $(cat /tmp/venv_health.err 2>/dev/null | tr '\n' ' ')")
    fi
fi

if [ ${#errors[@]} -gt 0 ]; then
    msg="🛡️ Anka VPS venv health: BROKEN — production systemd services will fail
$(printf '  - %s\n' "${errors[@]}")
Fix: cd /home/anka/askanka.com && rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements_vps.txt"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$msg" >/dev/null || true
    fi
    echo "[venv_health] FAIL"
    printf '  - %s\n' "${errors[@]}"
    exit 1
fi

echo "[venv_health] OK"
