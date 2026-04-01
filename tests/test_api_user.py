"""
tests/test_api_user.py — Unit tests for user provisioning endpoints.

All Hedera I/O (HFS, HCS, contract, token mint) is mocked.
Only models, provision store, and route logic are tested directly.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.crypto import make_challenge

client = TestClient(app)

ACCOUNT_ID = "0.0.55555"
COMPANION = "TestBot"
TOKEN_ID = "0.0.77777"
WALLET_SIG = b"\x11\x22\x33\x44" * 16 # 64-byte fake sig
WALLET_SIG_HEX = WALLET_SIG.hex()
INDEX_FILE_ID = "0.0.88888"

SECTION_FILE_IDS = {
 "soul": "0.0.200001",
 "user": "0.0.200002",
 "symbiote": "0.0.200003",
 "session_state": "0.0.200004",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_provision_start(mocker, token_id: str = TOKEN_ID) -> None:
 """Mock mint_soul_token to return a fixed token_id."""
 mocker.patch("api.routes.user.mint_soul_token", return_value=token_id)
 mocker.patch("api.routes.user.log_event", return_value="")


def _mock_provision_complete(mocker, vault_registered: bool = True) -> None:
 """Mock all HFS / contract calls for provision/complete."""
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
 assert data["challenge_hex"] == make_challenge(TOKEN_ID).hex()
 assert "expires_at" in data

 def test_challenge_matches_session_challenge(self, mocker):
 """Provisioning challenge must match session/challenge so same sig works for both."""
 data = _do_start(mocker)
 # /session/challenge for the same token_id should return identical challenge
 session_resp = client.post("/session/challenge", json={"token_id": TOKEN_ID})
 assert session_resp.json()["challenge_hex"] == data["challenge_hex"]

 def test_mint_failure_returns_502(self, mocker):
 mocker.patch("api.routes.user.mint_soul_token", side_effect=Exception("Hedera down"))
 resp = client.post("/user/provision/start", json={
 "account_id": ACCOUNT_ID,
 "companion_name": COMPANION,
 })
 assert resp.status_code == 502
 assert "mint failed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /user/provision/complete
# ---------------------------------------------------------------------------

class TestProvisionComplete:
 def test_happy_path(self, mocker):
 _do_start(mocker)
 _mock_provision_complete(mocker)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 200, resp.text
 data = resp.json()
 assert data["token_id"] == TOKEN_ID
 assert set(data["sections_pushed"]) == {"soul", "user", "symbiote", "session_state"}
 assert data["index_file_id"] == INDEX_FILE_ID
 assert data["vault_registered"] is True

 def test_pushes_all_four_identity_sections(self, mocker):
 _do_start(mocker)
 _mock_provision_complete(mocker)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert set(resp.json()["sections_pushed"]) == {
 "soul", "user", "symbiote", "session_state"
 }

 def test_no_pending_provision_returns_404(self, mocker):
 # Don't call /start — no pending record
 _mock_provision_complete(mocker)
 resp = client.post("/user/provision/complete", json={
 "token_id": "0.0.99999",
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 404
 assert "no pending provision" in resp.json()["detail"].lower()

 def test_invalid_hex_returns_400(self, mocker):
 _do_start(mocker)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": "zzz-not-hex",
 })
 assert resp.status_code == 400

 def test_wrong_sig_length_returns_400(self, mocker):
 _do_start(mocker)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": "aa" * 10, # 10 bytes — wrong length
 })
 assert resp.status_code == 400

 def test_no_contract_configured_returns_503(self, mocker):
 _do_start(mocker)
 mocker.patch("api.routes.user.get_validator_contract_id", return_value=None)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 503

 def test_contract_registration_failure_is_non_fatal(self, mocker):
 """Vault exists on HFS even if contract registration fails."""
 _do_start(mocker)
 _mock_provision_complete(mocker, vault_registered=False)
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 200
 assert resp.json()["vault_registered"] is False

 def test_pending_record_cleared_after_complete(self, mocker):
 """Second call to /provision/complete for the same token_id must 404."""
 _do_start(mocker)
 _mock_provision_complete(mocker)
 client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 404

 def test_hfs_push_failure_returns_502(self, mocker):
 _do_start(mocker)
 mocker.patch("api.routes.user.get_validator_contract_id", return_value="0.0.99000")
 mocker.patch("api.routes.user.push_section", side_effect=Exception("HFS down"))
 resp = client.post("/user/provision/complete", json={
 "token_id": TOKEN_ID,
 "wallet_signature_hex": WALLET_SIG_HEX,
 })
 assert resp.status_code == 502
 assert "hfs" in resp.json()["detail"].lower()


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
