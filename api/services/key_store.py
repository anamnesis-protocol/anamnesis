"""
api/services/key_store.py — Encrypted per-user AI API key storage.

Keys are Fernet-encrypted at the application layer before being written to
Supabase. Supabase only ever sees ciphertext. The plaintext key exists in
memory only during the chat request; it is never logged or returned by any
API endpoint.

Encryption:
 Fernet (AES-128-CBC + HMAC-SHA256, symmetric, authenticated).
 Secret: USER_KEYS_ENCRYPTION_SECRET env var — generate once with:
 python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Schema (Supabase `user_api_keys` table):
 user_id TEXT — Supabase UUID
 provider TEXT — 'openai' | 'anthropic' | 'google' | 'mistral' | 'groq' | 'ollama'
 encrypted_key TEXT — Fernet ciphertext (base64)
 UNIQUE(user_id, provider)

 Run this migration in Supabase SQL editor after adding new providers:
 ALTER TABLE user_api_keys
 DROP CONSTRAINT IF EXISTS user_api_keys_provider_check;
 ALTER TABLE user_api_keys
 ADD CONSTRAINT user_api_keys_provider_check
 CHECK (provider IN ('openai','anthropic','google','mistral','groq','ollama'));

Security note:
 get_configured_providers() returns only provider names — no decryption.
 get_user_keys() decrypts only when called (chat time), never at rest.
 Actual keys are never returned to the client by any endpoint.
"""

import logging
import os
from functools import lru_cache

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cipher
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _cipher():
    """Build and cache the Fernet instance. Raises if secret not set."""
    from cryptography.fernet import Fernet
    secret = os.getenv("USER_KEYS_ENCRYPTION_SECRET", "")
    if not secret:
        raise RuntimeError(
            "USER_KEYS_ENCRYPTION_SECRET is not configured. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(secret.encode() if isinstance(secret, str) else secret)


def encrypt_key(api_key: str) -> str:
    """Encrypt a plaintext API key. Returns Fernet ciphertext (base64 string)."""
    return _cipher().encrypt(api_key.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """Decrypt a Fernet ciphertext. Returns plaintext API key."""
    return _cipher().decrypt(encrypted.encode()).decode()


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

def _supabase():
    """Return a Supabase admin client (service role key — bypasses RLS)."""
    from supabase import create_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not configured.")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def save_user_key(user_id: str, provider: str, api_key: str) -> None:
    """
    Encrypt and upsert an API key for the given user + provider.
    If a key for that provider already exists, it is overwritten.
    """
    encrypted = encrypt_key(api_key)
    _supabase().table("user_api_keys").upsert(
        {
            "user_id": user_id,
            "provider": provider,
            "encrypted_key": encrypted,
            "updated_at": "now()",
        },
        on_conflict="user_id,provider",
    ).execute()


def get_user_keys(user_id: str) -> dict[str, str]:
    """
    Fetch and decrypt all API keys for a user.

    Returns:
        {provider: plaintext_api_key}
        Empty dict if the user has no keys configured.
    """
    result = (
        _supabase()
        .table("user_api_keys")
        .select("provider,encrypted_key")
        .eq("user_id", user_id)
        .execute()
    )
    keys = {}
    for row in result.data or []:
        try:
            keys[row["provider"]] = decrypt_key(row["encrypted_key"])
        except Exception:
            _log.warning(
                "BYOK key corrupted — skipping provider '%s' for user '%s'. "
                "Key may have been written with a different encryption secret.",
                row["provider"], user_id,
            )
    return keys


def get_configured_providers(user_id: str) -> list[str]:
    """
    Return the list of provider names that have a key configured.
    Does NOT decrypt — safe to call in list endpoints.
    """
    result = (
        _supabase()
        .table("user_api_keys")
        .select("provider")
        .eq("user_id", user_id)
        .execute()
    )
    return [row["provider"] for row in (result.data or [])]


def get_key_status(user_id: str) -> tuple[list[str], list[str]]:
    """
    Attempt to decrypt all stored keys for a user and categorise them.

    Returns:
        (configured, corrupted)
        configured — provider names whose key decrypts successfully.
        corrupted — provider names where decryption failed (tampered or
            written with a different USER_KEYS_ENCRYPTION_SECRET).

    Used by GET /user/keys so the frontend can prompt the user to re-enter
    a corrupted key rather than silently showing zero models.
    """
    result = (
        _supabase()
        .table("user_api_keys")
        .select("provider,encrypted_key")
        .eq("user_id", user_id)
        .execute()
    )
    configured: list[str] = []
    corrupted: list[str] = []
    for row in result.data or []:
        try:
            decrypt_key(row["encrypted_key"])
            configured.append(row["provider"])
        except Exception:
            _log.warning(
                "BYOK key corrupted — provider '%s' for user '%s' cannot be decrypted.",
                row["provider"], user_id,
            )
            corrupted.append(row["provider"])
    return configured, corrupted


def delete_user_key(user_id: str, provider: str) -> None:
    """Remove the stored key for a provider. No-op if not found."""
    _supabase().table("user_api_keys").delete().eq(
        "user_id", user_id
    ).eq("provider", provider).execute()
