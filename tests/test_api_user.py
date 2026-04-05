"""
tests/test_api_user.py — Unit tests for user provisioning endpoints.

All Hedera I/O (HFS, HCS, contract, token mint) is mocked.
Only models, provision store, and route logic are tested directly.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

ACCOUNT_ID = "0.0.55555"
COMPANION = "TestBot"
TOKEN_ID = "0.0.77777"
PASSPHRASE = "correct-horse-battery-staple"
INDEX_FILE_ID = "0.0.88888"

SECTION_FILE_IDS = {
    "harness": "0.0.200001",
    "user": "0.0.200002",
    "config": "0.0.200003",
    "session_state": "0.0.200004",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_provision_start(mocker, token_id: str = TOKEN_ID) -> None:
    mocker.patch("api.routes.user.mint_context_token", return_value=token_id)
    mocker.patch("api.routes.user.log_event", return_value="")


def _mock_provision_complete(mocker, vault_registered: bool = True) -> None:
    mocker.patch("api.routes.user.get_validator_contract_id", return_value="0.0.99000")
    mocker.patch(
        "api.routes.user.push_section",
        side_effect=lambda section_name, content, key, token_id, existing_file_id:
            SECTION_FILE_IDS.get(section_name, "0.0.299999"),
    )
    mocker.patch("api.routes.user.push_index", return_value=INDEX_FILE_ID)
    mocker.patch("api.routes.user.token_id_to_evm_address", return_value="0" * 40)
    if vault_registered:
        mocker.patch("api.routes.user.register_file", return_value=None)
    else:
        mocker.patch("api.routes.user.register_file", side_effect=Exception("contract error"))
    mocker.patch("api.routes.user.log_event", return_value="")


def _do_start(mocker, account_id: str = ACCOUNT_ID, companion: str = COMPANION) -> dict:
    _mock_provision_start(mocker)
    resp = client.post("/user/provision/start", json={
        "account_id": account_id,
        "companion_name": companion,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# /user/provision/start
# ---------------------------------------------------------------------------

class TestProvisionStart:
    def test_returns_token_id_and_challenge(self, mocker):
        data = _do_start(mocker)
        assert data["token_id"] == TOKEN_ID
        assert "expires_at" in data

    def test_mint_failure_returns_502(self, mocker):
        mocker.patch("api.routes.user.mint_context_token", side_effect=Exception("Hedera down"))
        resp = client.post("/user/provision/start", json={
            "account_id": ACCOUNT_ID,
            "companion_name": COMPANION,
        })
        assert resp.status_code == 502
        assert "mint failed" in resp.json()["detail"].lower()

    def test_mint_non_success_status_surfaces_as_502(self, mocker):
        """mint_context_token raises when Hedera returns non-SUCCESS — must not swallow it."""
        mocker.patch(
            "api.routes.user.mint_context_token",
            side_effect=RuntimeError("TokenCreateTransaction failed on-chain: status=7 (code 7)"),
        )
        resp = client.post("/user/provision/start", json={
            "account_id": ACCOUNT_ID,
            "companion_name": COMPANION,
        })
        assert resp.status_code == 502
        assert "7" in resp.json()["detail"]

    def test_duplicate_start_creates_new_pending_record(self, mocker):
        """Two /start calls for same account create independent pending records."""
        _do_start(mocker, account_id="0.0.11111")
        _mock_provision_start(mocker, token_id="0.0.22222")
        resp = client.post("/user/provision/start", json={
            "account_id": "0.0.11111",
            "companion_name": COMPANION,
        })
        assert resp.status_code == 200
        assert resp.json()["token_id"] == "0.0.22222"


# ---------------------------------------------------------------------------
# /user/provision/complete
# ---------------------------------------------------------------------------

class TestProvisionComplete:
    def test_happy_path(self, mocker):
        _do_start(mocker)
        _mock_provision_complete(mocker)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["token_id"] == TOKEN_ID
        assert set(data["sections_pushed"]) == {"harness", "user", "config", "session_state"}
        assert data["index_file_id"] == INDEX_FILE_ID
        assert data["vault_registered"] is True

    def test_pushes_all_four_identity_sections(self, mocker):
        _do_start(mocker)
        _mock_provision_complete(mocker)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert set(resp.json()["sections_pushed"]) == {
            "harness", "user", "config", "session_state"
        }

    def test_no_pending_provision_returns_404(self, mocker):
        _mock_provision_complete(mocker)
        resp = client.post("/user/provision/complete", json={
            "token_id": "0.0.99999",
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 404
        assert "no pending provision" in resp.json()["detail"].lower()

    def test_short_passphrase_returns_400(self, mocker):
        _do_start(mocker)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": "short",
        })
        assert resp.status_code == 400

    def test_no_contract_configured_returns_503(self, mocker):
        _do_start(mocker)
        mocker.patch("api.routes.user.get_validator_contract_id", return_value=None)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 503

    def test_contract_registration_failure_returns_502(self, mocker):
        """Contract registration failure must be fatal — vault unusable without on-chain record."""
        _do_start(mocker)
        _mock_provision_complete(mocker, vault_registered=False)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 502
        assert "contract registration failed" in resp.json()["detail"].lower()

    def test_contract_registration_failure_mentions_token_id(self, mocker):
        """Error detail must include token_id so user can contact support."""
        _do_start(mocker)
        _mock_provision_complete(mocker, vault_registered=False)
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert TOKEN_ID in resp.json()["detail"]

    def test_pending_record_cleared_after_complete(self, mocker):
        """Second /provision/complete for the same token_id must 404."""
        _do_start(mocker)
        _mock_provision_complete(mocker)
        client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 404

    def test_hfs_push_failure_returns_502(self, mocker):
        _do_start(mocker)
        mocker.patch("api.routes.user.get_validator_contract_id", return_value="0.0.99000")
        mocker.patch("api.routes.user.push_section", side_effect=Exception("HFS down"))
        resp = client.post("/user/provision/complete", json={
            "token_id": TOKEN_ID,
            "passphrase": PASSPHRASE,
        })
        assert resp.status_code == 502
        assert "hfs" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# mint_context_token — unit tests for status-check logic
# ---------------------------------------------------------------------------

class TestMintContextToken:
    def test_raises_when_create_tx_returns_non_success(self, mocker):
        """TokenCreateTransaction non-SUCCESS must raise — not return None token_id."""
        from hiero_sdk_python.hapi.services import response_code_pb2 as _rc

        mock_receipt = mocker.MagicMock()
        mock_receipt.status = _rc.INVALID_SIGNATURE  # 7
        mock_receipt.token_id = None

        mock_tx = mocker.MagicMock()
        mock_tx.execute.return_value = mock_receipt
        mock_tx.set_token_name.return_value = mock_tx
        mock_tx.set_token_symbol.return_value = mock_tx
        mock_tx.set_token_type.return_value = mock_tx
        mock_tx.set_supply_type.return_value = mock_tx
        mock_tx.set_max_supply.return_value = mock_tx
        mock_tx.set_initial_supply.return_value = mock_tx
        mock_tx.set_treasury_account_id.return_value = mock_tx
        mock_tx.set_supply_key.return_value = mock_tx
        mock_tx.set_memo.return_value = mock_tx
        mock_tx.freeze_with.return_value = mock_tx
        mock_tx.sign.return_value = mock_tx

        mocker.patch("src.context_token.TokenCreateTransaction", return_value=mock_tx)
        mocker.patch("src.context_token.get_client")
        mocker.patch("src.context_token.get_treasury", return_value=(
            mocker.MagicMock(), mocker.MagicMock()
        ))

        from src.context_token import mint_context_token
        with pytest.raises(RuntimeError, match="TokenCreateTransaction failed"):
            mint_context_token(context_file_id="0.0.99999")

    def test_raises_when_create_receipt_has_no_token_id(self, mocker):
        """SUCCESS status but None token_id must raise — SDK quirk guard."""
        from hiero_sdk_python.hapi.services import response_code_pb2 as _rc

        mock_receipt = mocker.MagicMock()
        mock_receipt.status = _rc.SUCCESS
        mock_receipt.token_id = None

        mock_tx = mocker.MagicMock()
        mock_tx.execute.return_value = mock_receipt
        for attr in ["set_token_name", "set_token_symbol", "set_token_type", "set_supply_type",
                     "set_max_supply", "set_initial_supply", "set_treasury_account_id",
                     "set_supply_key", "set_memo", "freeze_with", "sign"]:
            getattr(mock_tx, attr).return_value = mock_tx

        mocker.patch("src.context_token.TokenCreateTransaction", return_value=mock_tx)
        mocker.patch("src.context_token.get_client")
        mocker.patch("src.context_token.get_treasury", return_value=(
            mocker.MagicMock(), mocker.MagicMock()
        ))

        from src.context_token import mint_context_token
        with pytest.raises(RuntimeError, match="no token_id"):
            mint_context_token(context_file_id="0.0.99999")

    def test_metadata_stays_under_100_bytes(self):
        """NFT metadata must never exceed Hedera's 100-byte limit regardless of name length."""
        import json
        from src.context_token import _build_metadata  # we'll add this helper

        long_name = "A" * 200
        metadata = _build_metadata("0.0.12345", long_name)
        assert len(metadata) <= 100, f"Metadata is {len(metadata)} bytes — exceeds Hedera 100-byte limit"

    def test_metadata_contains_file_id(self):
        import json as _json
        from src.context_token import _build_metadata
        metadata = _build_metadata("0.0.12345", "TestBot")
        parsed = _json.loads(metadata.decode("utf-8"))
        assert parsed["f"] == "0.0.12345"


