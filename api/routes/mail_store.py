"""
api/routes/mail_store.py — SAC-Mail: Token-Gated Encrypted Messaging endpoints.

All routes require an active vault session (session_id query param or body field).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /mail/init                          — create mailbox (first time only)
  GET    /mail/inbox?session_id=             — list inbox messages (no bodies)
  GET    /mail/sent?session_id=              — list sent messages (no bodies)
  GET    /mail/unread?session_id=            — unread message count
  POST   /mail/send?session_id=             — send a message to another token
  GET    /mail/message/{id}?session_id=      — fetch and decrypt a message body
  DELETE /mail/message/{id}?session_id=      — delete from inbox or sent folder
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.mail_store import (
    init_mailbox,
    send_message,
    read_inbox,
    read_sent,
    get_message,
    delete_message,
    unread_count,
)
from api.session_store import get_session

router = APIRouter(prefix="/mail", tags=["mail"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InitRequest(BaseModel):
    session_id: str


class SendRequest(BaseModel):
    session_id: str
    to_token_id: str
    subject: str
    body: str


class DeleteRequest(BaseModel):
    session_id: str
    folder: str = "inbox"  # "inbox" or "sent"


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
def mail_init(req: InitRequest):
    """Create inbox and sent folder on HFS for this token. Call once at account setup."""
    token_id = _resolve_session(req.session_id)
    try:
        ids = init_mailbox(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"initialized": True, **ids}


@router.get("/inbox")
def mail_inbox(session_id: str = Query(...)):
    """Return inbox message list — metadata only, no message bodies."""
    token_id = _resolve_session(session_id)
    try:
        messages = read_inbox(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"messages": messages}


@router.get("/sent")
def mail_sent(session_id: str = Query(...)):
    """Return sent folder message list — metadata only."""
    token_id = _resolve_session(session_id)
    try:
        messages = read_sent(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"messages": messages}


@router.get("/unread")
def mail_unread(session_id: str = Query(...)):
    """Return count of unread messages in inbox."""
    token_id = _resolve_session(session_id)
    try:
        count = unread_count(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"unread": count}


@router.post("/send")
def mail_send(req: SendRequest):
    """
    Encrypt and deliver a message to another companion token's inbox.
    Returns message_id (UUID).

    The recipient's mailbox must be initialized (init_mailbox called for to_token_id).
    """
    from_token_id = _resolve_session(req.session_id)

    if not req.subject.strip():
        raise HTTPException(status_code=400, detail="Subject cannot be empty.")
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="Body cannot be empty.")
    if from_token_id == req.to_token_id:
        raise HTTPException(status_code=400, detail="Cannot send a message to yourself.")

    try:
        message_id = send_message(
            from_token_id=from_token_id,
            to_token_id=req.to_token_id,
            subject=req.subject,
            body=req.body,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))

    return {"message_id": message_id, "to_token_id": req.to_token_id}


@router.get("/message/{message_id}")
def mail_get_message(message_id: str, session_id: str = Query(...)):
    """
    Fetch, decrypt, and return full message content.
    Marks message as read in the inbox index.
    """
    token_id = _resolve_session(session_id)
    try:
        message = get_message(token_id, message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return message


@router.delete("/message/{message_id}")
def mail_delete_message(message_id: str, req: DeleteRequest):
    """
    Remove a message from inbox or sent folder.
    folder: "inbox" (default) or "sent"
    """
    token_id = _resolve_session(req.session_id)
    try:
        delete_message(token_id, message_id, folder=req.folder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": message_id, "folder": req.folder}
