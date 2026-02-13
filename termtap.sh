#!/bin/bash
# ---------------------------------------------------------------------------
# termtap — Send a terminal event to the Termtap menu bar app
#
# Usage:
#   termtap <event_title> <event_msg>
#   termtap terminate
#
# The window_id is automatically detected from the current Terminal.app window.
#
# Examples:
#   termtap "deploy" "starting deployment to staging"
#   termtap "build" "webpack build failed ❌"
#   termtap "test" "42 tests passed ✅"
#   termtap terminate
# ---------------------------------------------------------------------------

set -euo pipefail

PORT="${TERMINAL_FOCUS_PORT:-9876}"
HOST="127.0.0.1"

# --- Argument validation ---
if [ $# -lt 1 ]; then
    echo "Usage: termtap <event_title> [event_msg]"
    echo ""
    echo "  event_title   Short label for the event (e.g., 'build', 'deploy', 'test')"
    echo "  event_msg     Optional message with more detail"
    echo ""
    echo "Special event_title values:"
    echo "  terminate     Remove this terminal from the menu bar"
    echo ""
    echo "Examples:"
    echo "  termtap deploy 'deploying to production'"
    echo "  termtap build 'failed with exit code 1'"
    echo "  termtap terminate"
    exit 1
fi

EVENT_TITLE="$1"
EVENT_MSG="${2:-}"

# --- Get the window ID of the current Terminal.app window ---
get_window_id() {
    local wid
    wid=$(osascript -e '
        tell application "Terminal"
            set frontWindow to front window
            return id of frontWindow
        end tell
    ' 2>/dev/null)

    if [ -z "$wid" ]; then
        echo "Error: Could not determine Terminal.app window ID." >&2
        echo "Make sure you are running this from Terminal.app." >&2
        exit 1
    fi
    echo "$wid"
}

# Use cached window ID if available (avoids re-querying on every event)
if [ -z "${TERMINAL_FOCUS_WID:-}" ]; then
    WINDOW_ID=$(get_window_id)
    export TERMINAL_FOCUS_WID="$WINDOW_ID"
else
    WINDOW_ID="$TERMINAL_FOCUS_WID"
fi

# --- Send the event via HTTP POST ---
PAYLOAD=$(cat <<EOF
{
    "window_id": "$WINDOW_ID",
    "event_title": "$EVENT_TITLE",
    "event_msg": "$EVENT_MSG"
}
EOF
)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "http://${HOST}:${PORT}/" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" 2>/dev/null) || {
    echo "Error: Could not connect to Termtap app at ${HOST}:${PORT}." >&2
    echo "Is the app running? Start it with: termtap-server (or make run)" >&2
    exit 1
}

# Parse response — last line is HTTP status code, everything before is body
HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
HTTP_BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    if [ "$(echo "$EVENT_TITLE" | tr '[:upper:]' '[:lower:]')" = "terminate" ]; then
        echo "✓ Terminal removed from menu bar"
        unset TERMINAL_FOCUS_WID
    else
        echo "✓ Event sent: ${EVENT_TITLE} — ${EVENT_MSG}"
    fi
else
    echo "Error (HTTP $HTTP_CODE): $HTTP_BODY" >&2
    exit 1
fi
