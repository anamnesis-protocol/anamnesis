"""
api/provision_store.py — In-memory store for pending user provisioning.

Tracks context tokens that have been minted (via /provision/start) but whose
vault has not yet been created (awaiting /provision/complete).

TTL: 1 hour — if the user doesn't complete within 1 hour, the pending record
expires and a new provision/start must be called. The context token is already on-chain
but has no vault registered, so it is inert until provision/complete runs.

Production upgrade: replace _store with Redis with TTL keys.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

PROVISION_TTL_MINUTES = 60


@dataclass
class PendingProvision:
    token_id: str
    account_id: str
    companion_name: str
    started_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def expires_iso(self) -> str:
        return self.expires_at.isoformat()


_store: dict[str, PendingProvision] = {}


def create_pending(token_id: str, account_id: str, companion_name: str) -> PendingProvision:
    """Register a pending provision after context token is minted."""
    now = datetime.now(timezone.utc)
    record = PendingProvision(
        token_id=token_id,
        account_id=account_id,
        companion_name=companion_name,
        started_at=now,
        expires_at=now + timedelta(minutes=PROVISION_TTL_MINUTES),
    )
    _store[token_id] = record
    return record


def get_pending(token_id: str) -> PendingProvision | None:
    """
    Retrieve a pending provision. Returns None if not found or expired.
    Expired records are evicted on access.
    """
    record = _store.get(token_id)
    if not record:
        return None
    if record.expired:
        del _store[token_id]
        return None
    return record


def complete_pending(token_id: str) -> PendingProvision | None:
    """Remove and return a pending provision (called after vault is created)."""
    return _store.pop(token_id, None)
