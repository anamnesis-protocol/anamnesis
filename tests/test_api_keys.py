"""
tests/test_api_keys.py — Tests for GET/POST/DELETE /user/keys

All Supabase and Fernet calls are mocked. Tests cover:
- Auth requirement (JWT must be present)
- Demo-user sentinel (testnet mode)
- Provider validation
- Encrypt → store → list → delete lifecycle
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── App setup ─────────────────────────────────────────────────────────────────

# Use mainnet mode so JWT is enforced (not testnet bypass)
os.environ["SOVEREIGN_ENV"] = ""
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-that-is-long-enough-32b")
os.environ.setdefault("USER_KEYS_ENCRYPTION_SECRET", "") # will be set per-test via patch
os.environ.setdefault("HEDERA_NETWORK", "testnet")
os.environ.setdefault("OPERATOR_ID", "0.0.1234")
os.environ.setdefault("OPERATOR_KEY", "302e020100300506032b657004220420" + "a" * 64)

from api.main import app # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ── Token helper ───────────────────────────────────────────────────────────────

def _make_token(user_id: str = "real-user-uuid") -> str:
import jwt, time
return jwt.encode(
{"sub": user_id, "email": "user@example.com", "aud": "authenticated",
"exp": int(time.time()) + 3600},
"test-jwt-secret-that-is-long-enough-32b",
algorithm="HS256",
)


def _auth(user_id: str = "real-user-uuid") -> dict:
return {"Authorization": f"Bearer {_make_token(user_id)}"}


# ── Mock helpers ───────────────────────────────────────────────────────────────

def _mock_supabase(configured_providers: list[str] = None):
"""Return a mock Supabase client for key_store calls.

