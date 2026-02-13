"""Unit tests for focus_terminal_window (mocked)."""

from unittest.mock import patch, call

import pytest

from terminal_focus import focus_terminal_window


class TestFocusTerminalWindow:
    """Tests for AppleScript window focusing."""

    @patch("terminal_focus.subprocess.run")
    def test_calls_osascript(self, mock_run):
        focus_terminal_window("12345")

        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0][0] == "osascript"
        assert args[0][0][1] == "-e"
        assert "12345" in args[0][0][2]

    @patch("terminal_focus.subprocess.run")
    def test_script_contains_window_id(self, mock_run):
        focus_terminal_window("67890")

        script = mock_run.call_args[0][0][2]
        assert "67890" in script
        assert "Terminal" in script
        assert "activate" in script

    @patch("terminal_focus.subprocess.run")
    def test_script_sets_window_index(self, mock_run):
        focus_terminal_window("12345")

        script = mock_run.call_args[0][0][2]
        assert "set index" in script
        assert "set targetWindow" in script

    @patch("terminal_focus.subprocess.run")
    def test_timeout_is_set(self, mock_run):
        focus_terminal_window("12345")

        kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 5

    @patch("terminal_focus.subprocess.run", side_effect=Exception("osascript failed"))
    def test_exception_is_suppressed(self, mock_run):
        # Should not raise
        focus_terminal_window("12345")

    @patch("terminal_focus.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="osascript", timeout=5))
    def test_timeout_is_suppressed(self, mock_run):
        # Should not raise
        focus_terminal_window("12345")
