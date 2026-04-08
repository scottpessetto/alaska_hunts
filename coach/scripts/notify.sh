#!/bin/bash
# Send push notification via ntfy (self-hosted or ntfy.sh).
# Zero dependencies — just curl.
#
# Usage:
#   notify.sh "Briefing ready"                     # short notification
#   notify.sh --file output/daily/2026-04-08.md    # full file as notification body
#   notify.sh --title "Weekly Analysis" --file ...  # custom title
#   notify.sh --dry-run "test message"             # print without sending
set -euo pipefail

COACH_DIR="${COACH_DIR:-$HOME/claude/coach}"
CONFIG_FILE="$COACH_DIR/config/ntfy.env"

# --- Load config ---
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found. Create it with:"
    echo "  NTFY_URL=http://your-mac-mini:8080/coach"
    echo "  # or use the free public server:"
    echo "  NTFY_URL=https://ntfy.sh/your-secret-topic-name"
    exit 1
fi

source "$CONFIG_FILE"

if [ -z "${NTFY_URL:-}" ]; then
    echo "Error: NTFY_URL not set in $CONFIG_FILE"
    exit 1
fi

# --- Parse args ---
TITLE="Running Coach"
MESSAGE=""
FILE=""
DRY_RUN=false
PRIORITY="default"  # low, default, high, urgent

while [ $# -gt 0 ]; do
    case "$1" in
        --title)    TITLE="$2"; shift 2 ;;
        --file|-f)  FILE="$2"; shift 2 ;;
        --priority) PRIORITY="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        *)          MESSAGE="$1"; shift ;;
    esac
done

# --- Get message body ---
if [ -n "$FILE" ]; then
    FILEPATH="$FILE"
    [ ! -f "$FILEPATH" ] && FILEPATH="$COACH_DIR/$FILE"
    if [ ! -f "$FILEPATH" ]; then
        echo "Error: File not found: $FILE"
        exit 1
    fi
    MESSAGE=$(cat "$FILEPATH")
fi

if [ -z "$MESSAGE" ]; then
    echo "Error: No message. Use --file or pass text as argument."
    exit 1
fi

# ntfy supports markdown in the body (up to 4096 bytes for push preview).
# Send the full content — the app shows a preview and you can expand.
# Truncate for the push notification click text, full body in the app.

if [ "$DRY_RUN" = true ]; then
    echo "--- DRY RUN ---"
    echo "URL:      $NTFY_URL"
    echo "Title:    $TITLE"
    echo "Priority: $PRIORITY"
    echo "Body (${#MESSAGE} chars):"
    echo "$MESSAGE" | head -20
    [ ${#MESSAGE} -gt 500 ] && echo "... [truncated for preview]"
    echo "--- END ---"
    exit 0
fi

# --- Send via curl ---
curl -s \
    -H "Title: $TITLE" \
    -H "Priority: $PRIORITY" \
    -H "Markdown: yes" \
    -d "$MESSAGE" \
    "$NTFY_URL" > /dev/null

echo "Notification sent to $NTFY_URL (${#MESSAGE} chars)"
