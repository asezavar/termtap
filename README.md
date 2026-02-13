# Termtap

A macOS menu bar app that lets you track and quickly focus your Terminal.app windows. Terminals send events via a simple bash command, and the menu bar shows all active sessions — click one to bring it to the front.

## Features

- **Menu bar indicator** — shows `⚡N` when there are unseen updates, `N` otherwise
- **Bold unseen entries** — individual sessions with new updates are marked with `●`
- **One-click focus** — click a session in the dropdown to bring that Terminal window to the front
- **Simple CLI** — send events from any terminal with `termtap "title" "message"`
- **Configurable port** — defaults to `9876`, override with `--port` or `TERMINAL_FOCUS_PORT`

## Prerequisites

- macOS (Apple Silicon or Intel)
- Python 3.9+ (pre-installed on modern macOS)
- Terminal.app

## Quick Start (Dev Mode)

```bash
make run
```

This creates a virtual environment, installs dependencies, and starts the app directly.

## Install (Standalone)

```bash
make install
```

This will:
1. Create a venv and install dependencies
2. Bundle the app into `Termtap.app` via PyInstaller
3. Copy `Termtap.app` to `/Applications`
4. Symlink `termtap` CLI to `/usr/local/bin/termtap`
5. Create `termtap-server` launcher in `/usr/local/bin/`

After installation, no Python or venv needed — just use the commands.

## Usage

### Start the app

```bash
# After make install:
termtap-server

# Or in dev mode:
make run

# With custom port:
make run ARGS="--port 8888"
```

### Send events from any terminal

```bash
# Send an event (registers the terminal on first call, updates on subsequent calls)
termtap "build" "compiling project..."
termtap "deploy" "staging deploy started"
termtap "test" "42 tests passed ✅"

# Remove this terminal from the menu bar
termtap terminate
```

### Custom port

```bash
# Shell script uses TERMINAL_FOCUS_PORT env var
TERMINAL_FOCUS_PORT=8888 termtap "build" "started"
```

## Uninstall

```bash
make uninstall
```

## Makefile Targets

| Target          | Description                                       |
|-----------------|---------------------------------------------------|
| `make setup`    | Create venv and install Python dependencies       |
| `make build`    | Bundle into `Termtap.app` via PyInstaller         |
| `make install`  | Copy app to `/Applications` + symlink CLI         |
| `make uninstall`| Remove app and CLI symlinks                       |
| `make test`     | Run unit tests                                    |
| `make run`      | Quick dev run (no build, uses venv directly)      |
| `make clean`    | Remove build artifacts (venv, dist, build, spec)  |

## How It Works

1. **`terminal_focus.py`** — A `rumps`-based menu bar app with a threaded HTTP server on `127.0.0.1:9876`
2. **`termtap.sh`** — A bash script that auto-detects the Terminal.app window ID via AppleScript and sends JSON events via `curl`
3. Events are keyed by macOS window ID — first event registers, subsequent events update, `terminate` removes
4. Clicking a menu entry runs AppleScript to bring that specific Terminal.app window to the front

## Project Structure

```
├── terminal_focus.py   # Python menu bar app (rumps + HTTP + AppleScript)
├── termtap.sh          # Bash CLI for sending events
├── Makefile            # Build, install, run, clean targets
├── requirements.txt    # Python dependencies
├── tests/              # Unit tests
├── .gitignore          # Ignores venv, build artifacts
└── README.md           # This file
```
