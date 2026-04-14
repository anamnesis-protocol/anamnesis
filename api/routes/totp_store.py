"""
api/routes/totp_store.py — SAC-Pass TOTP: Authenticator endpoints.

All routes require an active vault session (session_id query param).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /pass/totp                     — add TOTP entry → entry_id
  GET    /pass/totp?session_id=         — list entries (with secrets for code gen)
  DELETE /pass/totp/{id}?session_id=    — delete entry
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.totp_store import (
    init_vault,
    get_vault,
    add_entry,
    delete_entry,
    list_entries,
)
from api.session_store import get_session

router = APIRouter(prefix="/pass", tags=["pass-totp"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AddTOTPRequest(BaseModel):
    session_id: str
    name: str
    secret: str
    issuer: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_session(session_id: str) -> str:
    """Validate session and return token_id."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=401,
            detail=f"Session '{session_id}' not found or expired.",
        )
    return session.token_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/totp")
def totp_list(session_id: str = Query(...)):
    """Return all TOTP entries with secrets (needed for code generation)."""
    token_id = _resolve_session(session_id)
    try:
        entries = list_entries(token_id)
    except RuntimeError:
        # Vault not initialized - auto-initialize
        try:
            init_vault(token_id)
            entries = []
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    return {"entries": entries}


@router.post("/totp")
def totp_add(req: AddTOTPRequest):
    """Add a new TOTP entry to the vault. Returns entry_id."""
    token_id = _resolve_session(req.session_id)
    try:
        entry_id = add_entry(
            token_id,
            name=req.name,
            secret=req.secret,
            issuer=req.issuer,
        )
    except RuntimeError:
        # Vault not initialized - auto-initialize and retry
        try:
            init_vault(token_id)
            entry_id = add_entry(
                token_id,
                name=req.name,
                secret=req.secret,
                issuer=req.issuer,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    return {"entry_id": entry_id}


@router.delete("/totp/{entry_id}")
def totp_delete(entry_id: str, session_id: str = Query(...)):
    """Remove a TOTP entry from the vault."""
    token_id = _resolve_session(session_id)
    try:
        delete_entry(token_id, entry_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": entry_id}
