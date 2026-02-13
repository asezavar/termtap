#!/usr/bin/env python3
"""
Terminal Focus — macOS Menu Bar App PoC

A menu bar app that lets you register Terminal.app windows and quickly
bring them to focus. Terminals send events via HTTP to this app, which
displays them in the macOS system menu bar.

Events: { window_id, event_title, event_msg }
Special event_title "terminate" removes the session from the list.
"""

import argparse
import json
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import rumps
import objc
from AppKit import NSAttributedString, NSFont, NSFontManager


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HTTP_PORT = 9876
ICON_NORMAL = "🖥"
ICON_UNSEEN = "⚡"


# ---------------------------------------------------------------------------
# Session store (thread-safe)
# ---------------------------------------------------------------------------
class SessionStore:
    """Thread-safe store for terminal sessions."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}  # window_id -> {event_title, event_msg, unseen}

    def upsert(self, window_id: str, event_title: str, event_msg: str):
        """Register or update a terminal session."""
        with self._lock:
            self._sessions[window_id] = {
                "event_title": event_title,
                "event_msg": event_msg,
                "unseen": True,
            }

    def remove(self, window_id: str):
        """Remove a terminal session."""
        with self._lock:
            self._sessions.pop(window_id, None)

    def mark_all_seen(self):
        """Mark all sessions as seen."""
        with self._lock:
            for session in self._sessions.values():
                session["unseen"] = False

    def get_all(self):
        """Return a deep snapshot of all sessions."""
        with self._lock:
            return {k: dict(v) for k, v in self._sessions.items()}

    def has_unseen(self):
        """Check if any session has unseen updates."""
        with self._lock:
            return any(s["unseen"] for s in self._sessions.values())

    def count(self):
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------
class EventHandler(BaseHTTPRequestHandler):
    """Handles incoming events from terminal sessions."""

    store: SessionStore = None  # set before server starts
    app_ref = None  # reference to the rumps app for menu refresh

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            window_id = str(data.get("window_id", "")).strip()
            event_title = str(data.get("event_title", "")).strip()
            event_msg = str(data.get("event_msg", "")).strip()

            if not window_id or not event_title:
                self._respond(400, {"error": "window_id and event_title are required"})
                return

            # Validate window_id is numeric (for AppleScript safety)
            if not window_id.isdigit():
                self._respond(400, {"error": "window_id must be a numeric value"})
                return

            if event_title.lower() == "terminate":
                self.store.remove(window_id)
                self._respond(200, {"status": "removed", "window_id": window_id})
            else:
                self.store.upsert(window_id, event_title, event_msg)
                self._respond(200, {"status": "registered", "window_id": window_id})

            # Trigger menu refresh on the main thread
            if self.app_ref:
                self.app_ref.schedule_refresh()

        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status_code, body):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        # Suppress default logging to stderr
        pass


# ---------------------------------------------------------------------------
# AppleScript helpers
# ---------------------------------------------------------------------------
def focus_terminal_window(window_id: str):
    """Bring a specific Terminal.app window to the front using AppleScript."""
    script = f'''
        tell application "Terminal"
            activate
            set targetWindow to missing value
            repeat with w in windows
                if id of w is {window_id} then
                    set targetWindow to w
                    exit repeat
                end if
            end repeat
            if targetWindow is not missing value then
                set index of targetWindow to 1
            end if
        end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except (subprocess.TimeoutExpired, Exception):
        pass


# ---------------------------------------------------------------------------
# Menu bar app
# ---------------------------------------------------------------------------
class TerminalFocusApp(rumps.App):
    """macOS menu bar app for terminal session management."""

    def __init__(self, store: SessionStore):
        super().__init__("0", quit_button=None)
        self.store = store
        self._refresh_lock = threading.Lock()
        self._dirty = threading.Event()  # signals that a refresh is needed
        self._session_keys = []  # track current menu item keys for cleanup

    def schedule_refresh(self):
        """Signal that a menu refresh is needed (called from HTTP thread)."""
        self._dirty.set()

    @rumps.timer(0.5)
    def _poll_for_updates(self, timer):
        """Polling timer on the main thread — checks if a refresh is needed."""
        if self._dirty.is_set():
            self._dirty.clear()
            self._rebuild_menu()

    def _rebuild_menu(self):
        """Rebuild the entire menu from the session store."""
        with self._refresh_lock:
            sessions = self.store.get_all()
            count = len(sessions)
            has_unseen = self.store.has_unseen()

            # Update title
            if has_unseen:
                self.title = f"{ICON_UNSEEN}{count}"
            else:
                self.title = f"{ICON_NORMAL}{count}"

            # Remove old session items
            for key in self._session_keys:
                try:
                    del self.menu[key]
                except KeyError:
                    pass
            self._session_keys = []

            # Build new menu from scratch
            self.menu.clear()

            if not sessions:
                item = rumps.MenuItem("No active terminals")
                self.menu.add(item)
                self._session_keys.append("No active terminals")
            else:
                for wid, info in sessions.items():
                    label = f"{info['event_title']}"
                    if info["event_msg"]:
                        label += f" — {info['event_msg']}"

                    if info["unseen"]:
                        label = f"● {label}"

                    item = rumps.MenuItem(label, callback=self._make_click_handler(wid))
                    self.menu.add(item)
                    self._session_keys.append(label)

            # Add separator and quit
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem("Quit", callback=self._quit))

    def _make_click_handler(self, window_id):
        """Create a click handler for a specific window."""
        def handler(sender):
            focus_terminal_window(window_id)
            # Mark all as seen when user interacts
            self.store.mark_all_seen()
            self._rebuild_menu()
        return handler

    def _quit(self, sender):
        rumps.quit_application()

    # -- Override to detect menu open via PyObjC delegate --
    # rumps doesn't natively expose "menu opened" so we hook into it
    def _nsapp_delegate_menuWillOpen_(self, menu):
        """Called when the menu bar dropdown is opened."""
        self.store.mark_all_seen()
        self._rebuild_menu()


# ---------------------------------------------------------------------------
# PyObjC delegate mixin for menu-will-open detection
# ---------------------------------------------------------------------------
def patch_menu_delegate(app):
    """
    Patch the rumps app's status bar menu to detect when it opens,
    so we can mark all sessions as seen.
    """
    try:
        status_item = app._status_bar
        menu = status_item.menu()

        # Create a delegate class dynamically
        MenuDelegate = objc.lookUpClass("NSObject")

        class MenuOpenDelegate(MenuDelegate):
            app_ref = None

            def menuWillOpen_(self, menu):
                if self.app_ref:
                    self.app_ref.store.mark_all_seen()
                    self.app_ref._rebuild_menu()

        delegate = MenuOpenDelegate.alloc().init()
        delegate.app_ref = app
        menu.setDelegate_(delegate)
        # Keep a strong reference so it's not garbage collected
        app._menu_delegate = delegate
    except Exception as e:
        print(f"Warning: Could not patch menu delegate: {e}")
        print("Unseen indicators will be cleared on item click instead.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Terminal Focus — macOS Menu Bar App")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=HTTP_PORT,
        help=f"HTTP port to listen on (default: {HTTP_PORT})",
    )
    args = parser.parse_args()
    port = args.port

    store = SessionStore()

    # Configure the HTTP handler with the shared store
    EventHandler.store = store

    # Create the app
    app = TerminalFocusApp(store)
    EventHandler.app_ref = app

    # Start HTTP server in background thread
    server = HTTPServer(("127.0.0.1", port), EventHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Terminal Focus listening on http://127.0.0.1:{port}")

    # Run the menu bar app (blocks)
    # We use a timer to patch the delegate after the app has initialized
    def _patch_after_start(timer):
        timer.stop()
        patch_menu_delegate(app)

    rumps.Timer(_patch_after_start, 0.5).start()
    app.run()


if __name__ == "__main__":
    main()
