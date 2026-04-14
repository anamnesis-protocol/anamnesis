"""
note_store.py — SAC-Pass Notes: Encrypted Secure Notes Storage

Architecture:
  - Notes vault = encrypted JSON stored on Hedera HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-notes-v1")
  - Vault index file_id cached locally in .notes_index.json
  - Supports multiple note types: credit_card, document, custom

Vault JSON structure (plaintext before encryption):
  {
    "version": 1,
    "created_at": "...",
    "notes": {
      "<uuid>": {
        "type": "credit_card",
        "title": "Chase Visa",
        "content": {
          "cardholder": "John Doe",
          "number": "4111111111111111",
          "expiry": "12/25",
          "cvv": "123",
          "pin": "1234",
          "notes": "Primary card"
        },
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
_INFO_NOTES = b"sovereign-ai-notes-v1"
_AAD_NOTES = b"sac-notes-vault-v1"

# Local cache for notes vault file_id
_NOTES_INDEX_CACHE = Path(__file__).parent.parent / ".notes_index.json"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_notes_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_NOTES)


# ---------------------------------------------------------------------------
# Local cache helpers
# ---------------------------------------------------------------------------


def _load_notes_cache() -> dict:
    if not _NOTES_INDEX_CACHE.exists():
        return {}
    with open(_NOTES_INDEX_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_notes_cache(data: dict) -> None:
    with open(_NOTES_INDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------


def init_vault(token_id: str) -> str:
    """Create a new empty notes vault on HFS. Returns the HFS file_id."""
    cache = _load_notes_cache()
    if cache.get("file_id"):
        raise RuntimeError(
            f"Notes vault already exists at {cache['file_id']}. Use get_vault() to access it."
        )

    key = get_notes_key(token_id)

    vault = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": {},
    }
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    compressed = compress(plaintext)
    ciphertext = encrypt_context(compressed, key, aad=_AAD_NOTES)

    client = get_client()
    contract_id = get_validator_contract_id()
    file_id = store_context(client, contract_id, token_id, ciphertext, memo="notes-vault-v1")

    cache["file_id"] = file_id
    _save_notes_cache(cache)

    log_event("NOTES_VAULT_CREATED", {"token_id": token_id, "file_id": file_id})
    return file_id


def get_vault(token_id: str) -> dict:
    """Load and decrypt the notes vault."""
    cache = _load_notes_cache()
    file_id = cache.get("file_id")
    if not file_id:
        raise RuntimeError("Notes vault not initialized. Call init_vault() first.")

    key = get_notes_key(token_id)
    client = get_client()
    ciphertext = load_context(client, file_id)
    compressed = decrypt_context(ciphertext, key, aad=_AAD_NOTES)
    plaintext = decompress(compressed)
    return json.loads(plaintext)


def _save_vault(token_id: str, vault: dict) -> None:
    """Encrypt and save the vault back to HFS."""
    cache = _load_notes_cache()
    file_id = cache.get("file_id")
    if not file_id:
        raise RuntimeError("Notes vault not initialized.")

    key = get_notes_key(token_id)
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    compressed = compress(plaintext)
    ciphertext = encrypt_context(compressed, key, aad=_AAD_NOTES)

    client = get_client()
    update_context(client, file_id, ciphertext)


# ---------------------------------------------------------------------------
# Note CRUD operations
# ---------------------------------------------------------------------------


def add_note(token_id: str, note_type: str, title: str, content: dict) -> str:
    """Add a new note to the vault. Returns note_id."""
    vault = get_vault(token_id)
    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    vault["notes"][note_id] = {
        "type": note_type,
        "title": title,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }

    _save_vault(token_id, vault)
    log_event("NOTE_ADDED", {"token_id": token_id, "note_id": note_id, "type": note_type})
    return note_id


def list_notes(token_id: str) -> list[dict]:
    """Return all notes without content (metadata only)."""
    vault = get_vault(token_id)
    return [
        {
            "id": note_id,
            "type": note["type"],
            "title": note["title"],
            "updated_at": note["updated_at"],
        }
        for note_id, note in vault["notes"].items()
    ]


def get_note(token_id: str, note_id: str) -> dict:
    """Get a specific note with full content."""
    vault = get_vault(token_id)
    if note_id not in vault["notes"]:
        raise KeyError(f"Note {note_id} not found")
    return vault["notes"][note_id]["content"]


def update_note(token_id: str, note_id: str, **fields) -> None:
    """Update note fields (type, title, content)."""
    vault = get_vault(token_id)
    if note_id not in vault["notes"]:
        raise KeyError(f"Note {note_id} not found")

    note = vault["notes"][note_id]
    for key, value in fields.items():
        if key in ("type", "title", "content"):
            note[key] = value
    note["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save_vault(token_id, vault)
    log_event("NOTE_UPDATED", {"token_id": token_id, "note_id": note_id})


def delete_note(token_id: str, note_id: str) -> None:
    """Delete a note from the vault."""
    vault = get_vault(token_id)
    if note_id not in vault["notes"]:
        raise KeyError(f"Note {note_id} not found")

    del vault["notes"][note_id]
    _save_vault(token_id, vault)
    log_event("NOTE_DELETED", {"token_id": token_id, "note_id": note_id})
