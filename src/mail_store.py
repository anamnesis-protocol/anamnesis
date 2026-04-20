"""
mail_store.py — SAC-Mail: Token-Gated Encrypted Messaging

Architecture:
  - Each message encrypted individually on HFS using recipient's key
  - Inbox index (message manifest) stored encrypted on HFS per token
  - Sent folder stored encrypted on HFS per token
  - HCS topic used for delivery proof — sender logs {from, to, hfs_file_id}
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-mail-msg-v1")
  - AAD binds each message to message_id + recipient_token (prevents replay)
  - Mailbox file_ids stored in Supabase (profiles.vault_file_ids) with local cache fallback

Key separation (no cross-service key reuse):
  - Message key:     HKDF(..., info=b"sovereign-ai-mail-msg-v1")
  - Inbox index key: HKDF(..., info=b"sovereign-ai-mail-index-v1")
  - Sent index key:  HKDF(..., info=b"sovereign-ai-mail-sent-v1")

Delivery model:
  1. Sender derives recipient's inbox key (server-side, custodial operator)
  2. Encrypts message + stores on HFS → hfs_file_id
  3. Updates recipient's inbox index on HFS
  4. Logs MAIL_DELIVERED event to HCS (delivery proof, no content)
  5. Adds to sender's sent folder (encrypted with sender's key)

Inbox JSON (plaintext before encryption):
  {
    "version": 1,
    "messages": {
      "<uuid>": {
        "from_token":  "0.0.xxxxx",
        "subject":     "Hello",
        "hfs_file_id": "0.0.xxxxx",
        "size_bytes":  512,
        "sent_at":     "...",
        "read":        false
      }
    }
  }

Message JSON (plaintext before encryption):
  {
    "message_id":     "<uuid>",
    "from_token":     "0.0.xxxxx",
    "to_token":       "0.0.xxxxx",
    "subject":        "Hello",
    "body":           "...",
    "sent_at":        "..."
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

_INFO_MAIL_MSG = b"sovereign-ai-mail-msg-v1"
_INFO_MAIL_INDEX = b"sovereign-ai-mail-index-v1"
_INFO_MAIL_SENT = b"sovereign-ai-mail-sent-v1"
_SERVICE = "mail"

_HFS_MAX_BYTES = 1_024 * 1_024  # 1 MB


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def _msg_key(token_id: str) -> bytes:
    """Key for encrypting individual messages stored in recipient's mailbox."""
    return derive_key(token_id, get_wallet_signature(token_id), info=_INFO_MAIL_MSG)


def _index_key(token_id: str) -> bytes:
    """Key for the inbox index (message manifest)."""
    return derive_key(token_id, get_wallet_signature(token_id), info=_INFO_MAIL_INDEX)


def _sent_key(token_id: str) -> bytes:
    """Key for the sender's sent folder."""
    return derive_key(token_id, get_wallet_signature(token_id), info=_INFO_MAIL_SENT)


def _msg_aad(message_id: str, recipient_token_id: str) -> bytes:
    """AAD binds message ciphertext to specific message_id + recipient. Prevents replay."""
    return f"sac-mail-msg:{message_id}:{recipient_token_id}".encode("utf-8")


def _inbox_aad(token_id: str) -> bytes:
    return f"sac-mail-inbox:{token_id}".encode("utf-8")


def _sent_aad(token_id: str) -> bytes:
    return f"sac-mail-sent:{token_id}".encode("utf-8")


# ---------------------------------------------------------------------------
# Mailbox initialization
# ---------------------------------------------------------------------------


