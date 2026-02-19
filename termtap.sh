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

# --- Resolve the TTY for the current terminal session ---
# If stdin is not a TTY (e.g., running as a hook from another CLI),
# walk up the process tree to find an ancestor with a TTY.
resolve_tty() {
    # Try stdin first
    local current_tty
    current_tty=$(tty 2>/dev/null) || true

    if [ -n "$current_tty" ] && [ "$current_tty" != "not a tty" ]; then
        echo "$current_tty"
        return
    fi

    # Walk up the process tree to find an ancestor with a TTY
    local pid=$$
    while [ "$pid" -gt 1 ] 2>/dev/null; do
        # Get the controlling TTY for this PID via ps
        local ancestor_tty
        ancestor_tty=$(ps -o tty= -p "$pid" 2>/dev/null | tr -d ' ')

        if [ -n "$ancestor_tty" ] && [ "$ancestor_tty" != "??" ] && [ "$ancestor_tty" != "-" ]; then
            echo "/dev/$ancestor_tty"
            return
        fi

        # Move to parent PID
        local ppid
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
        if [ -z "$ppid" ] || [ "$ppid" = "$pid" ]; then
            break
        fi
        pid="$ppid"
    done

    echo ""
}

CURRENT_TTY=$(resolve_tty)

if [ -z "$CURRENT_TTY" ]; then
    echo "Error: Could not determine terminal TTY." >&2
    echo "Make sure you are running this from a terminal." >&2
    exit 1
fi

# --- Get the window ID of the current Terminal.app window ---
# Uses the resolved TTY to find the correct window, even if it's not frontmost.
get_window_id() {
    local wid
    wid=$(osascript -e "
        set currentTTY to \"$CURRENT_TTY\"
        tell application \"Terminal\"
            repeat with w in windows
                repeat with t in tabs of w
                    if tty of t is currentTTY then
                        return id of w
                    end if
                end repeat
            end repeat
        end tell
        return \"\"
    " 2>/dev/null)

    if [ -z "$wid" ]; then
        echo "Error: Could not find a Terminal.app window matching TTY $CURRENT_TTY." >&2
        echo "Make sure you are running this from Terminal.app." >&2
        exit 1
    fi
    echo "$wid"
}

# --- Cache the window ID in a temp file keyed by TTY ---
# This persists across script invocations (unlike env vars in a subshell).
CACHE_DIR="${TMPDIR:-/tmp}/termtap"
mkdir -p "$CACHE_DIR"

get_cache_file() {
    # Convert tty path to a safe filename (e.g., /dev/ttys003 -> dev-ttys003)
    local safe_name
    safe_name=$(echo "$CURRENT_TTY" | sed 's|/|-|g; s|^-||')
    echo "${CACHE_DIR}/${safe_name}"
}

CACHE_FILE=$(get_cache_file)

if [ -f "$CACHE_FILE" ]; then
    WINDOW_ID=$(cat "$CACHE_FILE")
else
    WINDOW_ID=$(get_window_id)
    echo "$WINDOW_ID" > "$CACHE_FILE"
fi

# --- Build JSON payload safely ---
# Escape backslashes, double quotes, and control characters for valid JSON.
json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"      # escape backslashes
    s="${s//\"/\\\"}"      # escape double quotes
    printf '%s' "$s"
}

PAYLOAD=$(printf '{"window_id":"%s","event_title":"%s","event_msg":"%s"}' \
    "$(json_escape "$WINDOW_ID")" \
    "$(json_escape "$EVENT_TITLE")" \
    "$(json_escape "$EVENT_MSG")")

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
        rm -f "$CACHE_FILE"
    else
        echo "✓ Event sent: ${EVENT_TITLE} — ${EVENT_MSG}"
    fi
else
    echo "Error (HTTP $HTTP_CODE): $HTTP_BODY" >&2
    exit 1
fi
