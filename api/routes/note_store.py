"""
api/routes/note_store.py — SAC-Pass Notes: Secure Notes endpoints.

All routes require an active vault session (session_id query param).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /pass/note                     — add note → note_id
  GET    /pass/notes?session_id=        — list notes (no content)
  GET    /pass/note/{id}?session_id=    — get note content
  PATCH  /pass/note/{id}                — update note
  DELETE /pass/note/{id}?session_id=    — delete note
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.note_store import (
    init_vault,
    get_vault,
    add_note,
    update_note,
    delete_note,
    list_notes,
    get_note,
)
from api.session_store import get_session

router = APIRouter(prefix="/pass", tags=["pass-notes"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AddNoteRequest(BaseModel):
    session_id: str
    type: str  # credit_card, document, custom
    title: str
    content: dict


class UpdateNoteRequest(BaseModel):
    session_id: str
    type: str | None = None
    title: str | None = None
    content: dict | None = None


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


@router.get("/notes")
def notes_list(session_id: str = Query(...)):
    """Return all notes without content (safe to display)."""
    token_id = _resolve_session(session_id)
    try:
        notes = list_notes(token_id)
    except RuntimeError:
        # Vault not initialized - auto-initialize
        try:
            init_vault(token_id)
            notes = []
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    return {"notes": notes}


@router.post("/note")
def notes_add(req: AddNoteRequest):
    """Add a new note to the vault. Returns note_id."""
    token_id = _resolve_session(req.session_id)
    try:
        note_id = add_note(
            token_id,
            note_type=req.type,
            title=req.title,
            content=req.content,
        )
    except RuntimeError:
        # Vault not initialized - auto-initialize and retry
        try:
            init_vault(token_id)
            note_id = add_note(
                token_id,
                note_type=req.type,
                title=req.title,
                content=req.content,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    return {"note_id": note_id}


@router.get("/note/{note_id}")
def notes_get(note_id: str, session_id: str = Query(...)):
    """Retrieve the content for a specific note."""
    token_id = _resolve_session(session_id)
    try:
        content = get_note(token_id, note_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"note_id": note_id, "content": content}


@router.patch("/note/{note_id}")
def notes_update(note_id: str, req: UpdateNoteRequest):
    """Update one or more fields on an existing note."""
    token_id = _resolve_session(req.session_id)
    fields = {k: v for k, v in req.model_dump(exclude={"session_id"}).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        update_note(token_id, note_id, **fields)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"updated": note_id}


@router.delete("/note/{note_id}")
def notes_delete(note_id: str, session_id: str = Query(...)):
    """Remove a note from the vault."""
    token_id = _resolve_session(session_id)
    try:
        delete_note(token_id, note_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": note_id}
