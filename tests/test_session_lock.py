"""
tests/test_session_lock.py — Unit tests for session locking in api/session_store.py

Tests:
- acquire_lock / release_lock / get_lock_holder logic
- Expired session holders are evicted before new lock is granted
- create_session acquires lock; close_session releases it
- Concurrent open attempt via HTTP returns 409
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import api.session_store as store
from api.session_store import (
    acquire_lock,
    release_lock,
    get_lock_holder,
    create_session,
    close_session,
    get_session,
    Session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOKEN_A = "0.0.11111"
TOKEN_B = "0.0.22222"
SESSION_A = "session-aaa"
SESSION_B = "session-bbb"

FAKE_KEY = b"\x01" * 32


def _insert_active_session(token_id: str, session_id: str, expired: bool = False) -> Session:
    """Insert a mock Session directly into the store for isolation testing."""
    now = datetime.now(timezone.utc)
    expires = now - timedelta(hours=1) if expired else now + timedelta(hours=4)
    session = Session(
        session_id=session_id,
        token_id=token_id,
        serial=1,
        section_key=bytearray(FAKE_KEY),
        index_key=bytearray(FAKE_KEY),
        index_file_id="0.0.idx",
        full_section_ids={},
        start_hashes={},
        sections_loaded=[],
        context_sections={},
        created_at=now,
        expires_at=expires,
    )
    store._store[session_id] = session
    return session


@pytest.fixture(autouse=True)
def clean_store():
    """Reset store and locks before and after every test."""
    store._store.clear()
    store._locks.clear()
    yield
    store._store.clear()
    store._locks.clear()


# ---------------------------------------------------------------------------
# acquire_lock
# ---------------------------------------------------------------------------

class TestAcquireLock:
    def test_first_acquire_succeeds(self):
        assert acquire_lock(TOKEN_A, SESSION_A) is True
        assert store._locks[TOKEN_A] == SESSION_A

    def test_second_acquire_same_token_fails(self):
        _insert_active_session(TOKEN_A, SESSION_A)
        store._locks[TOKEN_A] = SESSION_A

        assert acquire_lock(TOKEN_A, SESSION_B) is False

    def test_second_acquire_different_token_succeeds(self):
        _insert_active_session(TOKEN_A, SESSION_A)
        store._locks[TOKEN_A] = SESSION_A

        assert acquire_lock(TOKEN_B, SESSION_B) is True

    def test_expired_holder_evicted_new_acquires(self):
        _insert_active_session(TOKEN_A, SESSION_A, expired=True)
        store._locks[TOKEN_A] = SESSION_A

        result = acquire_lock(TOKEN_A, SESSION_B)
        assert result is True
        assert store._locks[TOKEN_A] == SESSION_B
        assert SESSION_A not in store._store  # evicted

    def test_stale_lock_no_session_cleared_and_acquired(self):
        # Lock table has an entry but session was already evicted
        store._locks[TOKEN_A] = SESSION_A  # no matching session in _store

        result = acquire_lock(TOKEN_A, SESSION_B)
        assert result is True
        assert store._locks[TOKEN_A] == SESSION_B


# ---------------------------------------------------------------------------
# release_lock
# ---------------------------------------------------------------------------

class TestReleaseLock:
    def test_release_by_holder_clears_lock(self):
        store._locks[TOKEN_A] = SESSION_A
        release_lock(TOKEN_A, SESSION_A)
        assert TOKEN_A not in store._locks

    def test_release_by_non_holder_is_noop(self):
        store._locks[TOKEN_A] = SESSION_A
        release_lock(TOKEN_A, SESSION_B)  # wrong session
        assert store._locks[TOKEN_A] == SESSION_A  # unchanged

    def test_release_unlocked_token_is_noop(self):
        release_lock(TOKEN_A, SESSION_A)  # no lock exists — should not raise


# ---------------------------------------------------------------------------
# get_lock_holder
# ---------------------------------------------------------------------------

class TestGetLockHolder:
    def test_returns_session_id_when_locked(self):
        store._locks[TOKEN_A] = SESSION_A
        assert get_lock_holder(TOKEN_A) == SESSION_A

    def test_returns_none_when_not_locked(self):
        assert get_lock_holder(TOKEN_A) is None


# ---------------------------------------------------------------------------
# create_session acquires lock; close_session releases it
# ---------------------------------------------------------------------------

class TestSessionLifecycleLocking:
    def test_create_session_acquires_lock(self):
        session = create_session(
            token_id=TOKEN_A,
            serial=1,
            context_sections={"harness": b"hi"},
            section_key=FAKE_KEY,
            index_key=FAKE_KEY,
            index_file_id="0.0.idx",
            full_section_ids={},
        )
        assert store._locks[TOKEN_A] == session.session_id

    def test_close_session_releases_lock(self):
        session = create_session(
            token_id=TOKEN_A,
            serial=1,
            context_sections={"harness": b"hi"},
            section_key=FAKE_KEY,
            index_key=FAKE_KEY,
            index_file_id="0.0.idx",
            full_section_ids={},
        )
        close_session(session.session_id)
        assert TOKEN_A not in store._locks

    def test_create_second_session_raises_when_first_active(self):
        create_session(
            token_id=TOKEN_A,
            serial=1,
            context_sections={"harness": b"hi"},
            section_key=FAKE_KEY,
            index_key=FAKE_KEY,
            index_file_id="0.0.idx",
            full_section_ids={},
        )
        with pytest.raises(ValueError, match="already locked"):
            create_session(
                token_id=TOKEN_A,
                serial=2,
                context_sections={"harness": b"hi"},
                section_key=FAKE_KEY,
                index_key=FAKE_KEY,
                index_file_id="0.0.idx",
                full_section_ids={},
            )

    def test_keys_zeroed_after_close(self):
        session = create_session(
            token_id=TOKEN_A,
            serial=1,
            context_sections={"harness": b"some content"},
            section_key=FAKE_KEY,
            index_key=FAKE_KEY,
            index_file_id="0.0.idx",
            full_section_ids={},
        )
        key_len = len(session.section_key)
        close_session(session.session_id)
        assert all(b == 0 for b in session.section_key)
        assert all(b == 0 for b in session.index_key)

    def test_context_cleared_after_close(self):
        session = create_session(
            token_id=TOKEN_A,
            serial=1,
            context_sections={"harness": b"secret content"},
            section_key=FAKE_KEY,
            index_key=FAKE_KEY,
            index_file_id="0.0.idx",
            full_section_ids={},
        )
        close_session(session.session_id)
        assert session.context_sections == {}


# ---------------------------------------------------------------------------
# HTTP-level: concurrent open returns 409
# ---------------------------------------------------------------------------

class TestConcurrentSessionHttp:
    def test_second_open_returns_409(self):
        """
        When a vault has an active session, a second /session/open for the same
        token_id must return 409 Conflict.
        """
        from api.main import app
        client = TestClient(app)

        TOKEN = "0.0.77777"

        # Pre-install an active session + lock for this token
        _insert_active_session(TOKEN, "existing-session-id")
        store._locks[TOKEN] = "existing-session-id"

        # Attempt to open a second session — should hit the 409 check in session.py
        with patch("api.routes.session.get_lock_holder", return_value="existing-session-id"):
            resp = client.post(
                "/session/open",
                json={
                    "token_id": TOKEN,
                    "passphrase": "test-passphrase-long-enough",
                    "serial": 1,
                },
            )

        assert resp.status_code == 409
        assert "active session" in resp.json()["detail"].lower()