def init_mailbox(token_id: str) -> dict:
    """
    Create inbox and sent folder on HFS for a token.
    Returns {"inbox_file_id": ..., "sent_file_id": ...}.
    Safe to call at account creation time.
    """
    existing = get_service_data(token_id, _SERVICE) or {}
    if existing.get("inbox_file_id") and existing.get("sent_file_id"):
        raise RuntimeError(f"Mailbox already exists for {token_id}. Use read_inbox() to access it.")

    empty_inbox = {"version": 1, "messages": {}}
    empty_sent = {"version": 1, "messages": {}}

    inbox_raw = compress(json.dumps(empty_inbox, indent=2).encode("utf-8"))
    sent_raw = compress(json.dumps(empty_sent, indent=2).encode("utf-8"))

    inbox_file_id = store_context(_index_key(token_id), inbox_raw, token_id, _inbox_aad(token_id))
    sent_file_id = store_context(_sent_key(token_id), sent_raw, token_id, _sent_aad(token_id))

    ids = {"inbox_file_id": inbox_file_id, "sent_file_id": sent_file_id}
    set_service_data(token_id, _SERVICE, ids)

    log_event("MAIL_MAILBOX_CREATED", {"token_id": token_id, **ids})
    print(
        f"[sac-mail] Mailbox created for {token_id} — inbox: {inbox_file_id}, sent: {sent_file_id}"
    )
    return ids


# ---------------------------------------------------------------------------
# Inbox / sent folder read helpers
# ---------------------------------------------------------------------------


def _get_inbox(token_id: str) -> dict:
    data = get_service_data(token_id, _SERVICE) or {}
    file_id = data.get("inbox_file_id")
    if not file_id:
        raise RuntimeError(f"No mailbox for {token_id}. Run init_mailbox() first.")
    raw = load_context(_index_key(token_id), file_id, token_id, _inbox_aad(token_id))
    return json.loads(decompress(raw).decode("utf-8"))


def _save_inbox(token_id: str, inbox: dict) -> None:
    data = get_service_data(token_id, _SERVICE) or {}
    file_id = data["inbox_file_id"]
    raw = compress(json.dumps(inbox, indent=2).encode("utf-8"))
    update_context(_index_key(token_id), file_id, raw, token_id, _inbox_aad(token_id))


def _get_sent(token_id: str) -> dict:
    data = get_service_data(token_id, _SERVICE) or {}
    file_id = data.get("sent_file_id")
    if not file_id:
        raise RuntimeError(f"No mailbox for {token_id}. Run init_mailbox() first.")
    raw = load_context(_sent_key(token_id), file_id, token_id, _sent_aad(token_id))
    return json.loads(decompress(raw).decode("utf-8"))


def _save_sent(token_id: str, sent: dict) -> None:
    data = get_service_data(token_id, _SERVICE) or {}
    file_id = data["sent_file_id"]
    raw = compress(json.dumps(sent, indent=2).encode("utf-8"))
    update_context(_sent_key(token_id), file_id, raw, token_id, _sent_aad(token_id))


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def send_message(
    from_token_id: str,
    to_token_id: str,
    subject: str,
    body: str,
) -> str:
    """
    Encrypt and deliver a message to the recipient's HFS inbox.
    Returns the message_id (UUID).

    Both sender's sent folder and recipient's inbox are updated.
    HCS delivery proof is logged.
    """
    if len(body.encode("utf-8")) > _HFS_MAX_BYTES:
        raise ValueError(f"Message body too large. HFS limit is {_HFS_MAX_BYTES:,} bytes.")

    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    message = {
        "message_id": message_id,
        "from_token": from_token_id,
        "to_token": to_token_id,
        "subject": subject,
        "body": body,
        "sent_at": now,
    }

    # Encrypt message with recipient's key, AAD binds to this specific message + recipient
    payload = compress(json.dumps(message, indent=2).encode("utf-8"))
    aad = _msg_aad(message_id, to_token_id)
    hfs_file_id = store_context(_msg_key(to_token_id), payload, to_token_id, aad)

    # Update recipient's inbox index
    inbox = _get_inbox(to_token_id)
    inbox["messages"][message_id] = {
        "from_token": from_token_id,
        "subject": subject,
        "hfs_file_id": hfs_file_id,
        "size_bytes": len(body.encode("utf-8")),
        "sent_at": now,
        "read": False,
    }
    _save_inbox(to_token_id, inbox)

    # Update sender's sent folder
    sent = _get_sent(from_token_id)
    sent["messages"][message_id] = {
        "to_token": to_token_id,
        "subject": subject,
        "hfs_file_id": hfs_file_id,
        "size_bytes": len(body.encode("utf-8")),
        "sent_at": now,
    }
    _save_sent(from_token_id, sent)

    log_event(
        "MAIL_SENT",
        {
            "message_id": message_id,
            "from_token": from_token_id,
            "to_token": to_token_id,
            "subject": subject,
            "hfs_file_id": hfs_file_id,
        },
    )
    print(f"[sac-mail] Sent: '{subject}' → {to_token_id} (msg: {message_id[:8]}...)")
    return message_id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def read_inbox(token_id: str) -> list[dict]:
    """Return inbox message list without fetching bodies."""
    inbox = _get_inbox(token_id)
    return [
        {
            "id": mid,
            "from_token": m["from_token"],
            "subject": m["subject"],
            "size_bytes": m["size_bytes"],
            "sent_at": m["sent_at"],
            "read": m["read"],
        }
        for mid, m in inbox["messages"].items()
    ]


