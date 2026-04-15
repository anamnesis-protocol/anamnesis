"""
api/routes/calendar_store.py — SAC-Calendar: Token-Gated Encrypted Calendar endpoints.

All routes require an active vault session (session_id query param or body field).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /calendar/init                      — create vault (first time only)
  GET    /calendar/events?session_id=        — list all events
  POST   /calendar/event?session_id=         — add event → event_id
  GET    /calendar/event/{id}?session_id=    — get single event
  PATCH  /calendar/event/{id}               — update event fields
  DELETE /calendar/event/{id}?session_id=   — delete event
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.calendar_store import (
    init_vault,
    get_vault,
    add_event,
    update_event,
    delete_event,
    list_events,
    get_event,
)
from api.session_store import get_session

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InitRequest(BaseModel):
    session_id: str


class AddEventRequest(BaseModel):
    session_id: str
    title: str
    start: str
    end: str = ""
    all_day: bool = False
    description: str = ""
    location: str = ""
    color: str = "violet"


class UpdateEventRequest(BaseModel):
    session_id: str
    title: str | None = None
    start: str | None = None
    end: str | None = None
    all_day: bool | None = None
    description: str | None = None
    location: str | None = None
    color: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_session(session_id: str) -> str:
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
def calendar_init(req: InitRequest):
    """Create a new calendar vault on HFS for this token. Call once at account setup."""
    token_id = _resolve_session(req.session_id)
    try:
        file_id = init_vault(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"initialized": True, "file_id": file_id}


@router.get("/events")
def calendar_list_events(session_id: str = Query(...)):
    """Return all calendar events."""
    token_id = _resolve_session(session_id)
    try:
        events = list_events(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"events": events}


@router.post("/event")
def calendar_add_event(req: AddEventRequest):
    """Add a new event to the calendar vault. Returns event_id."""
    token_id = _resolve_session(req.session_id)
    try:
        event_id = add_event(
            token_id,
            title=req.title,
            start=req.start,
            end=req.end,
            all_day=req.all_day,
            description=req.description,
            location=req.location,
            color=req.color,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"event_id": event_id}


@router.get("/event/{event_id}")
def calendar_get_event(event_id: str, session_id: str = Query(...)):
    """Return a single calendar event by ID."""
    token_id = _resolve_session(session_id)
    try:
        event = get_event(token_id, event_id)
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return event


@router.patch("/event/{event_id}")
def calendar_update_event(event_id: str, req: UpdateEventRequest):
    """Update one or more fields on an existing event."""
    token_id = _resolve_session(req.session_id)
    fields = {k: v for k, v in req.model_dump(exclude={"session_id"}).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        update_event(token_id, event_id, **fields)
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"updated": event_id}


@router.delete("/event/{event_id}")
def calendar_delete_event(event_id: str, session_id: str = Query(...)):
    """Remove an event from the calendar vault."""
    token_id = _resolve_session(session_id)
    try:
        delete_event(token_id, event_id)
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": event_id}
