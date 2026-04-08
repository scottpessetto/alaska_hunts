#!/bin/bash
# Generate daily morning briefing via Claude Code, then send via text.
# Cron entry: 45 5 * * * ~/claude/coach/scripts/daily_briefing.sh >> ~/claude/coach/logs/cron.log 2>&1
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"
DATE=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%A)
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] [daily]"

log() { echo "$LOG_PREFIX $1"; }

log "Starting daily briefing for $DATE ($DAY_OF_WEEK)"

# --- Gather context files ---

CONTEXT_FILE="$COACH_DIR/memory/athlete_context.md"
PLAN_FILE="$COACH_DIR/config/training_plan.yaml"
PHILOSOPHY_FILE="$COACH_DIR/config/coach.md"
RACE_FILE="$COACH_DIR/config/race_profile.yaml"
GARMIN_TODAY="$COACH_DIR/data/garmin/${DATE}.yaml"

# Read files with fallbacks
read_file() {
    if [ -f "$1" ]; then
        cat "$1"
    else
        echo "[No data available: $(basename "$1")]"
    fi
}

# Gather last 7 days of check-ins and garmin data
RECENT_CHECKINS=""
RECENT_GARMIN=""
for i in $(seq 1 7); do
    # macOS date syntax: -v-Xd; Linux: -d "-X days"
    if date -v-1d +%Y-%m-%d >/dev/null 2>&1; then
        D=$(date -v-${i}d +%Y-%m-%d)
    else
        D=$(date -d "-${i} days" +%Y-%m-%d)
    fi

    CI_FILE="$COACH_DIR/data/checkins/${D}.yaml"
    GA_FILE="$COACH_DIR/data/garmin/${D}.yaml"

    if [ -f "$CI_FILE" ]; then
        RECENT_CHECKINS="${RECENT_CHECKINS}
--- ${D} ---
$(cat "$CI_FILE")
"
    fi

    if [ -f "$GA_FILE" ]; then
        RECENT_GARMIN="${RECENT_GARMIN}
--- ${D} ---
$(cat "$GA_FILE")
"
    fi
done

OUTPUT_FILE="$COACH_DIR/output/daily/${DATE}.md"
mkdir -p "$(dirname "$OUTPUT_FILE")"

# --- Build prompt with inlined data ---

PROMPT=$(cat <<PROMPT_EOF
$(read_file "$COACH_DIR/prompts/daily_briefing.md")

=== COACHING PHILOSOPHY ===
$(read_file "$PHILOSOPHY_FILE")

=== RACE PROFILE ===
$(read_file "$RACE_FILE")

=== ATHLETE CONTEXT (rolling memory) ===
$(read_file "$CONTEXT_FILE")

=== TRAINING PLAN ===
$(read_file "$PLAN_FILE")

=== TODAY'S GARMIN DATA ($DATE) ===
$(read_file "$GARMIN_TODAY")

=== RECENT CHECK-INS (last 7 days) ===
${RECENT_CHECKINS:-"[No recent check-ins]"}

=== RECENT GARMIN DATA (last 7 days) ===
${RECENT_GARMIN:-"[No recent Garmin data]"}

Today is $DAY_OF_WEEK, $DATE. Generate the daily briefing now.
PROMPT_EOF
)

# --- Invoke Claude Code ---

log "Calling Claude Code for briefing..."
claude -p "$PROMPT" > "$OUTPUT_FILE"

if [ $? -ne 0 ] || [ ! -s "$OUTPUT_FILE" ]; then
    log "ERROR: Claude Code briefing failed"
    exit 1
fi

log "Briefing written to $OUTPUT_FILE"

# --- Update rolling context ---

log "Updating athlete context..."
CONTEXT_PROMPT=$(cat <<CTX_EOF
$(read_file "$COACH_DIR/prompts/context_update.md")

=== CURRENT ATHLETE CONTEXT ===
$(read_file "$CONTEXT_FILE")

=== DAILY BRIEFING JUST GENERATED ===
$(cat "$OUTPUT_FILE")

=== TODAY'S GARMIN DATA ===
$(read_file "$GARMIN_TODAY")

=== RECENT CHECK-INS ===
${RECENT_CHECKINS:-"[No recent check-ins]"}

Today is $DAY_OF_WEEK, $DATE. Rewrite the athlete_context.md now.
CTX_EOF
)

claude -p "$CONTEXT_PROMPT" > "${CONTEXT_FILE}.tmp"

if [ $? -eq 0 ] && [ -s "${CONTEXT_FILE}.tmp" ]; then
    mv "${CONTEXT_FILE}.tmp" "$CONTEXT_FILE"
    log "Context updated"
else
    rm -f "${CONTEXT_FILE}.tmp"
    log "WARNING: Context update failed, keeping previous version"
fi

# --- Send push notification ---

if [ -f "$COACH_DIR/config/ntfy.env" ]; then
    log "Sending briefing via ntfy..."
    bash "$COACH_DIR/scripts/notify.sh" \
        --title "Daily Briefing - $DAY_OF_WEEK" \
        --file "$OUTPUT_FILE" 2>&1 || \
        log "WARNING: Push notification failed"
else
    log "ntfy not configured, skipping notification"
fi

log "Daily briefing complete"