Rows include a fake `encrypted_key` field because get_key_status() now
selects provider+encrypted_key and attempts decryption. Tests that call
GET /user/keys should also patch `api.services.key_store.decrypt_key`
to control whether keys appear as configured or corrupted.
"""
mock_sb = MagicMock()
rows = [{"provider": p, "encrypted_key": "fake-ciphertext"} for p in (configured_providers or [])]
mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=rows)
mock_sb.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])
mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
return mock_sb


# ── GET /user/keys ─────────────────────────────────────────────────────────────

class TestListKeys:
def test_no_auth_returns_401(self):
res = client.get("/user/keys")
assert res.status_code == 401

def test_authenticated_no_keys_returns_empty(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase([])), \
patch("api.services.key_store.decrypt_key", return_value="plaintext"):
res = client.get("/user/keys", headers=_auth())
assert res.status_code == 200
data = res.json()
assert data["configured"] == []
assert data["corrupted_providers"] == []

def test_authenticated_with_keys_returns_providers(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase(["openai", "anthropic"])), \
patch("api.services.key_store.decrypt_key", return_value="plaintext"):
res = client.get("/user/keys", headers=_auth())
assert res.status_code == 200
data = res.json()
assert set(data["configured"]) == {"openai", "anthropic"}
assert data["corrupted_providers"] == []

def test_corrupted_key_appears_in_corrupted_providers(self):
"""A row whose encrypted_key cannot be decrypted appears in corrupted_providers, not configured."""
with patch("api.services.key_store._supabase", return_value=_mock_supabase(["openai"])), \
patch("api.services.key_store.decrypt_key", side_effect=Exception("bad token")):
res = client.get("/user/keys", headers=_auth())
assert res.status_code == 200
data = res.json()
assert data["configured"] == []
assert "openai" in data["corrupted_providers"]

def test_demo_user_returns_demo_flag(self):
"""In testnet mode get_current_user returns 'demo-user' → special response."""
with patch.dict(os.environ, {"SOVEREIGN_ENV": "testnet"}):
# Need to reload the dependency — use testnet env override
res = client.get("/user/keys") # no auth needed in testnet
assert res.status_code == 200
data = res.json()
assert data.get("demo") is True
assert data["configured"] == []
assert data["corrupted_providers"] == []


# ── POST /user/keys/{provider} ─────────────────────────────────────────────────

class TestSaveKey:
def test_no_auth_returns_401(self):
res = client.post("/user/keys/openai", json={"key": "sk-test"})
assert res.status_code == 401

def test_invalid_provider_returns_400(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase()):
res = client.post("/user/keys/fakeprovider", json={"key": "abc"}, headers=_auth())
assert res.status_code == 400
assert "Unknown provider" in res.json()["detail"]

def test_empty_key_returns_400(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase()):
res = client.post("/user/keys/openai", json={"key": " "}, headers=_auth())
assert res.status_code == 400
assert "empty" in res.json()["detail"].lower()

def test_valid_key_saved_returns_200(self):
mock_cipher = MagicMock()
mock_cipher.encrypt.return_value = b"encrypted-ciphertext"

with patch("api.services.key_store._supabase", return_value=_mock_supabase()), \
patch("api.services.key_store._cipher", return_value=mock_cipher):
res = client.post("/user/keys/openai", json={"key": "sk-realkey"}, headers=_auth())
assert res.status_code == 200
assert res.json()["saved"] == "openai"

def test_all_valid_providers_accepted(self):
"""All providers in the valid set return 200."""
valid_providers = ["openai", "anthropic", "google", "mistral", "groq", "ollama"]
mock_cipher = MagicMock()
mock_cipher.encrypt.return_value = b"ciphertext"

for provider in valid_providers:
with patch("api.services.key_store._supabase", return_value=_mock_supabase()), \
patch("api.services.key_store._cipher", return_value=mock_cipher):
res = client.post(f"/user/keys/{provider}", json={"key": "test-key"}, headers=_auth())
assert res.status_code == 200, f"Expected 200 for provider {provider}, got {res.status_code}"

def test_missing_key_field_returns_422(self):
res = client.post("/user/keys/openai", json={}, headers=_auth())
assert res.status_code == 422


# ── DELETE /user/keys/{provider} ──────────────────────────────────────────────

class TestDeleteKey:
def test_no_auth_returns_401(self):
res = client.delete("/user/keys/openai")
assert res.status_code == 401

def test_invalid_provider_returns_400(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase()):
res = client.delete("/user/keys/badprovider", headers=_auth())
assert res.status_code == 400

def test_valid_provider_returns_200(self):
with patch("api.services.key_store._supabase", return_value=_mock_supabase()):
res = client.delete("/user/keys/openai", headers=_auth())
assert res.status_code == 200
assert res.json()["deleted"] == "openai"

def test_delete_nonexistent_key_still_200(self):
"""Deleting a provider that has no key is a no-op — not an error."""
with patch("api.services.key_store._supabase", return_value=_mock_supabase([])):
res = client.delete("/user/keys/anthropic", headers=_auth())
assert res.status_code == 200


# ── key_store.py unit tests ───────────────────────────────────────────────────

class TestKeyStore:
"""Direct unit tests for encrypt/decrypt functions."""

def test_encrypt_decrypt_roundtrip(self):
"""Fernet encrypt → decrypt returns original key."""
from cryptography.fernet import Fernet
secret = Fernet.generate_key().decode()
with patch.dict(os.environ, {"USER_KEYS_ENCRYPTION_SECRET": secret}):
# Reset lru_cache so new secret is picked up
from api.services.key_store import _cipher, encrypt_key, decrypt_key
_cipher.cache_clear()
plaintext = "sk-testkey-12345"
ciphertext = encrypt_key(plaintext)
assert ciphertext != plaintext
assert decrypt_key(ciphertext) == plaintext
_cipher.cache_clear()

def test_encrypt_different_calls_different_ciphertext(self):
"""Fernet uses random IV — same input produces different ciphertext each call."""
from cryptography.fernet import Fernet
secret = Fernet.generate_key().decode()
with patch.dict(os.environ, {"USER_KEYS_ENCRYPTION_SECRET": secret}):
from api.services.key_store import _cipher, encrypt_key
_cipher.cache_clear()
ct1 = encrypt_key("sk-same-key")
ct2 = encrypt_key("sk-same-key")
assert ct1 != ct2 # different IVs → different ciphertext
_cipher.cache_clear()

def test_missing_secret_raises_runtime_error(self):
"""Missing USER_KEYS_ENCRYPTION_SECRET → RuntimeError."""
with patch.dict(os.environ, {"USER_KEYS_ENCRYPTION_SECRET": ""}):
from api.services.key_store import _cipher
_cipher.cache_clear()
with pytest.raises(RuntimeError, match="USER_KEYS_ENCRYPTION_SECRET"):
_cipher()
_cipher.cache_clear()
