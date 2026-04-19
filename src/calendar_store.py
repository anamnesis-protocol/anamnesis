"""
calendar_store.py — SAC-Calendar: Token-Gated Encrypted Calendar

Architecture:
  - Calendar vault = encrypted JSON stored on Hedera HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-calendar-v1")
  - Vault index file_id stored in Supabase (profiles.vault_file_ids) with local cache fallback
  - No master password. Proof of token ownership = access.

Vault JSON structure (plaintext before encryption):
  {
    "version": 1,
    "created_at": "...",
    "events": {
      "<uuid>": {
        "title": "Team sync",
        "start": "2026-04-15T09:00:00+00:00",
        "end": "2026-04-15T10:00:00+00:00",
        "all_day": false,
        "description": "",
        "location": "",
        "color": "violet",
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

# Purpose-separated key — never reuses vault, pass, drive, or mail keys
_INFO_CALENDAR = b"sovereign-ai-calendar-v1"
_AAD_CALENDAR = b"sac-calendar-vault-v1"
_SERVICE = "calendar"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_calendar_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_CALENDAR)


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------


def init_vault(token_id: str) -> str:
    """
    Create a new empty calendar vault on HFS.
    Returns the HFS file_id of the vault.
    """
    existing = get_service_data(token_id, _SERVICE)
    if existing:
        raise RuntimeError(
            f"Calendar vault already exists at {existing}. Use get_vault() to access it."
        )

    key = get_calendar_key(token_id)

    vault = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "events": {},
    }
    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    file_id = store_context(key, payload, token_id, _AAD_CALENDAR)

    set_service_data(token_id, _SERVICE, file_id)

    log_event("CALENDAR_VAULT_CREATED", {"token_id": token_id, "file_id": file_id})
    print(f"[sac-calendar] Vault created on HFS: {file_id}")
    return file_id


def get_vault(token_id: str) -> dict:
    """Fetch, decrypt, and return the calendar vault as a dict."""
    file_id = get_service_data(token_id, _SERVICE)
    if not file_id:
        raise RuntimeError("No calendar vault found. Run init_vault() first.")

    key = get_calendar_key(token_id)
    raw = load_context(key, file_id, token_id, _AAD_CALENDAR)
    plaintext = decompress(raw)
    return json.loads(plaintext.decode("utf-8"))


def _save_vault(token_id: str, vault: dict) -> None:
    """Encrypt and push updated vault back to HFS."""
    file_id = get_service_data(token_id, _SERVICE)
    key = get_calendar_key(token_id)

    plaintext = json.dumps(vault, indent=2).encode("utf-8")
    payload = compress(plaintext)
    update_context(key, file_id, payload, token_id, _AAD_CALENDAR)


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------


def add_event(
    token_id: str,
    title: str,
    start: str,
    end: str = "",
    all_day: bool = False,
    description: str = "",
    location: str = "",
    color: str = "violet",
) -> str:
    """Add a new event to the calendar vault. Returns the event ID."""
    vault = get_vault(token_id)
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    vault["events"][event_id] = {
        "title": title,
        "start": start,
        "end": end,
        "all_day": all_day,
        "description": description,
        "location": location,
        "color": color,
        "created_at": now,
        "updated_at": now,
    }

    _save_vault(token_id, vault)
    log_event("CALENDAR_EVENT_ADDED", {"token_id": token_id, "title": title})
    return event_id


def update_event(token_id: str, event_id: str, **kwargs) -> None:
    """Update fields on an existing event."""
    vault = get_vault(token_id)
    if event_id not in vault["events"]:
        raise KeyError(f"No event with id {event_id}")

    allowed = {"title", "start", "end", "all_day", "description", "location", "color"}
    for k, v in kwargs.items():
        if k in allowed:
            vault["events"][event_id][k] = v

    vault["events"][event_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_vault(token_id, vault)
    log_event("CALENDAR_EVENT_UPDATED", {"token_id": token_id, "event_id": event_id})


def delete_event(token_id: str, event_id: str) -> None:
    """Remove an event from the vault."""
    vault = get_vault(token_id)
    if event_id not in vault["events"]:
        raise KeyError(f"No event with id {event_id}")

    title = vault["events"][event_id]["title"]
    del vault["events"][event_id]
    _save_vault(token_id, vault)
    log_event("CALENDAR_EVENT_DELETED", {"token_id": token_id, "title": title})


def list_events(token_id: str) -> list[dict]:
    """Return all calendar events."""
    vault = get_vault(token_id)
    return [{"id": eid, **event} for eid, event in vault["events"].items()]


def get_event(token_id: str, event_id: str) -> dict:
    """Return a single event by ID."""
    vault = get_vault(token_id)
    if event_id not in vault["events"]:
        raise KeyError(f"No event with id {event_id}")
    return {"id": event_id, **vault["events"][event_id]}
