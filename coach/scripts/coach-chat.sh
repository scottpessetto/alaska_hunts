#!/bin/bash
# Open an interactive Claude Code session with full coaching context loaded.
# Usage: coach-chat
#        coach-chat "Should I skip tomorrow's tempo run? My achilles is sore."
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"

read_file() {
    if [ -f "$1" ]; then
        cat "$1"
    else
        echo "[Not available: $(basename "$1")]"
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

# Gather last 3 days of check-ins and garmin data for recent context
RECENT_DATA=""
for i in $(seq 1 3); do
    D=$(date_minus_days $i)
    CI="$COACH_DIR/data/checkins/${D}.yaml"
    GA="$COACH_DIR/data/garmin/${D}.yaml"
    [ -f "$CI" ] && RECENT_DATA="${RECENT_DATA}
--- Check-in ${D} ---
$(cat "$CI")
"
    [ -f "$GA" ] && RECENT_DATA="${RECENT_DATA}
--- Garmin ${D} ---
$(cat "$GA")
"
done

# Today's briefing if it exists
TODAY=$(date +%Y-%m-%d)
TODAY_BRIEFING=""
if [ -f "$COACH_DIR/output/daily/${TODAY}.md" ]; then
    TODAY_BRIEFING="
=== TODAY'S BRIEFING ===
$(cat "$COACH_DIR/output/daily/${TODAY}.md")"
fi

SYSTEM_PROMPT="You are my mountain running coach. You have deep context on my training.
Be direct, specific, and data-informed. Reference actual numbers when relevant.
If I ask about modifying the plan, explain the tradeoffs.

=== COACHING PHILOSOPHY ===
$(read_file "$COACH_DIR/config/coach.md")

=== ATHLETE CONTEXT (your memory) ===
$(read_file "$COACH_DIR/memory/athlete_context.md")

=== TRAINING PLAN ===
$(read_file "$COACH_DIR/config/training_plan.yaml")

=== RACE PROFILE ===
$(read_file "$COACH_DIR/config/race_profile.yaml")

=== RECENT DATA (last 3 days) ===
${RECENT_DATA:-"[No recent data available]"}
${TODAY_BRIEFING}"

if [ $# -gt 0 ]; then
    # One-shot mode: answer a question and exit
    claude -p "${SYSTEM_PROMPT}

My question: $*"
else
    # Interactive mode: open a conversation
    claude --system-prompt "$SYSTEM_PROMPT"
fi
