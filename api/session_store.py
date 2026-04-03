"""
api/session_store.py — In-memory session store with TTL.

For the SaaS MVP, sessions are stored in process memory.
Production upgrade path: replace _store with a Redis client.

Each session tracks:
- The token_id and serial for HCS audit logging
- Session-scoped crypto keys (section_key + index_key) for re-encryption at close
- Full vault index dict + index HFS file ID for writing back to Hedera at close
- Content hashes at session open (for SESSION_ENDED delta)
- Expiry (SESSION_TTL_HOURS from open time)

Security note (patent sub-claim — Session-Scoped Key Lifecycle):
 Keys are stored as bytearray so they can be explicitly zeroed before eviction.
 close_session() zeros both keys before removing the session from the store,
 bounding key material lifetime to the open-to-close session window.
 Keys are never written to disk, never sent to the client.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

SESSION_TTL_HOURS = 4


@dataclass
class Session:
    session_id: str
    token_id: str
    serial: int
    # Session-scoped crypto keys — stored as bytearray so they can be zeroed on close.
    # These are the HKDF-derived keys from session open (Claim 14).
    # Never written to disk. Zeroed by close_session() before eviction.
    section_key: bytearray
    index_key: bytearray
    # HFS file ID for the vault index — needed to update index at session close
    # without creating a new file (avoids contract re-registration).
    index_file_id: str
    # Full index dict from session open: {section_name: file_id, "_section_hashes": {...}}
    # Retained so session close can update changed sections without re-pulling the index.
    full_section_ids: dict
    # SHA-256 hex of each section's content at open time (for delta on close)
    start_hashes: dict[str, str]
    # Loaded section names (not content — keep content out of memory after delivery)
    sections_loaded: list[str]
    # Decrypted vault context — retained server-side for chat (never re-sent by client).
    # Patent model-agnostic claim: same context injected as system prompt for any AI model.
    # Zeroed by _zero_and_evict() at session close alongside the crypto keys.
    context_sections: dict[str, str]
    created_at: datetime
    expires_at: datetime
    # Last AI model used in this session — recorded for auto session_state summary at close.
    # Has default so it can be set mid-session without re-constructing the dataclass.
    last_model: str = ""
    # Supabase user UUID — empty string for demo/testnet (no JWT at session open).
    # Used to load per-user AI API keys from key_store on first chat request.
    user_id: str = ""
    # Per-user AI API keys — lazily loaded on first /chat/models or /chat/message request.
    # Sentinel: None → demo/testnet mode → use server .env keys
    # {} → real user with no keys configured → no models shown
    # {...} → real user with at least one key → use those keys
    # Zeroed at session close alongside section_key and context_sections.
    user_api_keys: dict | None = None

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def created_iso(self) -> str:
        return self.created_at.isoformat()

    @property
    def expires_iso(self) -> str:
        return self.expires_at.isoformat()


# Process-level store — keyed by session_id
_store: dict[str, Session] = {}

# Session lock table — prevents concurrent sessions for the same vault.
# Maps token_id → active session_id. A vault may only have one active session
# at a time — opening a second session while one is active returns 409.
# Released by close_session() and _zero_and_evict() (including TTL expiry).
_locks: dict[str, str] = {}


def acquire_lock(token_id: str, session_id: str) -> bool:
    """
    Acquire the session lock for a vault (token_id).

    Returns True if the lock was acquired.
    Returns False if a non-expired session already holds the lock.
    Expired lock holders are evicted before the new session acquires the lock.
    """
    existing_session_id = _locks.get(token_id)
    if existing_session_id:
        existing = _store.get(existing_session_id)
        if existing and not existing.expired:
            return False  # vault is locked by an active session
        # Lock held by a stale or expired session — evict and re-acquire
        if existing:
            _zero_and_evict(existing_session_id, existing)
        _locks.pop(token_id, None)
    _locks[token_id] = session_id
    return True


def release_lock(token_id: str, session_id: str) -> None:
    """Release the session lock if this session holds it."""
    if _locks.get(token_id) == session_id:
        _locks.pop(token_id, None)


def get_lock_holder(token_id: str) -> str | None:
    """Return the session_id currently holding the lock, or None."""
    return _locks.get(token_id)


def create_session(
    token_id: str,
    serial: int,
    context_sections: dict[str, bytes],
    section_key: bytes,
    index_key: bytes,
    index_file_id: str,
    full_section_ids: dict,
    user_id: str = "",
) -> Session:
    """
    Create and register a new session.

    Args:
        token_id: Context token ID
        serial: NFT serial number
        context_sections: {section_name: content_bytes} loaded at open time.
            Used to compute start_hashes AND stored as decoded strings
            for server-side chat context injection.
        section_key: 32-byte HKDF section key from session open. Stored as
            bytearray so it can be zeroed at session close.
        index_key: 32-byte HKDF index key from session open. Same lifecycle.
        index_file_id: HFS file ID of the vault index — used to update index at close.
        full_section_ids: Complete index dict from session open — used at close to
            re-encrypt and push only changed sections.

    Returns:
        Session object
    """
    now = datetime.now(timezone.utc)
    session = Session(
        session_id=str(uuid.uuid4()),
        token_id=token_id,
        serial=serial,
        section_key=bytearray(section_key),
        index_key=bytearray(index_key),
        index_file_id=index_file_id,
        full_section_ids=dict(full_section_ids),
        start_hashes={
            name: hashlib.sha256(content).hexdigest()
            for name, content in context_sections.items()
        },
        sections_loaded=list(context_sections.keys()),
        # Retain decoded context server-side for chat — client sends only session_id + message.
        # Zeroed alongside crypto keys at _zero_and_evict().
        context_sections={
            name: content.decode("utf-8", errors="replace")
            for name, content in context_sections.items()
        },
        created_at=now,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        user_id=user_id,
        # user_api_keys: None = demo/testnet (env fallback)
        # {} will be set after first Supabase lookup for real users
        user_api_keys=None,
    )
    _store[session.session_id] = session
    # Acquire vault lock — one active session per token_id
    if not acquire_lock(token_id, session.session_id):
        # Race condition: shouldn't normally happen since open_session checks first
        _store.pop(session.session_id, None)
        raise ValueError(f"Vault '{token_id}' is already locked by an active session.")
    return session


def get_session(session_id: str) -> Session | None:
    """
    Retrieve a session by ID. Returns None if not found or expired.
    Expired sessions are evicted on access (keys zeroed on eviction).
    """
    session = _store.get(session_id)
    if not session:
        return None
    if session.expired:
        _zero_and_evict(session_id, session)
        return None
    return session


def close_session(session_id: str) -> Session | None:
    """
    Zero key material and remove session from store.

    The section_key and index_key bytearrays are overwritten with zeros before
    the session is evicted — bounding key lifetime to the open-to-close window.
    Returns the closed session (keys already zeroed), or None if not found.
    """
    session = _store.get(session_id)
    if not session:
        return None
    return _zero_and_evict(session_id, session)


def _zero_and_evict(session_id: str, session: Session) -> Session:
    """
    Overwrite key material and context with zeros/empty, then remove from store.
    Explicit clearing before GC — Python's GC is non-deterministic.

    Clears:
    - section_key / index_key bytearrays (crypto keys — overwritten with \\x00)
    - context_sections dict (decrypted vault content — strings replaced with empty)
    """
    session.section_key[:] = b"\x00" * len(session.section_key)
    session.index_key[:] = b"\x00" * len(session.index_key)
    for k in list(session.context_sections.keys()):
        session.context_sections[k] = ""
    session.context_sections.clear()
    # Zero per-user API keys alongside crypto keys
    if session.user_api_keys:
        for k in list(session.user_api_keys.keys()):
            session.user_api_keys[k] = ""
        session.user_api_keys.clear()
    session.user_api_keys = None
    _store.pop(session_id, None)
    release_lock(session.token_id, session_id)
    return session


def update_section_id(session_id: str, section_name: str, file_id: str) -> bool:
    """
    Update full_section_ids with a new or updated section/bundle file_id.

    Called after a bundle is pushed mid-session so that session close includes
    the bundle's HFS file_id in the vault index update. Non-atomic — safe for
    single-session use (each session is owned by one request context at a time).

    Args:
        session_id: UUID of the active session.
        section_name: Full section name including prefix (e.g. 'dir:sessions').
        file_id: HFS file ID string (e.g. '0.0.1234567').

    Returns:
        True if session was found and updated; False if session not found.
    """
    session = _store.get(session_id)
    if not session:
        return False
    session.full_section_ids[section_name] = file_id
    return True


def active_count() -> int:
    """Return number of non-expired sessions (for monitoring)."""
    return sum(1 for s in _store.values() if not s.expired)
