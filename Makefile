# ---------------------------------------------------------------------------
# Termtap — Makefile
#
# Targets:
#   make setup     — Create venv and install Python dependencies
#   make build     — Bundle into Termtap.app via PyInstaller
#   make install   — Copy app to /Applications + symlink CLI to /usr/local/bin
#   make uninstall — Remove app and CLI symlink
#   make run       — Quick dev run (no build, uses venv directly)
#   make clean     — Remove build artifacts
# ---------------------------------------------------------------------------

.PHONY: setup build install uninstall test run clean

VENV_DIR     := .venv
PYTHON       := $(VENV_DIR)/bin/python3
PIP          := $(VENV_DIR)/bin/pip
PYINSTALLER  := $(VENV_DIR)/bin/pyinstaller
APP_NAME     := Termtap
APP_BUNDLE   := dist/$(APP_NAME).app
INSTALL_DIR  := /Applications
CLI_NAME     := termtap
CLI_SRC      := $(CURDIR)/termtap.sh
CLI_LINK     := /usr/local/bin/$(CLI_NAME)
SERVER_LINK  := /usr/local/bin/termtap-server

# ---------------------------------------------------------------------------
# Setup — create venv and install dependencies
# ---------------------------------------------------------------------------
setup: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate:
	@echo "🔧 Creating virtual environment..."
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "✅ Setup complete"

# ---------------------------------------------------------------------------
# Build — bundle into a standalone macOS .app
# ---------------------------------------------------------------------------
build: setup
	@echo "📦 Building $(APP_NAME).app..."
	$(PYINSTALLER) \
		--name $(APP_NAME) \
		--windowed \
		--onedir \
		--noconfirm \
		--clean \
		terminal_focus.py
	@echo "✅ Build complete: $(APP_BUNDLE)"

# ---------------------------------------------------------------------------
# Install — copy app + symlink CLI
# ---------------------------------------------------------------------------
install: build
	@echo "📲 Installing $(APP_NAME)..."
	@# Copy app bundle
	@if [ -d "$(INSTALL_DIR)/$(APP_NAME).app" ]; then \
		echo "  Removing existing $(APP_NAME).app..."; \
		rm -rf "$(INSTALL_DIR)/$(APP_NAME).app"; \
	fi
	cp -R "$(APP_BUNDLE)" "$(INSTALL_DIR)/"
	@echo "  ✅ $(APP_NAME).app → $(INSTALL_DIR)/"
	@# Symlink CLI script
	@sudo mkdir -p /usr/local/bin
	sudo ln -sf "$(CLI_SRC)" "$(CLI_LINK)"
	@echo "  ✅ $(CLI_NAME) → $(CLI_LINK)"
	@# Create a launcher script for the server
	@echo '#!/bin/bash' > /tmp/termtap-server
	@echo 'open -a "$(INSTALL_DIR)/$(APP_NAME).app" --args "$$@"' >> /tmp/termtap-server
	@chmod +x /tmp/termtap-server
	@sudo mv /tmp/termtap-server "$(SERVER_LINK)"
	@echo "  ✅ termtap-server → $(SERVER_LINK)"
	@echo ""
	@echo "🎉 Installation complete!"
	@echo "   Start the app:  termtap-server"
	@echo "   Send events:    termtap \"build\" \"compiling...\""
	@echo "   Terminate:      termtap terminate"

# ---------------------------------------------------------------------------
# Uninstall — remove app and symlinks
# ---------------------------------------------------------------------------
uninstall:
	@echo "🗑  Uninstalling $(APP_NAME)..."
	rm -rf "$(INSTALL_DIR)/$(APP_NAME).app"
	sudo rm -f "$(CLI_LINK)"
	sudo rm -f "$(SERVER_LINK)"
	@echo "✅ Uninstalled"

# ---------------------------------------------------------------------------
# Test — run unit tests
# ---------------------------------------------------------------------------
test: setup
	@echo "🧪 Running tests..."
	$(PYTHON) -m pytest tests/ -v

# ---------------------------------------------------------------------------
# Run — quick dev run without building .app
# ---------------------------------------------------------------------------
run: setup
	@echo "🚀 Starting $(APP_NAME) (dev mode)..."
	$(PYTHON) terminal_focus.py $(ARGS)

# ---------------------------------------------------------------------------
# Clean — remove build artifacts
# ---------------------------------------------------------------------------
clean:
	@echo "🧹 Cleaning build artifacts..."
	rm -rf build/ dist/ *.spec $(VENV_DIR)/
	@echo "✅ Clean"
