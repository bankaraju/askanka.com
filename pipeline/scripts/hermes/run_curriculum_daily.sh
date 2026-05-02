#!/bin/bash
# Daily Hermes FAQ curriculum run on Contabo.
# Reads current stage, runs Gemma → grader → advances on 100% clean → Telegram.
#
# State: ~/.hermes/data/faq_curriculum_state.json
# Log:   ~/.hermes/data/faq_curriculum_log.jsonl
#
# Designed to be invoked by systemd timer at 22:00 IST.
set -euo pipefail

REPO="$HOME/askanka.com"
STATE="$HOME/.hermes/data/faq_curriculum_state.json"
LOG="$HOME/.hermes/data/faq_curriculum_log.jsonl"
DATE="$(date +%Y-%m-%d)"
PY="$REPO/.venv/bin/python"

cd "$REPO"
ENV_FILE="$REPO/pipeline/.env"
GEMINI_API_KEY=$(grep -E '^GEMINI_API_KEY=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"')
export GEMINI_API_KEY
. "$REPO/pipeline/scripts/load_telegram_creds.sh" 2>/dev/null || true

# Initialise state if missing — start at Stage 1.
if [ ! -f "$STATE" ]; then
  mkdir -p "$(dirname "$STATE")"
  echo '{"stage": 1, "history": [], "pass_streak": 0, "halt_pass": false}' > "$STATE"
fi

STAGE="$($PY -c "import json; print(json.load(open('$STATE'))['stage'])")"
HALT="$($PY -c "import json; print(json.load(open('$STATE')).get('halt_pass', False))")"

if [ "$HALT" = "True" ]; then
  echo "Curriculum HALTED — already PASSed at Stage 5. State: $STATE"
  exit 0
fi

echo "[$(date -Iseconds)] Curriculum daily run — date=$DATE stage=$STAGE"

# Run Gemma stage.
$PY pipeline/scripts/hermes/run_faq_curriculum.py --stage "$STAGE" --date "$DATE"

# Grade.
$PY pipeline/scripts/hermes/grade_faq_answers.py "$DATE"

# Read sidecar.
SIDECAR="$REPO/docs/research/hermes_pilot/report_cards/$DATE-week-1.json"
if [ ! -f "$SIDECAR" ]; then
  echo "FATAL: grader did not produce $SIDECAR"
  exit 2
fi

# Decide stage advancement: 100% halluc-clean AND no GRADER ERROR rows.
ADVANCE="$($PY <<EOF
import json
s = json.load(open("$SIDECAR"))
recs = s["records"]
clean = all(r.get("no_hallucination") == 1 for r in recs)
no_grader_err = all("GRADER ERROR" not in (r.get("notes") or "") for r in recs)
all_pass = all(r.get("pass") for r in recs)
print("yes" if (clean and no_grader_err and all_pass) else "no")
EOF
)"

NEW_STAGE="$STAGE"
NEW_HALT="false"
if [ "$ADVANCE" = "yes" ]; then
  if [ "$STAGE" -ge 5 ]; then
    NEW_HALT="true"
    echo "Stage 5 PASSed — curriculum HALTED."
  else
    NEW_STAGE="$((STAGE + 1))"
    echo "Stage $STAGE clean — advancing to Stage $NEW_STAGE."
  fi
fi

# Update state + append log entry.
$PY <<EOF
import json, datetime
s = json.load(open("$STATE"))
sidecar = json.load(open("$SIDECAR"))
entry = {
    "date": "$DATE",
    "stage_run": $STAGE,
    "tiers": sidecar.get("tiers_present"),
    "n_questions": sidecar["n_questions"],
    "aggregate_pct": sidecar["aggregate_pct"],
    "halluc_clean_pct": sidecar["halluc_clean_pct"],
    "citation_pct": sidecar["citation_pct"],
    "avg_latency_min": sidecar["avg_latency_min"],
    "verdict": sidecar["verdict"],
    "advanced": "$ADVANCE" == "yes",
    "stage_after": $NEW_STAGE,
    "halt_pass_after": "$NEW_HALT" == "true",
}
s["history"].append(entry)
s["stage"] = $NEW_STAGE
s["halt_pass"] = "$NEW_HALT" == "true"
if "$ADVANCE" == "yes":
    s["pass_streak"] = s.get("pass_streak", 0) + 1
else:
    s["pass_streak"] = 0
json.dump(s, open("$STATE", "w"), indent=2)
with open("$LOG", "a") as f:
    f.write(json.dumps(entry) + "\n")
EOF

# Telegram one-liner.
TG_MSG="$($PY <<EOF
import json
s = json.load(open("$SIDECAR"))
state = json.load(open("$STATE"))
emoji = "OK" if "$ADVANCE" == "yes" else "FAIL"
halt = " HALT-PASS" if state["halt_pass"] else ""
advance = f" -> Stage {state['stage']}" if "$ADVANCE" == "yes" and not state["halt_pass"] else ""
print(
    f"Hermes FAQ {emoji}{halt} Stage $STAGE n={s['n_questions']} "
    f"agg={s['aggregate_pct']}% halluc-clean={s['halluc_clean_pct']}% "
    f"verdict={s['verdict']}{advance}"
)
EOF
)"

echo "$TG_MSG"

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${TG_MSG}" > /dev/null && echo "Telegram sent." || echo "Telegram send failed."
else
  echo "(TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping Telegram.)"
fi

echo "[$(date -Iseconds)] Curriculum daily run done."
