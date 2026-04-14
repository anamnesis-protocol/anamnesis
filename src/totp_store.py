"""
totp_store.py — SAC-Pass TOTP: Encrypted Authenticator Storage

Architecture:
  - TOTP vault = encrypted JSON stored on Hedera HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-totp-v1")
  - Vault index file_id cached locally in .totp_index.json
  - Stores TOTP secrets for 2FA code generation

Vault JSON structure (plaintext before encryption):
  {
    "version": 1,
    "created_at": "...",
    "entries": {
      "<uuid>": {
        "name": "GitHub",
        "secret": "JBSWY3DPEHPK3PXP",
        "issuer": "GitHub Inc",
        "created_at": "...",
        "updated_at": "..."
      }
    }
  }
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_client, get_validator_contract_id
from src.crypto import derive_key, encrypt_context, decrypt_context, compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.vault import get_wallet_signature
from src.event_log import log_event

# Purpose-separated key
_INFO_TOTP = b"sovereign-ai-totp-v1"
_AAD_TOTP = b"sac-totp-vault-v1"

# Local cache for TOTP vault file_id
_TOTP_INDEX_CACHE = Path(__file__).parent.parent / ".totp_index.json"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_totp_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_TOTP)


# ---------------------------------------------------------------------------
# Local cache helpers
# ---------------------------------------------------------------------------


def _load_totp_cache() -> dict:
    if not _TOTP_INDEX_CACHE.exists():
        return {}
    with open(_TOTP_INDEX_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_totp_cache(data: dict) -> None:
    with open(_TOTP_INDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------


def init_vault(token_id: str) -> str:
    """Create a new empty TOTP vault on HFS. Returns the HFS file_id."""
    cache = _load_totp_cache()
    if cache.get("file_id"):
        raise RuntimeError(
            f"TOTP vault already exists at {cache['file_id']}. Use get_vault() to access it."
        )

    key = get_totp_key(token_id)

    vault = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": {},
    }
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    compressed = compress(plaintext)
    ciphertext = encrypt_context(compressed, key, aad=_AAD_TOTP)

    client = get_client()
    contract_id = get_validator_contract_id()
    file_id = store_context(client, contract_id, token_id, ciphertext, memo="totp-vault-v1")

    cache["file_id"] = file_id
    _save_totp_cache(cache)

    log_event("TOTP_VAULT_CREATED", {"token_id": token_id, "file_id": file_id})
    return file_id


def get_vault(token_id: str) -> dict:
    """Load and decrypt the TOTP vault."""
    cache = _load_totp_cache()
    file_id = cache.get("file_id")
    if not file_id:
        raise RuntimeError("TOTP vault not initialized. Call init_vault() first.")

    key = get_totp_key(token_id)
    client = get_client()
    ciphertext = load_context(client, file_id)
    compressed = decrypt_context(ciphertext, key, aad=_AAD_TOTP)
    plaintext = decompress(compressed)
    return json.loads(plaintext)


def _save_vault(token_id: str, vault: dict) -> None:
    """Encrypt and save the vault back to HFS."""
    cache = _load_totp_cache()
    file_id = cache.get("file_id")
    if not file_id:
        raise RuntimeError("TOTP vault not initialized.")

    key = get_totp_key(token_id)
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    compressed = compress(plaintext)
    ciphertext = encrypt_context(compressed, key, aad=_AAD_TOTP)

    client = get_client()
    update_context(client, file_id, ciphertext)


# ---------------------------------------------------------------------------
# TOTP CRUD operations
# ---------------------------------------------------------------------------


def add_entry(token_id: str, name: str, secret: str, issuer: str | None = None) -> str:
    """Add a new TOTP entry to the vault. Returns entry_id."""
    vault = get_vault(token_id)
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    vault["entries"][entry_id] = {
        "name": name,
        "secret": secret,
        "issuer": issuer,
        "created_at": now,
        "updated_at": now,
    }

    _save_vault(token_id, vault)
    log_event("TOTP_ENTRY_ADDED", {"token_id": token_id, "entry_id": entry_id, "name": name})
    return entry_id


def list_entries(token_id: str) -> list[dict]:
    """Return all TOTP entries WITH secrets (needed for code generation)."""
    vault = get_vault(token_id)
    return [
        {
            "id": entry_id,
            "name": entry["name"],
            "secret": entry["secret"],
            "issuer": entry.get("issuer"),
            "updated_at": entry["updated_at"],
        }
        for entry_id, entry in vault["entries"].items()
    ]


def delete_entry(token_id: str, entry_id: str) -> None:
    """Delete a TOTP entry from the vault."""
    vault = get_vault(token_id)
    if entry_id not in vault["entries"]:
        raise KeyError(f"TOTP entry {entry_id} not found")

    del vault["entries"][entry_id]
    _save_vault(token_id, vault)
    log_event("TOTP_ENTRY_DELETED", {"token_id": token_id, "entry_id": entry_id})
