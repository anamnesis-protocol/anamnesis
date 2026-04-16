"""
tests/test_api_vault.py — Unit tests for the dir bundle vault API.

Tests are structured so Hedera I/O (HFS, HCS) is mocked.
Crypto and session store logic runs for real.

Covers:
- POST /vault/bundle: push a new bundle → 200, file_id returned
- POST /vault/bundle: push update to same bundle → update_context path
- POST /vault/bundle: invalid bundle_name → 422
- POST /vault/bundle: nonexistent session_id → 404
- POST /vault/bundle: empty files → 422
- GET /vault/bundles: returns bundle names from session index
- GET /vault/bundle/{name}: pull bundle content → files dict matches
- GET /vault/bundle/{name}: pull nonexistent bundle → 404
"""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.session_store import _store, Session
from src.crypto import derive_key, compress
from src.vault import bundle_from_dict

client = TestClient(app)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_ID = "0.0.77777"
WALLET_SIG = b"\xde\xad\xbe\xef" * 16  # 64-byte fake sig
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"

_SECTION_KEY = derive_key(TOKEN_ID, WALLET_SIG, info=_INFO_SECTION)
_INDEX_KEY = derive_key(TOKEN_ID, WALLET_SIG, info=_INFO_INDEX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str, extra_section_ids: dict | None = None) -> Session:
    """Insert a live session directly into the store (bypasses open flow)."""
    now = datetime.now(timezone.utc)
    full_ids = {"soul": "0.0.1001", "user": "0.0.1002"}
    if extra_section_ids:
        full_ids.update(extra_section_ids)

        session = Session(
            session_id=session_id,
            token_id=TOKEN_ID,
            serial=1,
            section_key=bytearray(_SECTION_KEY),
            index_key=bytearray(_INDEX_KEY),
            index_file_id="0.0.9000",
            full_section_ids=full_ids,
            start_hashes={"soul": "abc", "user": "def"},
            sections_loaded=["soul", "user"],
            context_sections={"soul": "# SOUL", "user": "# USER"},
            created_at=now,
            expires_at=now + timedelta(hours=4),
        )
        _store[session_id] = session
        return session

    def _bundle_aad(bundle_name: str, token_id: str) -> bytes:
        """Mirror of vault.py _bundle_aad — must match exactly."""
        full = f"dir:{bundle_name}"
        return f"dir:{full}:{token_id}".encode("utf-8")

        # ---------------------------------------------------------------------------
        # POST /vault/bundle — push new bundle
        # ---------------------------------------------------------------------------

        class TestBundlePush:
            SID = "bundle-push-session-001"

            def setup_method(self):
                _store.clear()
                _make_session(self.SID)

                def teardown_method(self):
                    _store.clear()

                    def test_push_new_bundle_success(self):
                        new_file_id = "0.0.5001"
                        with (
                            patch(
                                "api.routes.vault.store_context", return_value=new_file_id
                            ) as mock_store,
                            patch("api.routes.vault.log_event"),
                        ):
                            resp = client.post(
                                "/vault/bundle",
                                json={
                                    "session_id": self.SID,
                                    "bundle_name": "sessions",
                                    "files": {
                                        "2026-03-17-session.md": "# Session\nWorked on vault bundles.",
                                        "2026-03-18-session.md": "# Session\nFixed chunking bug.",
                                    },
                                },
                            )

                            assert resp.status_code == 200, resp.text
                            body = resp.json()
                            assert body["bundle_name"] == "sessions"
                            assert body["file_id"] == new_file_id
                            assert body["files_stored"] == 2
                            mock_store.assert_called_once()

                        def test_push_new_bundle_updates_session_ids(self):
                            """file_id should be recorded in session.full_section_ids after push."""
                            new_file_id = "0.0.5002"
                            with (
                                patch("api.routes.vault.store_context", return_value=new_file_id),
                                patch("api.routes.vault.log_event"),
                            ):
                                resp = client.post(
                                    "/vault/bundle",
                                    json={
                                        "session_id": self.SID,
                                        "bundle_name": "projects",
                                        "files": {"project-alpha.md": "# Alpha\nDetails."},
                                    },
                                )

                                assert resp.status_code == 200
                                session = _store[self.SID]
                                assert session.full_section_ids.get("dir:projects") == new_file_id

                            def test_push_update_existing_bundle(self):
                                """When bundle already exists in index, update_context should be called."""
                                existing_fid = "0.0.5003"
                                session = _store[self.SID]
                                session.full_section_ids["dir:research"] = existing_fid

                                with (
                                    patch("api.routes.vault.update_context") as mock_update,
                                    patch("api.routes.vault.store_context") as mock_store,
                                    patch("api.routes.vault.log_event"),
                                ):
                                    resp = client.post(
                                        "/vault/bundle",
                                        json={
                                            "session_id": self.SID,
                                            "bundle_name": "research",
                                            "files": {
                                                "ibm-prior-art.md": "# IBM\nSearched 14 terms."
                                            },
                                        },
                                    )

                                    assert resp.status_code == 200
                                    mock_update.assert_called_once()
                                    mock_store.assert_not_called()
                                    body = resp.json()
                                    assert body["file_id"] == existing_fid

                                def test_push_invalid_bundle_name_spaces(self):
                                    resp = client.post(
                                        "/vault/bundle",
                                        json={
                                            "session_id": self.SID,
                                            "bundle_name": "my sessions",  # spaces not allowed
                                            "files": {"a.md": "content"},
                                        },
                                    )
                                    assert resp.status_code == 422

                                    def test_push_invalid_bundle_name_uppercase(self):
                                        resp = client.post(
                                            "/vault/bundle",
                                            json={
                                                "session_id": self.SID,
                                                "bundle_name": "MyBundle",  # uppercase not allowed
                                                "files": {"a.md": "content"},
                                            },
                                        )
                                        assert resp.status_code == 422

                                        def test_push_invalid_bundle_name_starts_with_hyphen(self):
                                            resp = client.post(
                                                "/vault/bundle",
                                                json={
                                                    "session_id": self.SID,
                                                    "bundle_name": "-sessions",
                                                    "files": {"a.md": "content"},
                                                },
                                            )
                                            assert resp.status_code == 422

                                            def test_push_nonexistent_session(self):
                                                resp = client.post(
                                                    "/vault/bundle",
                                                    json={
                                                        "session_id": "nonexistent-session-id",
                                                        "bundle_name": "sessions",
                                                        "files": {"a.md": "content"},
                                                    },
                                                )
                                                assert resp.status_code == 404

                                                def test_push_empty_files(self):
                                                    resp = client.post(
                                                        "/vault/bundle",
                                                        json={
                                                            "session_id": self.SID,
                                                            "bundle_name": "sessions",
                                                            "files": {},
                                                        },
                                                    )
                                                    assert resp.status_code == 422

                                                    def test_push_hcs_failure_is_nonfatal(self):
                                                        """Bundle should succeed even if HCS log_event raises."""
                                                        with (
                                                            patch(
                                                                "api.routes.vault.store_context",
                                                                return_value="0.0.5099",
                                                            ),
                                                            patch(
                                                                "api.routes.vault.log_event",
                                                                side_effect=RuntimeError(
                                                                    "HCS down"
                                                                ),
                                                            ),
                                                        ):
                                                            resp = client.post(
                                                                "/vault/bundle",
                                                                json={
                                                                    "session_id": self.SID,
                                                                    "bundle_name": "notes",
                                                                    "files": {"note.md": "content"},
                                                                },
                                                            )
                                                            assert resp.status_code == 200
                                                            assert (
                                                                resp.json()["hcs_logged"] is False
                                                            )

                                                            # ---------------------------------------------------------------------------
                                                            # GET /vault/bundles — list bundle names
                                                            # ---------------------------------------------------------------------------

                                                        class TestBundleList:
                                                            SID = "bundle-list-session-001"

                                                            def setup_method(self):
                                                                _store.clear()
                                                                _make_session(
                                                                    self.SID,
                                                                    extra_section_ids={
                                                                        "dir:sessions": "0.0.6001",
                                                                        "dir:projects": "0.0.6002",
                                                                    },
                                                                )

                                                                def teardown_method(self):
                                                                    _store.clear()

                                                                    def test_list_bundles_returns_names(
                                                                        self,
                                                                    ):
                                                                        resp = client.get(
                                                                            f"/vault/bundles?session_id={self.SID}"
                                                                        )
                                                                        assert (
                                                                            resp.status_code == 200
                                                                        )
                                                                        body = resp.json()
                                                                        assert set(
                                                                            body["bundles"]
                                                                        ) == {
                                                                            "sessions",
                                                                            "projects",
                                                                        }

                                                                        def test_list_bundles_excludes_identity_sections(
                                                                            self,
                                                                        ):
                                                                            """soul, user etc. should not appear in bundles list."""
                                                                            resp = client.get(
                                                                                f"/vault/bundles?session_id={self.SID}"
                                                                            )
                                                                            bundles = resp.json()[
                                                                                "bundles"
                                                                            ]
                                                                            assert (
                                                                                "soul"
                                                                                not in bundles
                                                                            )
                                                                            assert (
                                                                                "user"
                                                                                not in bundles
                                                                            )

                                                                            def test_list_bundles_nonexistent_session(
                                                                                self,
                                                                            ):
                                                                                resp = client.get(
                                                                                    "/vault/bundles?session_id=no-such-session"
                                                                                )
                                                                                assert (
                                                                                    resp.status_code
                                                                                    == 404
                                                                                )

                                                                                def test_list_bundles_empty_when_no_bundles(
                                                                                    self,
                                                                                ):
                                                                                    # session with no dir: entries
                                                                                    _store.clear()
                                                                                    _make_session(
                                                                                        self.SID
                                                                                    )  # only soul + user (no dir: keys)
                                                                                    resp = client.get(
                                                                                        f"/vault/bundles?session_id={self.SID}"
                                                                                    )
                                                                                    assert (
                                                                                        resp.status_code
                                                                                        == 200
                                                                                    )
                                                                                    assert (
                                                                                        resp.json()[
                                                                                            "bundles"
                                                                                        ]
                                                                                        == []
                                                                                    )

                                                                                    # ---------------------------------------------------------------------------
                                                                                    # GET /vault/bundle/{name} — pull a bundle
                                                                                    # ---------------------------------------------------------------------------

                                                                                    class TestBundlePull:
                                                                                        SID = "bundle-pull-session-001"
                                                                                        BUNDLE_NAME = "sessions"
                                                                                        BUNDLE_FILE_ID = "0.0.7001"
                                                                                        FILES = {
                                                                                            "2026-03-17-session.md": "# Session\nFixed chunking bug.",
                                                                                            "notes/extra.md": "Extra note content here.",
                                                                                        }

                                                                                        def setup_method(
                                                                                            self,
                                                                                        ):
                                                                                            _store.clear()
                                                                                            _make_session(
                                                                                                self.SID,
                                                                                                extra_section_ids={
                                                                                                    f"dir:{self.BUNDLE_NAME}": self.BUNDLE_FILE_ID,
                                                                                                },
                                                                                            )

                                                                                            # load_context returns the DECRYPTED plaintext (compress(bundle_bytes)).
                                                                                            # The route then calls decompress() on it — so mock must return the compressed payload.
                                                                                            bundle_bytes = bundle_from_dict(
                                                                                                self.FILES
                                                                                            )
                                                                                            self._plaintext = compress(
                                                                                                bundle_bytes
                                                                                            )

                                                                                            def teardown_method(
                                                                                                self,
                                                                                            ):
                                                                                                _store.clear()

                                                                                                def test_pull_bundle_content(
                                                                                                    self,
                                                                                                ):
                                                                                                    with patch(
                                                                                                        "api.routes.vault.load_context",
                                                                                                        return_value=self._plaintext,
                                                                                                    ):
                                                                                                        resp = client.get(
                                                                                                            f"/vault/bundle/{self.BUNDLE_NAME}?session_id={self.SID}"
                                                                                                        )

                                                                                                        assert (
                                                                                                            resp.status_code
                                                                                                            == 200
                                                                                                        )
                                                                                                        body = (
                                                                                                            resp.json()
                                                                                                        )
                                                                                                        assert (
                                                                                                            body[
                                                                                                                "bundle_name"
                                                                                                            ]
                                                                                                            == self.BUNDLE_NAME
                                                                                                        )
                                                                                                        assert (
                                                                                                            body[
                                                                                                                "files"
                                                                                                            ]
                                                                                                            == self.FILES
                                                                                                        )

                                                                                                    def test_pull_nonexistent_bundle(
                                                                                                        self,
                                                                                                    ):
                                                                                                        resp = client.get(
                                                                                                            f"/vault/bundle/does-not-exist?session_id={self.SID}"
                                                                                                        )
                                                                                                        assert (
                                                                                                            resp.status_code
                                                                                                            == 404
                                                                                                        )

                                                                                                        def test_pull_nonexistent_session(
                                                                                                            self,
                                                                                                        ):
                                                                                                            resp = client.get(
                                                                                                                f"/vault/bundle/{self.BUNDLE_NAME}?session_id=no-session"
                                                                                                            )
                                                                                                            assert (
                                                                                                                resp.status_code
                                                                                                                == 404
                                                                                                            )

                                                                                                            def test_pull_invalid_bundle_name(
                                                                                                                self,
                                                                                                            ):
                                                                                                                resp = client.get(
                                                                                                                    f"/vault/bundle/INVALID NAME?session_id={self.SID}"
                                                                                                                )
                                                                                                                # FastAPI will URL-encode the space, resulting in 404 (not found in index) or 422
                                                                                                                # Either is acceptable — the key point is it doesn't 200 with garbage
                                                                                                                assert (
                                                                                                                    resp.status_code
                                                                                                                    in (
                                                                                                                        404,
                                                                                                                        422,
                                                                                                                    )
                                                                                                                )

                                                                                                                # ---------------------------------------------------------------------------
                                                                                                                # bundle_from_dict / unbundle_to_dict round-trip (unit)
                                                                                                                # ---------------------------------------------------------------------------

                                                                                                                class TestBundleUtils:
                                                                                                                    def test_bundle_roundtrip(
                                                                                                                        self,
                                                                                                                    ):
                                                                                                                        from src.vault import (
                                                                                                                            unbundle_to_dict,
                                                                                                                        )

                                                                                                                        files = {
                                                                                                                            "a.md": "# A\nContent A.",
                                                                                                                            "subdir/b.md": "# B\nContent B.",
                                                                                                                        }
                                                                                                                        bundle = bundle_from_dict(
                                                                                                                            files
                                                                                                                        )
                                                                                                                        result = unbundle_to_dict(
                                                                                                                            bundle
                                                                                                                        )
                                                                                                                        assert (
                                                                                                                            result
                                                                                                                            == files
                                                                                                                        )

                                                                                                                        def test_bundle_sorted_keys(
                                                                                                                            self,
                                                                                                                        ):
                                                                                                                            """bundle_from_dict should produce deterministic output (sorted keys)."""
                                                                                                                            files_a = {
                                                                                                                                "z.md": "z",
                                                                                                                                "a.md": "a",
                                                                                                                            }
                                                                                                                            files_b = {
                                                                                                                                "a.md": "a",
                                                                                                                                "z.md": "z",
                                                                                                                            }
                                                                                                                            assert bundle_from_dict(
                                                                                                                                files_a
                                                                                                                            ) == bundle_from_dict(
                                                                                                                                files_b
                                                                                                                            )

                                                                                                                            def test_bundle_empty_content(
                                                                                                                                self,
                                                                                                                            ):
                                                                                                                                files = {
                                                                                                                                    "empty.md": ""
                                                                                                                                }
                                                                                                                                bundle = bundle_from_dict(
                                                                                                                                    files
                                                                                                                                )
                                                                                                                                from src.vault import (
                                                                                                                                    unbundle_to_dict,
                                                                                                                                )

                                                                                                                                assert (
                                                                                                                                    unbundle_to_dict(
                                                                                                                                        bundle
                                                                                                                                    )
                                                                                                                                    == files
                                                                                                                                )

                                                                                                                                def test_bundle_unicode_content(
                                                                                                                                    self,
                                                                                                                                ):
                                                                                                                                    files = {
                                                                                                                                        "unicode.md": "日本語テスト — émojis 🎉"
                                                                                                                                    }
                                                                                                                                    bundle = bundle_from_dict(
                                                                                                                                        files
                                                                                                                                    )
                                                                                                                                    from src.vault import (
                                                                                                                                        unbundle_to_dict,
                                                                                                                                    )

                                                                                                                                    result = unbundle_to_dict(
                                                                                                                                        bundle
                                                                                                                                    )
                                                                                                                                    assert (
                                                                                                                                        result
                                                                                                                                        == files
                                                                                                                                    )


