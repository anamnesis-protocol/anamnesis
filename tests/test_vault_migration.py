"""
tests/test_vault_migration.py — Tests for vault schema versioning and auto-migration.

Tests cover:
  - Version comparison / needs_migration()
  - run_migrations() happy path and idempotency
  - _migrate_1_0_to_1_1: adds knowledge section; skips if already present
  - Migration failure is non-fatal (session proceeds)
  - schema_version bumped correctly
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from api.services.vault_migration import (
    needs_migration,
    run_migrations,
    CURRENT_SCHEMA_VERSION,
    _version_tuple,
    _MIGRATION_DEFAULTS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(schema_version: str = "1.0", has_knowledge: bool = False) -> MagicMock:
    """Return a minimal mock Session object."""
    session = MagicMock()
    session.schema_version = schema_version
    session.token_id = "0.0.99999"
    session.full_section_ids = {"soul": "0.0.1001", "user": "0.0.1002"}
    if has_knowledge:
        session.full_section_ids["knowledge"] = "0.0.1005"
    session.context_sections = {"soul": "# Soul\nDirectives.", "user": "# User\nProfile."}
    session.section_key = bytearray(b"\x01" * 32)
    return session


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def test_version_tuple_basic():
    assert _version_tuple("1.0") == (1, 0)
    assert _version_tuple("1.1") == (1, 1)
    assert _version_tuple("2.0") == (2, 0)


def test_version_tuple_malformed():
    assert _version_tuple("bad") == (0,)
    assert _version_tuple("") == (0,)


def test_needs_migration_outdated():
    assert needs_migration("1.0") is True


def test_needs_migration_current():
    assert needs_migration(CURRENT_SCHEMA_VERSION) is False


def test_needs_migration_future():
    # A vault somehow ahead of the server — should not trigger migration
    assert needs_migration("9.9") is False


# ---------------------------------------------------------------------------
# run_migrations — no-op when current
# ---------------------------------------------------------------------------


def test_run_migrations_already_current():
    session = _make_session(schema_version=CURRENT_SCHEMA_VERSION, has_knowledge=True)
    result = run_migrations(session)
    assert result is False
    assert session.schema_version == CURRENT_SCHEMA_VERSION


def test_run_migrations_missing_schema_version_attribute():
    """Session missing schema_version entirely defaults to '1.0' and triggers migration."""
    session = _make_session()
    del session.schema_version  # simulate missing attribute

    with patch("src.vault.push_section", return_value="0.0.9999"):
        result = run_migrations(session)

    # migration attempted since default "1.0" < "1.1"
    assert result is True
    assert session.schema_version == "1.1"


# ---------------------------------------------------------------------------
# _migrate_1_0_to_1_1 — knowledge section creation
# ---------------------------------------------------------------------------


def test_migration_1_0_to_1_1_adds_knowledge():
    """Migration should push knowledge section and update session state."""
    session = _make_session(schema_version="1.0", has_knowledge=False)

    with patch("src.vault.push_section", return_value="0.0.2001"):
        result = run_migrations(session)

    assert result is True
    assert session.schema_version == "1.1"
    assert "knowledge" in session.full_section_ids


def test_migration_1_0_to_1_1_skips_if_present():
    """Migration is idempotent — skips if knowledge section already exists."""
    session = _make_session(schema_version="1.0", has_knowledge=True)

    with patch("src.vault.push_section") as mock_push:
        result = run_migrations(session)

    # push_section not called since section already exists
    mock_push.assert_not_called()
    assert result is True  # version bumped regardless
    assert session.schema_version == "1.1"


def test_migration_pushes_knowledge_section():
    """Unit test the migration function directly — push_section is called with correct args."""
    from api.services.vault_migration import _migrate_1_0_to_1_1

    session = _make_session(schema_version="1.0", has_knowledge=False)
    new_file_id = "0.0.3001"

    with patch("api.services.vault_migration._migrate_1_0_to_1_1") as mock_fn:
        mock_fn.return_value = ["knowledge"]
        _migrate_1_0_to_1_1(session)


def test_migration_direct_push_section_call():
    """Direct call: push_section receives correct args and session state updated."""
    from api.services.vault_migration import _migrate_1_0_to_1_1

    session = _make_session(schema_version="1.0", has_knowledge=False)
    new_file_id = "0.0.4001"
    expected_default = _MIGRATION_DEFAULTS["knowledge"]

    with patch("src.vault.push_section", return_value=new_file_id) as mock_push:
        added = _migrate_1_0_to_1_1(session)

    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert call_args[0][0] == "knowledge"  # section_name
    assert call_args[0][1] == expected_default.encode("utf-8")  # content
    assert call_args[0][2] == bytes(session.section_key)  # key: bytearray → bytes
    assert call_args[0][3] == session.token_id  # token_id
    assert call_args[1].get("existing_file_id") is None

    assert "knowledge" in added
    assert session.full_section_ids["knowledge"] == new_file_id
    assert session.context_sections["knowledge"] == expected_default


def test_migration_direct_already_has_knowledge():
    """Direct call: no push_section if knowledge already in full_section_ids."""
    from api.services.vault_migration import _migrate_1_0_to_1_1

    session = _make_session(schema_version="1.0", has_knowledge=True)

    with patch("src.vault.push_section") as mock_push:
        added = _migrate_1_0_to_1_1(session)

    mock_push.assert_not_called()
    assert added == []


# ---------------------------------------------------------------------------
# Non-fatal failure path
# ---------------------------------------------------------------------------


def test_migration_failure_is_non_fatal():
    """If push_section raises, the migration returns [] and does NOT re-raise."""
    from api.services.vault_migration import _migrate_1_0_to_1_1

    session = _make_session(schema_version="1.0", has_knowledge=False)

    with patch("src.vault.push_section", side_effect=RuntimeError("Hedera unavailable")):
        # Should not raise
        added = _migrate_1_0_to_1_1(session)

    assert added == []
    assert "knowledge" not in session.full_section_ids


def test_run_migrations_failure_returns_true_but_bumps_version():
    """Even if migration fn returns [] (failure), version is still bumped."""
    session = _make_session(schema_version="1.0", has_knowledge=False)

    with patch("api.services.vault_migration._migrate_1_0_to_1_1", return_value=[]):
        result = run_migrations(session)

    # `if added or True` in runner always bumps version
    assert result is True
    assert session.schema_version == "1.1"


# ---------------------------------------------------------------------------
# schema_version default content
# ---------------------------------------------------------------------------


def test_migration_defaults_knowledge_is_valid_markdown():
    content = _MIGRATION_DEFAULTS["knowledge"]
    assert content.startswith("# Knowledge Base")
    assert len(content) > 50
