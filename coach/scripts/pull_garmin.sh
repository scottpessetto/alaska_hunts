#!/bin/bash
# Wrapper for Garmin data pull. Adapt pull_garmin.py to your existing script.
# Cron entry: 15 5 * * * ~/claude/coach/scripts/pull_garmin.sh >> ~/claude/coach/logs/cron.log 2>&1
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] [garmin]"

log() { echo "$LOG_PREFIX $1"; }

log "Starting Garmin pull for $DATE"

OUTPUT="$COACH_DIR/data/garmin/${DATE}.yaml"
mkdir -p "$(dirname "$OUTPUT")"

cd "$COACH_DIR"
python3 scripts/pull_garmin.py --date "$DATE" --output "$OUTPUT"

if [ $? -eq 0 ] && [ -s "$OUTPUT" ]; then
    log "Success: $OUTPUT"
else
    log "FAILED: Garmin pull for $DATE"
    exit 1
fi
