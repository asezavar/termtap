"""Unit tests for the HTTP EventHandler."""

import json
import threading

import pytest

from http.server import HTTPServer
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from terminal_focus import SessionStore, EventHandler


@pytest.fixture
def server_and_store():
    """Start a test HTTP server with a fresh SessionStore."""
    store = SessionStore()
    EventHandler.store = store
    EventHandler.app_ref = None  # no menu bar app in tests

    server = HTTPServer(("127.0.0.1", 0), EventHandler)  # port 0 = random free port
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield store, port

    server.shutdown()


def _post(port, payload):
    """Send a POST request and return (status_code, response_body)."""
    data = json.dumps(payload).encode()
    req = Request(
        f"http://127.0.0.1:{port}/",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body


class TestEventHandlerRegister:
    """Tests for registering sessions via HTTP."""

    def test_register_new_session(self, server_and_store):
        store, port = server_and_store

        status, body = _post(port, {
            "window_id": 12345,
            "event_title": "build",
            "event_msg": "started",
        })

        assert status == 200
        assert body["status"] == "registered"
        assert store.count() == 1

    def test_register_updates_existing(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "started"})
        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "done"})

        assert store.count() == 1
        sessions = store.get_all()
        assert sessions["12345"]["event_msg"] == "done"

    def test_register_multiple_sessions(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 100, "event_title": "build", "event_msg": "a"})
        _post(port, {"window_id": 200, "event_title": "deploy", "event_msg": "b"})
        _post(port, {"window_id": 300, "event_title": "test", "event_msg": "c"})

        assert store.count() == 3


class TestEventHandlerTerminate:
    """Tests for terminating sessions via HTTP."""

    def test_terminate_removes_session(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "started"})
        status, body = _post(port, {"window_id": 12345, "event_title": "terminate", "event_msg": ""})

        assert status == 200
        assert body["status"] == "removed"
        assert store.count() == 0

    def test_terminate_case_insensitive(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "started"})
        _post(port, {"window_id": 12345, "event_title": "Terminate", "event_msg": ""})

        assert store.count() == 0

    def test_terminate_nonexistent_is_ok(self, server_and_store):
        store, port = server_and_store

        status, body = _post(port, {"window_id": 99999, "event_title": "terminate", "event_msg": ""})

        assert status == 200
        assert body["status"] == "removed"


class TestEventHandlerValidation:
    """Tests for input validation."""

    def test_missing_window_id(self, server_and_store):
        _, port = server_and_store

        status, body = _post(port, {"event_title": "build", "event_msg": "started"})

        assert status == 400
        assert "error" in body

    def test_missing_event_title(self, server_and_store):
        _, port = server_and_store

        status, body = _post(port, {"window_id": 12345, "event_msg": "started"})

        assert status == 400
        assert "error" in body

    def test_non_numeric_window_id(self, server_and_store):
        _, port = server_and_store

        status, body = _post(port, {
            "window_id": "abc",
            "event_title": "build",
            "event_msg": "started",
        })

        assert status == 400
        assert "numeric" in body["error"]

    def test_invalid_json(self, server_and_store):
        _, port = server_and_store

        data = b"not json at all"
        req = Request(
            f"http://127.0.0.1:{port}/",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req) as resp:
                status = resp.status
                body = json.loads(resp.read().decode())
        except HTTPError as e:
            status = e.code
            body = json.loads(e.read().decode())

        assert status == 400
        assert "Invalid JSON" in body["error"]

    def test_empty_body(self, server_and_store):
        _, port = server_and_store

        data = b""
        req = Request(
            f"http://127.0.0.1:{port}/",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req) as resp:
                status = resp.status
        except HTTPError as e:
            status = e.code

        assert status == 400

    def test_empty_event_msg_is_allowed(self, server_and_store):
        store, port = server_and_store

        status, body = _post(port, {
            "window_id": 12345,
            "event_title": "build",
            "event_msg": "",
        })

        assert status == 200
        assert store.count() == 1


class TestEventHandlerUnseenState:
    """Tests for unseen flag behavior through HTTP."""

    def test_new_session_is_unseen(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "started"})

        assert store.has_unseen() is True

    def test_update_marks_unseen_again(self, server_and_store):
        store, port = server_and_store

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "started"})
        store.mark_all_seen()
        assert store.has_unseen() is False

        _post(port, {"window_id": 12345, "event_title": "build", "event_msg": "done"})
        assert store.has_unseen() is True
