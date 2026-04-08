#!/bin/bash
# Generate weekly deep analysis via Claude Code, then send via text.
# Cron entry: 0 6 * * 0 ~/claude/coach/scripts/weekly_analysis.sh >> ~/claude/coach/logs/cron.log 2>&1
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"
DATE=$(date +%Y-%m-%d)
WEEK=$(date +%Y-W%V)
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] [weekly]"

log() { echo "$LOG_PREFIX $1"; }

log "Starting weekly analysis for $WEEK"

# --- Helper ---
read_file() {
    if [ -f "$1" ]; then
        cat "$1"
    else
        echo "[No data available: $(basename "$1")]"
    fi
}

date_minus_days() {
    local days=$1
    if date -v-1d +%Y-%m-%d >/dev/null 2>&1; then
        date -v-${days}d +%Y-%m-%d
    else
        date -d "-${days} days" +%Y-%m-%d
    fi
}

# --- Archive current context ---

CONTEXT_FILE="$COACH_DIR/memory/athlete_context.md"
SNAPSHOTS_DIR="$COACH_DIR/memory/weekly_snapshots"
mkdir -p "$SNAPSHOTS_DIR"

if [ -f "$CONTEXT_FILE" ]; then
    cp "$CONTEXT_FILE" "$SNAPSHOTS_DIR/${WEEK}.md"
    log "Archived context to $SNAPSHOTS_DIR/${WEEK}.md"
fi

# --- Gather ALL data from past 7 days ---

WEEK_DATA=""
for i in $(seq 0 6); do
    D=$(date_minus_days $i)
    for subdir in "data/checkins" "data/garmin" "data/strava"; do
        F="$COACH_DIR/${subdir}/${D}.yaml"
        if [ -f "$F" ]; then
            WEEK_DATA="${WEEK_DATA}
--- ${subdir}/${D}.yaml ---
$(cat "$F")
"
        fi
    done
done

# --- Gather daily briefings from past 7 days ---

WEEK_BRIEFINGS=""
for i in $(seq 0 6); do
    D=$(date_minus_days $i)
    F="$COACH_DIR/output/daily/${D}.md"
    if [ -f "$F" ]; then
        WEEK_BRIEFINGS="${WEEK_BRIEFINGS}
--- daily/${D}.md ---
$(cat "$F")
"
    fi
done

# --- Previous week's analysis ---

PREV_WEEK_DATE=$(date_minus_days 7)
# Compute previous ISO week
if date -v-1d +%Y-%m-%d >/dev/null 2>&1; then
    PREV_WEEK=$(date -v-7d +%Y-W%V)
else
    PREV_WEEK=$(date -d "-7 days" +%Y-W%V)
fi
PREV_ANALYSIS=""
PREV_FILE="$COACH_DIR/output/weekly/${PREV_WEEK}.md"
if [ -f "$PREV_FILE" ]; then
    PREV_ANALYSIS=$(cat "$PREV_FILE")
fi

OUTPUT_FILE="$COACH_DIR/output/weekly/${WEEK}.md"
mkdir -p "$(dirname "$OUTPUT_FILE")"

# --- Build prompt ---

PROMPT=$(cat <<PROMPT_EOF
$(read_file "$COACH_DIR/prompts/weekly_analysis.md")

=== COACHING PHILOSOPHY ===
$(read_file "$COACH_DIR/config/coach.md")

=== RACE PROFILE ===
$(read_file "$COACH_DIR/config/race_profile.yaml")

=== ATHLETE CONTEXT (rolling memory) ===
$(read_file "$CONTEXT_FILE")

=== TRAINING PLAN ===
$(read_file "$COACH_DIR/config/training_plan.yaml")

=== THIS WEEK'S RAW DATA (checkins + garmin + strava) ===
${WEEK_DATA:-"[No data available for this week]"}

=== THIS WEEK'S DAILY BRIEFINGS ===
${WEEK_BRIEFINGS:-"[No daily briefings available]"}

=== PREVIOUS WEEK'S ANALYSIS ===
${PREV_ANALYSIS:-"[No previous weekly analysis available]"}

Today is $DATE, end of training week $WEEK. Generate the weekly analysis now.
PROMPT_EOF
)

# --- Invoke Claude Code ---

log "Calling Claude Code for weekly analysis..."
claude -p "$PROMPT" > "$OUTPUT_FILE"

if [ $? -ne 0 ] || [ ! -s "$OUTPUT_FILE" ]; then
    log "ERROR: Claude Code weekly analysis failed"
    exit 1
fi

log "Weekly analysis written to $OUTPUT_FILE"

# --- Full context rewrite ---

log "Performing full context rewrite..."
CONTEXT_PROMPT=$(cat <<CTX_EOF
$(read_file "$COACH_DIR/prompts/context_update.md")

=== CURRENT ATHLETE CONTEXT ===
$(read_file "$CONTEXT_FILE")

=== WEEKLY ANALYSIS JUST COMPLETED ===
$(cat "$OUTPUT_FILE")

=== FULL WEEK RAW DATA ===
${WEEK_DATA:-"[No data]"}

Today is $DATE, end of training week $WEEK. Perform a thorough rewrite of athlete_context.md.
CTX_EOF
)

claude -p "$CONTEXT_PROMPT" > "${CONTEXT_FILE}.tmp"

if [ $? -eq 0 ] && [ -s "${CONTEXT_FILE}.tmp" ]; then
    mv "${CONTEXT_FILE}.tmp" "$CONTEXT_FILE"
    log "Context fully rewritten"
else
    rm -f "${CONTEXT_FILE}.tmp"
    log "WARNING: Context rewrite failed, keeping previous version"
fi

# --- Send push notification ---

if [ -f "$COACH_DIR/config/ntfy.env" ]; then
    log "Sending weekly analysis via ntfy..."
    bash "$COACH_DIR/scripts/notify.sh" \
        --title "Weekly Analysis - $WEEK" \
        --priority high \
        --file "$OUTPUT_FILE" 2>&1 || \
        log "WARNING: Push notification failed"
else
    log "ntfy not configured, skipping notification"
fi

log "Weekly analysis complete"