# ---------------------------------------------------------------------------
# POST /vault/upgrade — add system section to existing vaults
# ---------------------------------------------------------------------------

TOKEN_UPGRADE = "0.0.99999"
_SIG_UPGRADE = b"\xca\xfe\xba\xbe" * 16
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"
_SEC_KEY = derive_key(TOKEN_UPGRADE, _SIG_UPGRADE, info=_INFO_SECTION)
_IDX_KEY = derive_key(TOKEN_UPGRADE, _SIG_UPGRADE, info=_INFO_INDEX)


def _make_upgrade_session(session_id: str, has_system: bool = False) -> Session:
    """Insert a session that is missing (or already has) the system section."""
    now = datetime.now(timezone.utc)
    full_ids: dict = {
        "soul": "0.0.2001",
        "user": "0.0.2002",
        "config": "0.0.2003",
        "session_state": "0.0.2004",
    }
    if has_system:
        full_ids["system"] = "0.0.2005"

    session = Session(
        session_id=session_id,
        token_id=TOKEN_UPGRADE,
        serial=1,
        section_key=bytearray(_SEC_KEY),
        index_key=bytearray(_IDX_KEY),
        index_file_id="0.0.9999",
        full_section_ids=full_ids,
        start_hashes={k: "abc" for k in full_ids if k != "system"},
        sections_loaded=[k for k in full_ids if k != "system"],
        context_sections={k: f"# {k.title()}" for k in full_ids if k != "system"},
        created_at=now,
        expires_at=now + timedelta(hours=4),
    )
    _store[session_id] = session
    return session


