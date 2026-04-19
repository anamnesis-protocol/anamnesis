"""
pass_store.py — SAC-Pass: Token-Gated Password Manager

Architecture:
  - Password vault = encrypted JSON stored on Hedera HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-pass-v1")
  - Vault index file_id stored in Supabase (profiles.vault_file_ids) with local cache fallback
  - No master password. No company holds keys. Proof of token ownership = access.

Vault JSON structure (plaintext before encryption):
  {
    "version": 1,
    "created_at": "...",
    "entries": {
      "<uuid>": {
        "name": "GitHub",
        "username": "lee@example.com",
        "password": "hunter2",
        "url": "https://github.com",
        "notes": "",
        "created_at": "...",
        "updated_at": "..."
      }
    }
  }

The entire JSON blob is encrypted as one unit before HFS storage.
"""

import json
import uuid
from datetime import datetime, timezone

from src.crypto import derive_key, compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.vault import get_wallet_signature
from src.event_log import log_event
from src.vault_index_store import get_service_data, set_service_data

# Purpose-separated key — never reuses vault or drive keys
_INFO_PASS = b"sovereign-ai-pass-v1"
_AAD_PASS = b"sac-pass-vault-v1"
_SERVICE = "pass"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_pass_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_PASS)


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------


def init_vault(token_id: str) -> str:
    """
    Create a new empty password vault on HFS.
    Returns the HFS file_id of the vault.
    """
    existing = get_service_data(token_id, _SERVICE)
    if existing:
        raise RuntimeError(
            f"Pass vault already exists at {existing}. Use get_vault() to access it."
        )

    key = get_pass_key(token_id)

    vault = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entries": {},
    }
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    file_id = store_context(key, payload, token_id, _AAD_PASS)

    set_service_data(token_id, _SERVICE, file_id)

    log_event("PASS_VAULT_CREATED", {"token_id": token_id, "file_id": file_id})
    print(f"[sac-pass] Vault created on HFS: {file_id}")
    return file_id


def get_vault(token_id: str) -> dict:
    """Fetch, decrypt, and return the password vault as a dict."""
    file_id = get_service_data(token_id, _SERVICE)
    if not file_id:
        raise RuntimeError("No pass vault found. Run init_vault() first.")

    key = get_pass_key(token_id)
    raw = load_context(key, file_id, token_id, _AAD_PASS)
    plaintext = decompress(raw)
    return json.loads(plaintext.decode("utf-8"))


def _save_vault(token_id: str, vault: dict) -> None:
    """Encrypt and push updated vault back to HFS."""
    file_id = get_service_data(token_id, _SERVICE)
    key = get_pass_key(token_id)

    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    update_context(key, file_id, payload, token_id, _AAD_PASS)


# ---------------------------------------------------------------------------
# Entry CRUD
# ---------------------------------------------------------------------------


def add_entry(
    token_id: str,
    name: str,
    username: str,
    password: str,
    url: str = "",
    notes: str = "",
) -> str:
    """Add a new entry to the vault. Returns the entry ID."""
    vault = get_vault(token_id)
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    vault["entries"][entry_id] = {
        "name": name,
        "username": username,
        "password": password,
        "url": url,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }

    _save_vault(token_id, vault)
    log_event("PASS_ENTRY_ADDED", {"token_id": token_id, "entry_name": name})
    return entry_id


def update_entry(token_id: str, entry_id: str, **kwargs) -> None:
    """Update fields on an existing entry. Accepts name, username, password, url, notes."""
    vault = get_vault(token_id)
    if entry_id not in vault["entries"]:
        raise KeyError(f"No entry with id {entry_id}")

    allowed = {"name", "username", "password", "url", "notes"}
    for k, v in kwargs.items():
        if k in allowed:
            vault["entries"][entry_id][k] = v

    vault["entries"][entry_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_vault(token_id, vault)
    log_event("PASS_ENTRY_UPDATED", {"token_id": token_id, "entry_id": entry_id})


def delete_entry(token_id: str, entry_id: str) -> None:
    """Remove an entry from the vault."""
    vault = get_vault(token_id)
    if entry_id not in vault["entries"]:
        raise KeyError(f"No entry with id {entry_id}")

    name = vault["entries"][entry_id]["name"]
    del vault["entries"][entry_id]
    _save_vault(token_id, vault)
    log_event("PASS_ENTRY_DELETED", {"token_id": token_id, "entry_name": name})


def list_entries(token_id: str) -> list[dict]:
    """Return all entries without passwords (safe to display)."""
    vault = get_vault(token_id)
    return [
        {
            "id": eid,
            "name": e["name"],
            "username": e["username"],
            "url": e["url"],
            "updated_at": e["updated_at"],
        }
        for eid, e in vault["entries"].items()
    ]


def get_password(token_id: str, entry_id: str) -> str:
    """Retrieve the password for a specific entry."""
    vault = get_vault(token_id)
    if entry_id not in vault["entries"]:
        raise KeyError(f"No entry with id {entry_id}")
    return vault["entries"][entry_id]["password"]
