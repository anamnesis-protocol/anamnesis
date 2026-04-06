"""
tests/test_api_session.py — Unit tests for the SaaS session API.

Tests are structured so the heavy Hedera I/O (HFS, HCS, contract) is mocked.
Only the crypto and session store logic runs for real.

Covers:
- /session/challenge returns correct deterministic challenge
- /session/open happy path (mocked HFS → returns context)
- /session/open rejects bad wallet sig (InvalidTag → 401)
- /session/open rejects injected content (ValueError → 403)
- /session/open rejects bad hex input → 400
- /session/close returns 200 and evicts session
- /session/close on expired/unknown session → 404
- /session/status returns active session count
"""

import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from cryptography.exceptions import InvalidTag

from api.main import app
from src.crypto import make_challenge, derive_key, encrypt_context, compress
from src.vault import _make_section_aad, _make_index_aad

client = TestClient(app)

TOKEN_ID = "0.0.99999"
SERIAL = 1
WALLET_SIG = b"\xab\xcd\xef\x12" * 16  # 64-byte fake Ed25519 sig
WALLET_SIG_HEX = WALLET_SIG.hex()

# Constants from vault.py — must match
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"

# Sample context content
_HARNESS_CONTENT = b"# HARNESS\nThis is the harness directives."
_USER_CONTENT = b"# USER\nThis is the user profile."
_CONFIG_CONTENT = b"# CONFIG\nThis is the AI configuration."
_SESSION_CONTENT = b"# SESSION\nLast session: today."


