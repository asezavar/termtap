"""Unit tests for SessionStore."""

import threading

import pytest

from terminal_focus import SessionStore


class TestSessionStoreUpsert:
    """Tests for registering and updating sessions."""

    def test_upsert_adds_new_session(self):
        store = SessionStore()
        store.upsert("123", "build", "started")

        sessions = store.get_all()
        assert "123" in sessions
        assert sessions["123"]["event_title"] == "build"
        assert sessions["123"]["event_msg"] == "started"
        assert sessions["123"]["unseen"] is True

    def test_upsert_updates_existing_session(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        store.upsert("123", "build", "completed")

        sessions = store.get_all()
        assert len(sessions) == 1
        assert sessions["123"]["event_msg"] == "completed"
        assert sessions["123"]["unseen"] is True

    def test_upsert_multiple_sessions(self):
        store = SessionStore()
        store.upsert("100", "build", "started")
        store.upsert("200", "deploy", "staging")
        store.upsert("300", "test", "running")

        assert store.count() == 3

    def test_upsert_marks_unseen_after_mark_all_seen(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        store.mark_all_seen()
        assert store.has_unseen() is False

        store.upsert("123", "build", "done")
        assert store.has_unseen() is True


class TestSessionStoreRemove:
    """Tests for removing sessions."""

    def test_remove_existing_session(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        store.remove("123")

        assert store.count() == 0
        assert "123" not in store.get_all()

    def test_remove_nonexistent_session_is_noop(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        store.remove("999")  # should not raise

        assert store.count() == 1

    def test_double_remove_is_noop(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        store.remove("123")
        store.remove("123")  # should not raise

        assert store.count() == 0


class TestSessionStoreMarkAllSeen:
    """Tests for marking sessions as seen."""

    def test_mark_all_seen(self):
        store = SessionStore()
        store.upsert("100", "build", "started")
        store.upsert("200", "deploy", "staging")

        assert store.has_unseen() is True

        store.mark_all_seen()

        assert store.has_unseen() is False
        sessions = store.get_all()
        for session in sessions.values():
            assert session["unseen"] is False

    def test_mark_all_seen_empty_store(self):
        store = SessionStore()
        store.mark_all_seen()  # should not raise
        assert store.has_unseen() is False


class TestSessionStoreHasUnseen:
    """Tests for unseen detection."""

    def test_no_unseen_when_empty(self):
        store = SessionStore()
        assert store.has_unseen() is False

    def test_has_unseen_after_upsert(self):
        store = SessionStore()
        store.upsert("123", "build", "started")
        assert store.has_unseen() is True

    def test_partial_unseen(self):
        store = SessionStore()
        store.upsert("100", "build", "started")
        store.upsert("200", "deploy", "staging")
        store.mark_all_seen()

        # Only update one session
        store.upsert("100", "build", "done")

        assert store.has_unseen() is True
        sessions = store.get_all()
        assert sessions["100"]["unseen"] is True
        assert sessions["200"]["unseen"] is False


class TestSessionStoreCount:
    """Tests for session counting."""

    def test_count_empty(self):
        store = SessionStore()
        assert store.count() == 0

    def test_count_after_upserts(self):
        store = SessionStore()
        store.upsert("100", "a", "b")
        store.upsert("200", "c", "d")
        assert store.count() == 2

    def test_count_after_remove(self):
        store = SessionStore()
        store.upsert("100", "a", "b")
        store.upsert("200", "c", "d")
        store.remove("100")
        assert store.count() == 1


class TestSessionStoreGetAll:
    """Tests for get_all snapshot behavior."""

    def test_get_all_returns_copy(self):
        store = SessionStore()
        store.upsert("123", "build", "started")

        snapshot = store.get_all()
        snapshot["123"]["event_msg"] = "MODIFIED"

        # Original should be unchanged
        assert store.get_all()["123"]["event_msg"] == "started"


class TestSessionStoreThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_upserts(self):
        store = SessionStore()
        errors = []

        def upsert_many(start_id, count):
            try:
                for i in range(count):
                    store.upsert(str(start_id + i), "event", f"msg-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=upsert_many, args=(0, 100)),
            threading.Thread(target=upsert_many, args=(1000, 100)),
            threading.Thread(target=upsert_many, args=(2000, 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert store.count() == 300

    def test_concurrent_upsert_and_remove(self):
        store = SessionStore()
        errors = []

        def upsert_loop():
            try:
                for i in range(100):
                    store.upsert(str(i), "event", f"msg-{i}")
            except Exception as e:
                errors.append(e)

        def remove_loop():
            try:
                for i in range(100):
                    store.remove(str(i))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=upsert_loop)
        t2 = threading.Thread(target=remove_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0
