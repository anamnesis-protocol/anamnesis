"""
api/routes/pass_store.py — SAC-Pass: Token-Gated Password Manager endpoints.

All routes require an active vault session (session_id query param).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /pass/init                     — create vault (first time only)
  GET    /pass/entries?session_id=      — list entries (no passwords)
  POST   /pass/entry?session_id=        — add entry → entry_id
  GET    /pass/entry/{id}?session_id=   — get password for entry
  PATCH  /pass/entry/{id}?session_id=   — update entry fields
  DELETE /pass/entry/{id}?session_id=   — delete entry
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pass_store import (
    init_vault,
    get_vault,
    add_entry,
    update_entry,
    delete_entry,
    list_entries,
    get_password,
)
from api.session_store import get_session

router = APIRouter(prefix="/pass", tags=["pass"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AddEntryRequest(BaseModel):
    session_id: str
    name: str
    username: str
    password: str
    url: str = ""
    notes: str = ""


class UpdateEntryRequest(BaseModel):
    session_id: str
    name: str | None = None
    username: str | None = None
    password: str | None = None
    url: str | None = None
    notes: str | None = None


class InitRequest(BaseModel):
    session_id: str


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


@router.post("/init")
def pass_init(req: InitRequest):
    """Create a new password vault on HFS for this token. Call once at account setup."""
    token_id = _resolve_session(req.session_id)
    try:
        file_id = init_vault(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"initialized": True, "file_id": file_id}


@router.get("/entries")
def pass_list_entries(session_id: str = Query(...)):
    """Return all vault entries without passwords (safe to display)."""
    token_id = _resolve_session(session_id)
    try:
        entries = list_entries(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load vault: {exc}")
    return {"entries": entries}


@router.post("/entry")
def pass_add_entry(req: AddEntryRequest):
    """Add a new credential entry to the vault. Returns entry_id."""
    token_id = _resolve_session(req.session_id)
    try:
        entry_id = add_entry(
            token_id,
            name=req.name,
            username=req.username,
            password=req.password,
            url=req.url,
            notes=req.notes,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"entry_id": entry_id}


@router.get("/entry/{entry_id}")
def pass_get_password(entry_id: str, session_id: str = Query(...)):
    """
    Retrieve the password for a specific vault entry.
    Only called when user explicitly requests a password — never returned in list.
    """
    token_id = _resolve_session(session_id)
    try:
        password = get_password(token_id, entry_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"entry_id": entry_id, "password": password}


@router.patch("/entry/{entry_id}")
def pass_update_entry(entry_id: str, req: UpdateEntryRequest):
    """Update one or more fields on an existing entry."""
    token_id = _resolve_session(req.session_id)
    fields = {k: v for k, v in req.model_dump(exclude={"session_id"}).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        update_entry(token_id, entry_id, **fields)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"updated": entry_id}


@router.delete("/entry/{entry_id}")
def pass_delete_entry(entry_id: str, session_id: str = Query(...)):
    """Remove an entry from the vault."""
    token_id = _resolve_session(session_id)
    try:
        delete_entry(token_id, entry_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": entry_id}