def _make_encrypted_index(token_id: str, wallet_sig: bytes, section_file_ids: dict) -> bytes:
    """Build an encrypted vault index blob matching the real vault format."""
    index_key = derive_key(token_id, wallet_sig, info=_INFO_INDEX)
    aad = _make_index_aad(token_id)
    index_json = json.dumps(section_file_ids, indent=2).encode("utf-8")
    return encrypt_context(index_key, index_json, aad)

    def _make_encrypted_section(
        token_id: str, wallet_sig: bytes, section_name: str, content: bytes
    ) -> bytes:
        """Build an encrypted vault section blob matching the real vault format."""
        section_key = derive_key(token_id, wallet_sig, info=_INFO_SECTION)
        aad = _make_section_aad(section_name, token_id)
        return encrypt_context(section_key, compress(content), aad)

        # ---------------------------------------------------------------------------
        # /session/challenge
        # ---------------------------------------------------------------------------

        class TestChallenge:
            def test_returns_deterministic_challenge(self):
                resp = client.post("/session/challenge", json={"token_id": TOKEN_ID})
                assert resp.status_code == 200
                data = resp.json()
                assert data["token_id"] == TOKEN_ID
                expected = make_challenge(TOKEN_ID).hex()
                assert data["challenge_hex"] == expected

                def test_different_tokens_different_challenges(self):
                    r1 = client.post("/session/challenge", json={"token_id": "0.0.111"})
                    r2 = client.post("/session/challenge", json={"token_id": "0.0.222"})
                    assert r1.json()["challenge_hex"] != r2.json()["challenge_hex"]

                    # ---------------------------------------------------------------------------
                    # /session/open — happy path
                    # ---------------------------------------------------------------------------

                    class TestSessionOpen:
                        def _mock_open_success(self, mocker):
                            """
                            Set up mocks so /session/open succeeds without Hedera network calls.
                            Returns (mock_get_contract, mock_get_file_id, mock_pull_index, mock_pull_section).
                            """
                            section_file_ids = {
                                "harness": "0.0.100001",
                                "user": "0.0.100002",
                                "config": "0.0.100003",
                                "session_state": "0.0.100004",
                            }
                            section_contents = {
                                "harness": _HARNESS_CONTENT,
                                "user": _USER_CONTENT,
                                "config": _CONFIG_CONTENT,
                                "session_state": _SESSION_CONTENT,
                            }

                            mocker.patch(
                                "api.routes.session.get_validator_contract_id",
                                return_value="0.0.99000",
                            )
                            mocker.patch(
                                "api.routes.session._get_registered_file_id",
                                return_value="0.0.99001",
                            )
                            mocker.patch(
                                "api.routes.session.token_id_to_evm_address",
                                return_value="0" * 40,
                            )
                            mocker.patch(
                                "api.routes.session.pull_index",
                                return_value=section_file_ids,
                            )
                            mocker.patch(
                                "api.routes.session.pull_section",
                                side_effect=lambda file_id, key, token_id, section_name="", expected_hash=None: section_contents.get(
                                    section_name, b"# content"
                                ),
                            )
                            mocker.patch("api.routes.session.log_event", return_value="")

                            return section_contents

                            def test_happy_path_returns_session_id(self, mocker):
                                self._mock_open_success(mocker)
                                resp = client.post(
                                    "/session/open",
                                    json={
                                        "token_id": TOKEN_ID,
                                        "wallet_signature_hex": WALLET_SIG_HEX,
                                    },
                                )
                                assert resp.status_code == 200, resp.text
                                data = resp.json()
                                assert "session_id" in data
                                assert len(data["session_id"]) == 36  # UUID
                                assert data["token_id"] == TOKEN_ID

                                def test_happy_path_returns_all_identity_sections(self, mocker):
                                    self._mock_open_success(mocker)
                                    resp = client.post(
                                        "/session/open",
                                        json={
                                            "token_id": TOKEN_ID,
                                            "wallet_signature_hex": WALLET_SIG_HEX,
                                        },
                                    )
                                    data = resp.json()
                                    assert set(data["context_sections"].keys()) == {
                                        "harness",
                                        "user",
                                        "config",
                                        "session_state",
                                    }
                                    assert (
                                        data["context_sections"]["harness"]
                                        == _HARNESS_CONTENT.decode()
                                    )

                                    def test_happy_path_has_expiry(self, mocker):
                                        self._mock_open_success(mocker)
                                        resp = client.post(
                                            "/session/open",
                                            json={
                                                "token_id": TOKEN_ID,
                                                "wallet_signature_hex": WALLET_SIG_HEX,
                                            },
                                        )
                                        data = resp.json()
                                        assert "expires_at" in data
                                        assert "created_at" in data

                                        def test_dir_bundles_excluded_from_context(self, mocker):
                                            """dir: prefixed sections must never appear in session context."""
                                            section_ids_with_dirs = {
                                                "harness": "0.0.100001",
                                                "user": "0.0.100002",
                                                "config": "0.0.100003",
                                                "session_state": "0.0.100004",
                                                "dir:research": "0.0.200001",
                                                "dir:projects": "0.0.200002",
                                            }
                                            section_contents = {
                                                "harness": _HARNESS_CONTENT,
                                                "user": _USER_CONTENT,
                                                "config": _CONFIG_CONTENT,
                                                "session_state": _SESSION_CONTENT,
                                            }
                                            mocker.patch(
                                                "api.routes.session.get_validator_contract_id",
                                                return_value="0.0.99000",
                                            )
                                            mocker.patch(
                                                "api.routes.session._get_registered_file_id",
                                                return_value="0.0.99001",
                                            )
                                            mocker.patch(
                                                "api.routes.session.token_id_to_evm_address",
                                                return_value="0" * 40,
                                            )
                                            mocker.patch(
                                                "api.routes.session.pull_index",
                                                return_value=section_ids_with_dirs,
                                            )
                                            mocker.patch(
                                                "api.routes.session.pull_section",
                                                side_effect=lambda file_id, key, token_id, section_name="", expected_hash=None: section_contents.get(
                                                    section_name, b"# fallback"
                                                ),
                                            )
                                            mocker.patch(
                                                "api.routes.session.log_event", return_value=""
                                            )

                                            resp = client.post(
                                                "/session/open",
                                                json={
                                                    "token_id": TOKEN_ID,
                                                    "wallet_signature_hex": WALLET_SIG_HEX,
                                                },
                                            )
                                            assert resp.status_code == 200
                                            sections = resp.json()["context_sections"]
                                            assert "dir:research" not in sections
                                            assert "dir:projects" not in sections

                                            # ---------------------------------------------------------------------------
                                            # /session/open — auth failures
                                            # ---------------------------------------------------------------------------

                                            class TestSessionOpenAuthFailures:
                                                def test_invalid_hex_returns_400(self):
                                                    resp = client.post(
                                                        "/session/open",
                                                        json={
                                                            "token_id": TOKEN_ID,
                                                            "wallet_signature_hex": "not-valid-hex",
                                                        },
                                                    )
                                                    assert resp.status_code == 400

                                                    def test_wrong_sig_length_returns_400(self):
                                                        resp = client.post(
                                                            "/session/open",
                                                            json={
                                                                "token_id": TOKEN_ID,
                                                                "wallet_signature_hex": "ab"
                                                                * 32,  # 32 bytes — wrong length
                                                            },
                                                        )
                                                        assert resp.status_code == 400

                                                        def test_invalid_tag_on_index_returns_401(
                                                            self, mocker
                                                        ):
                                                            mocker.patch(
                                                                "api.routes.session.get_validator_contract_id",
                                                                return_value="0.0.99000",
                                                            )
                                                            mocker.patch(
                                                                "api.routes.session._get_registered_file_id",
                                                                return_value="0.0.99001",
                                                            )
                                                            mocker.patch(
                                                                "api.routes.session.token_id_to_evm_address",
                                                                return_value="0" * 40,
                                                            )
                                                            mocker.patch(
                                                                "api.routes.session.pull_index",
                                                                side_effect=InvalidTag(),
                                                            )

                                                            resp = client.post(
                                                                "/session/open",
                                                                json={
                                                                    "token_id": TOKEN_ID,
                                                                    "wallet_signature_hex": WALLET_SIG_HEX,
                                                                },
                                                            )
                                                            assert resp.status_code == 401
                                                            assert (
                                                                "invalid wallet signature"
                                                                in resp.json()["detail"].lower()
                                                            )

                                                            def test_invalid_tag_on_section_returns_401(
                                                                self, mocker
                                                            ):
                                                                mocker.patch(
                                                                    "api.routes.session.get_validator_contract_id",
                                                                    return_value="0.0.99000",
                                                                )
                                                                mocker.patch(
                                                                    "api.routes.session._get_registered_file_id",
                                                                    return_value="0.0.99001",
                                                                )
                                                                mocker.patch(
                                                                    "api.routes.session.token_id_to_evm_address",
                                                                    return_value="0" * 40,
                                                                )
                                                                mocker.patch(
                                                                    "api.routes.session.pull_index",
                                                                    return_value={
                                                                        "harness": "0.0.100001",
                                                                        "user": "0.0.100002",
                                                                        "config": "0.0.100003",
                                                                        "session_state": "0.0.100004",
                                                                    },
                                                                )
                                                                mocker.patch(
                                                                    "api.routes.session.pull_section",
                                                                    side_effect=InvalidTag(),
                                                                )

                                                                resp = client.post(
                                                                    "/session/open",
                                                                    json={
                                                                        "token_id": TOKEN_ID,
                                                                        "wallet_signature_hex": WALLET_SIG_HEX,
                                                                    },
                                                                )
                                                                assert resp.status_code == 401

                                                                def test_injection_detected_returns_403(
                                                                    self, mocker
                                                                ):
                                                                    mocker.patch(
                                                                        "api.routes.session.get_validator_contract_id",
                                                                        return_value="0.0.99000",
                                                                    )
                                                                    mocker.patch(
                                                                        "api.routes.session._get_registered_file_id",
                                                                        return_value="0.0.99001",
                                                                    )
                                                                    mocker.patch(
                                                                        "api.routes.session.token_id_to_evm_address",
                                                                        return_value="0" * 40,
                                                                    )
                                                                    mocker.patch(
                                                                        "api.routes.session.pull_index",
                                                                        return_value={
                                                                            "harness": "0.0.100001"
                                                                        },
                                                                    )
                                                                    mocker.patch(
                                                                        "api.routes.session.pull_section",
                                                                        side_effect=ValueError(
                                                                            "[integrity:soul] Content failed security scan"
                                                                        ),
                                                                    )

                                                                    resp = client.post(
                                                                        "/session/open",
                                                                        json={
                                                                            "token_id": TOKEN_ID,
                                                                            "wallet_signature_hex": WALLET_SIG_HEX,
                                                                        },
                                                                    )
                                                                    assert resp.status_code == 403
                                                                    assert (
                                                                        "integrity"
                                                                        in resp.json()[
                                                                            "detail"
                                                                        ].lower()
                                                                    )

                                                                    def test_no_contract_configured_returns_503(
                                                                        self, mocker
                                                                    ):
                                                                        mocker.patch(
                                                                            "api.routes.session.get_validator_contract_id",
                                                                            return_value=None,
                                                                        )

                                                                        resp = client.post(
                                                                            "/session/open",
                                                                            json={
                                                                                "token_id": TOKEN_ID,
                                                                                "wallet_signature_hex": WALLET_SIG_HEX,
                                                                            },
                                                                        )
                                                                        assert (
                                                                            resp.status_code == 503
                                                                        )

                                                                        def test_token_not_registered_returns_404(
                                                                            self, mocker
                                                                        ):
                                                                            mocker.patch(
                                                                                "api.routes.session.get_validator_contract_id",
                                                                                return_value="0.0.99000",
                                                                            )
                                                                            mocker.patch(
                                                                                "api.routes.session._get_registered_file_id",
                                                                                return_value="",
                                                                            )
                                                                            mocker.patch(
                                                                                "api.routes.session.token_id_to_evm_address",
                                                                                return_value="0"
                                                                                * 40,
                                                                            )

                                                                            resp = client.post(
                                                                                "/session/open",
                                                                                json={
                                                                                    "token_id": TOKEN_ID,
                                                                                    "wallet_signature_hex": WALLET_SIG_HEX,
                                                                                },
                                                                            )
                                                                            assert (
                                                                                resp.status_code
                                                                                == 404
                                                                            )
                                                                            assert (
                                                                                "no vault registered"
                                                                                in resp.json()[
                                                                                    "detail"
                                                                                ].lower()
                                                                            )

                                                                            # ---------------------------------------------------------------------------
                                                                            # /session/close
                                                                            # ---------------------------------------------------------------------------

                                                                            class TestSessionClose:
                                                                                def _open_session(
                                                                                    self, mocker
                                                                                ) -> str:
                                                                                    """Helper: open a mock session and return its session_id."""
                                                                                    mocker.patch(
                                                                                        "api.routes.session.get_validator_contract_id",
                                                                                        return_value="0.0.99000",
                                                                                    )
                                                                                    mocker.patch(
                                                                                        "api.routes.session._get_registered_file_id",
                                                                                        return_value="0.0.99001",
                                                                                    )
                                                                                    mocker.patch(
                                                                                        "api.routes.session.token_id_to_evm_address",
                                                                                        return_value="0"
                                                                                        * 40,
                                                                                    )
                                                                                    mocker.patch(
                                                                                        "api.routes.session.pull_index",
                                                                                        return_value={
                                                                                            "harness": "0.0.100001",
                                                                                            "user": "0.0.100002",
                                                                                            "config": "0.0.100003",
                                                                                            "session_state": "0.0.100004",
                                                                                        },
                                                                                    )
                                                                                    mocker.patch(
                                                                                        "api.routes.session.pull_section",
                                                                                        return_value=_HARNESS_CONTENT,
                                                                                    )
                                                                                    mocker.patch(
                                                                                        "api.routes.session.log_event",
                                                                                        return_value="",
                                                                                    )

                                                                                    resp = client.post(
                                                                                        "/session/open",
                                                                                        json={
                                                                                            "token_id": TOKEN_ID,
                                                                                            "wallet_signature_hex": WALLET_SIG_HEX,
                                                                                        },
                                                                                    )
                                                                                    return resp.json()[
                                                                                        "session_id"
                                                                                    ]

                                                                                    def test_close_returns_200(
                                                                                        self, mocker
                                                                                    ):
                                                                                        session_id = self._open_session(
                                                                                            mocker
                                                                                        )
                                                                                        resp = client.post(
                                                                                            "/session/close",
                                                                                            json={
                                                                                                "session_id": session_id
                                                                                            },
                                                                                        )
                                                                                        assert (
                                                                                            resp.status_code
                                                                                            == 200
                                                                                        )
                                                                                        data = (
                                                                                            resp.json()
                                                                                        )
                                                                                        assert (
                                                                                            data[
                                                                                                "session_id"
                                                                                            ]
                                                                                            == session_id
                                                                                        )
                                                                                        assert (
                                                                                            "closed_at"
                                                                                            in data
                                                                                        )

                                                                                        def test_close_evicts_session(
                                                                                            self,
                                                                                            mocker,
                                                                                        ):
                                                                                            session_id = self._open_session(
                                                                                                mocker
                                                                                            )
                                                                                            client.post(
                                                                                                "/session/close",
                                                                                                json={
                                                                                                    "session_id": session_id
                                                                                                },
                                                                                            )
                                                                                            # Second close should 404
                                                                                            resp = client.post(
                                                                                                "/session/close",
                                                                                                json={
                                                                                                    "session_id": session_id
                                                                                                },
                                                                                            )
                                                                                            assert (
                                                                                                resp.status_code
                                                                                                == 404
                                                                                            )

                                                                                            def test_close_unknown_session_returns_404(
                                                                                                self,
                                                                                            ):
                                                                                                resp = client.post(
                                                                                                    "/session/close",
                                                                                                    json={
                                                                                                        "session_id": "00000000-0000-0000-0000-000000000000"
                                                                                                    },
                                                                                                )
                                                                                                assert (
                                                                                                    resp.status_code
                                                                                                    == 404
                                                                                                )

                                                                                                # ---------------------------------------------------------------------------
                                                                                                # /session/status
                                                                                                # ---------------------------------------------------------------------------

                                                                                                class TestSessionStatus:
                                                                                                    def test_status_returns_ok(
                                                                                                        self,
                                                                                                    ):
                                                                                                        resp = client.get(
                                                                                                            "/session/status"
                                                                                                        )
                                                                                                        assert (
                                                                                                            resp.status_code
                                                                                                            == 200
                                                                                                        )
                                                                                                        assert (
                                                                                                            resp.json()[
                                                                                                                "status"
                                                                                                            ]
                                                                                                            == "ok"
                                                                                                        )
                                                                                                        assert (
                                                                                                            "active_sessions"
                                                                                                            in resp.json()
                                                                                                        )
