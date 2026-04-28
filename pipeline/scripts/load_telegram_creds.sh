#!/usr/bin/env bash
# Source-only helper. Extracts Telegram creds from .env without bash-source
# semantics (avoids set -u trips on stray values, CRLF line endings, $
# substitutions in passwords, etc.).
#
# Usage:
#   . /home/anka/askanka.com/pipeline/scripts/load_telegram_creds.sh
#
# After sourcing, $TELEGRAM_BOT_TOKEN and $TELEGRAM_CHAT_ID are set (or empty
# strings if .env is missing). Callers should test with `[ -n "$VAR" ]`.

ENV_FILE="${ENV_FILE:-/home/anka/askanka.com/pipeline/.env}"
TELEGRAM_BOT_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"' || true)
TELEGRAM_CHAT_ID=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"' || true)
export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
