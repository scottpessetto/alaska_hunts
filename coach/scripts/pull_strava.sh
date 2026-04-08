#!/bin/bash
# Wrapper for Strava data pull. Adapt pull_strava.py to your existing script.
# Cron entry: 20 5 * * * ~/claude/coach/scripts/pull_strava.sh >> ~/claude/coach/logs/cron.log 2>&1
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"
DATE=$(date +%Y-%m-%d)
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] [strava]"

log() { echo "$LOG_PREFIX $1"; }

log "Starting Strava pull for $DATE"

OUTPUT="$COACH_DIR/data/strava/${DATE}.yaml"
mkdir -p "$(dirname "$OUTPUT")"

cd "$COACH_DIR"
python3 scripts/pull_strava.py --date "$DATE" --output "$OUTPUT"

if [ $? -eq 0 ] && [ -s "$OUTPUT" ]; then
    log "Success: $OUTPUT"
else
    log "FAILED: Strava pull for $DATE"
    exit 1
fi
