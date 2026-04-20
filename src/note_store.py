"""
note_store.py — SAC-Pass Notes: Encrypted Secure Notes Storage

Architecture:
  - Notes vault = encrypted JSON stored on Hedera HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-notes-v1")
  - Vault index file_id stored in Supabase (profiles.vault_file_ids) with local cache fallback
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

from src.crypto import derive_key, compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.vault import get_wallet_signature
from src.event_log import log_event
from src.vault_index_store import get_service_data, set_service_data

# Purpose-separated key
_INFO_NOTES = b"sovereign-ai-notes-v1"
_AAD_NOTES = b"sac-notes-vault-v1"
_SERVICE = "notes"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_notes_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_NOTES)


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------


def init_vault(token_id: str) -> str:
    """Create a new empty notes vault on HFS. Returns the HFS file_id."""
    existing = get_service_data(token_id, _SERVICE)
    if existing:
        raise RuntimeError(
            f"Notes vault already exists at {existing}. Use get_vault() to access it."
        )

    key = get_notes_key(token_id)

    vault = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": {},
    }
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    file_id = store_context(key, payload, token_id, _AAD_NOTES)

    set_service_data(token_id, _SERVICE, file_id)
    log_event("NOTES_VAULT_CREATED", {"token_id": token_id, "file_id": file_id})
    print(f"[sac-notes] Vault created on HFS: {file_id}")
    return file_id


def get_vault(token_id: str) -> dict:
    """Load and decrypt the notes vault."""
    file_id = get_service_data(token_id, _SERVICE)
    if not file_id:
        raise RuntimeError("Notes vault not initialized. Call init_vault() first.")

    key = get_notes_key(token_id)
    raw = load_context(key, file_id, token_id, _AAD_NOTES)
    plaintext = decompress(raw)
    return json.loads(plaintext.decode("utf-8"))


def _save_vault(token_id: str, vault: dict) -> None:
    """Encrypt and save the vault back to HFS."""
    file_id = get_service_data(token_id, _SERVICE)
    key = get_notes_key(token_id)
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    update_context(key, file_id, payload, token_id, _AAD_NOTES)


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