# ---------------------------------------------------------------------------
# /user/{token_id}/status
# ---------------------------------------------------------------------------

class TestUserStatus:
    def test_registered_vault(self, mocker):
        mocker.patch("api.routes.user.get_validator_contract_id", return_value="0.0.99000")
        mocker.patch("api.routes.user.token_id_to_evm_address", return_value="0" * 40)
        mocker.patch("api.routes.user._get_registered_file_id", return_value=INDEX_FILE_ID)

        resp = client.get(f"/user/{TOKEN_ID}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["registered"] is True
        assert data["index_file_id"] == INDEX_FILE_ID

    def test_unregistered_vault(self, mocker):
        mocker.patch("api.routes.user.get_validator_contract_id", return_value="0.0.99000")
        mocker.patch("api.routes.user.token_id_to_evm_address", return_value="0" * 40)
        mocker.patch("api.routes.user._get_registered_file_id", return_value="")

        resp = client.get(f"/user/{TOKEN_ID}/status")
        assert resp.status_code == 200
        assert resp.json()["registered"] is False
        assert resp.json()["index_file_id"] is None

    def test_no_contract_returns_503(self, mocker):
        mocker.patch("api.routes.user.get_validator_contract_id", return_value=None)
        resp = client.get(f"/user/{TOKEN_ID}/status")
        assert resp.status_code == 503