def read_sent(token_id: str) -> list[dict]:
    """Return sent folder message list without fetching bodies."""
    sent = _get_sent(token_id)
    return [
        {
            "id": mid,
            "to_token": m["to_token"],
            "subject": m["subject"],
            "size_bytes": m["size_bytes"],
            "sent_at": m["sent_at"],
        }
        for mid, m in sent["messages"].items()
    ]


def get_message(token_id: str, message_id: str) -> dict:
    """
    Fetch, decrypt, and return the full message body.
    Marks the message as read in the inbox index.
    """
    inbox = _get_inbox(token_id)
    if message_id not in inbox["messages"]:
        raise KeyError(f"No message {message_id} in inbox for {token_id}")

    meta = inbox["messages"][message_id]
    aad = _msg_aad(message_id, token_id)
    raw = load_context(_msg_key(token_id), meta["hfs_file_id"], token_id, aad)
    message = json.loads(decompress(raw).decode("utf-8"))

    if not meta["read"]:
        inbox["messages"][message_id]["read"] = True
        _save_inbox(token_id, inbox)

    log_event("MAIL_READ", {"token_id": token_id, "message_id": message_id})
    return message


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_message(token_id: str, message_id: str, folder: str = "inbox") -> None:
    """
    Remove a message from inbox or sent folder index.
    Encrypted blob remains on HFS (immutable ledger) but is no longer referenced.
    folder: "inbox" or "sent"
    """
    if folder == "inbox":
        index = _get_inbox(token_id)
        if message_id not in index["messages"]:
            raise KeyError(f"No message {message_id} in inbox")
        subject = index["messages"][message_id]["subject"]
        del index["messages"][message_id]
        _save_inbox(token_id, index)
    elif folder == "sent":
        index = _get_sent(token_id)
        if message_id not in index["messages"]:
            raise KeyError(f"No message {message_id} in sent folder")
        subject = index["messages"][message_id]["subject"]
        del index["messages"][message_id]
        _save_sent(token_id, index)
    else:
        raise ValueError("folder must be 'inbox' or 'sent'")

    log_event(
        "MAIL_DELETED",
        {
            "token_id": token_id,
            "message_id": message_id,
            "folder": folder,
            "subject": subject,
        },
    )
    print(f"[sac-mail] Deleted from {folder}: '{subject}'")
    print("  Note: encrypted blob remains on HFS (immutable ledger).")


# ---------------------------------------------------------------------------
# Unread count
# ---------------------------------------------------------------------------


def unread_count(token_id: str) -> int:
    """Return number of unread messages in inbox."""
    inbox = _get_inbox(token_id)
    return sum(1 for m in inbox["messages"].values() if not m["read"])