class TestVaultUpgrade:
    SID = "upgrade-test-session-001"

    def setup_method(self):
        _store.clear()

    def teardown_method(self):
        _store.clear()

    def test_upgrade_adds_system_section(self):
        """Upgrade endpoint should push system section and update session state."""
        _make_upgrade_session(self.SID)
        with (
            patch("api.routes.vault._push_section", return_value="0.0.3001") as mock_push,
            patch("api.routes.vault._update_index") as mock_idx,
            patch("api.routes.vault.log_event"),
        ):
            resp = client.post(f"/vault/upgrade?session_id={self.SID}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "upgraded"
        assert body["section"] == "system"
        assert body["file_id"] == "0.0.3001"
        mock_push.assert_called_once()
        mock_idx.assert_called_once()

    def test_upgrade_updates_session_in_memory(self):
        """After upgrade, the session should have system in context_sections and sections_loaded."""
        _make_upgrade_session(self.SID)
        with (
            patch("api.routes.vault._push_section", return_value="0.0.3002"),
            patch("api.routes.vault._update_index"),
            patch("api.routes.vault.log_event"),
        ):
            client.post(f"/vault/upgrade?session_id={self.SID}")

        session = _store[self.SID]
        assert "system" in session.context_sections
        assert "system" in session.sections_loaded
        assert session.full_section_ids["system"] == "0.0.3002"
        assert "system" in session.start_hashes
        # Content should reference vault/MCP/RAG
        assert (
            "Vault" in session.context_sections["system"]
            or "vault" in session.context_sections["system"].lower()
        )

    def test_upgrade_idempotent_when_system_already_present(self):
        """Calling upgrade on a vault that already has the system section is a no-op."""
        _make_upgrade_session(self.SID, has_system=True)
        with (
            patch("api.routes.vault._push_section") as mock_push,
            patch("api.routes.vault._update_index") as mock_idx,
        ):
            resp = client.post(f"/vault/upgrade?session_id={self.SID}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "already_present"
        mock_push.assert_not_called()
        mock_idx.assert_not_called()

    def test_upgrade_missing_session_returns_404(self):
        resp = client.post("/vault/upgrade?session_id=no-such-session")
        assert resp.status_code == 404

    def test_upgrade_hfs_failure_returns_502(self):
        """If HFS push fails, the endpoint should return 502 (not 500)."""
        _make_upgrade_session(self.SID)
        with (
            patch("api.routes.vault._push_section", side_effect=RuntimeError("HFS unavailable")),
            patch("api.routes.vault.log_event"),
        ):
            resp = client.post(f"/vault/upgrade?session_id={self.SID}")

        assert resp.status_code == 502
        assert "HFS" in resp.json()["detail"]

    def test_upgrade_hcs_failure_is_nonfatal(self):
        """HCS log failure should not prevent a successful upgrade."""
        _make_upgrade_session(self.SID)
        with (
            patch("api.routes.vault._push_section", return_value="0.0.3003"),
            patch("api.routes.vault._update_index"),
            patch("api.routes.vault.log_event", side_effect=RuntimeError("HCS down")),
        ):
            resp = client.post(f"/vault/upgrade?session_id={self.SID}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "upgraded"
