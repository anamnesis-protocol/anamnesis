"""
api/routes/knowledge_store.py — Context Import: token-gated encrypted knowledge section.

Lets users import their own markdown/text files into the 'knowledge' vault section.
That section is loaded at session open alongside identity sections and RAG-indexed,
so the AI companion can retrieve relevant context from it on every chat turn.

Endpoints:
  POST   /knowledge/import                   — add/replace files in the knowledge section
  GET    /knowledge/files?session_id=        — list imported files (name + size)
  DELETE /knowledge/file?session_id=&name=   — remove a single file
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.knowledge_store import (
    read_files,
    write_files,
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    MAX_FILES,
)
from api.session_store import get_session

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ImportFile(BaseModel):
    name: str = Field(description="Filename (e.g. 'notes.md', 'README.txt')")
    content: str = Field(description="Plain text / markdown content")


class ImportRequest(BaseModel):
    session_id: str
    files: list[ImportFile] = Field(description="Files to add or replace")


class FileEntry(BaseModel):
    name: str
    size_chars: int


class FilesResponse(BaseModel):
    files: list[FileEntry]
    total_chars: int


class ImportResponse(BaseModel):
    added: list[str]
    replaced: list[str]
    total_files: int
    total_chars: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_or_raise(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=401,
            detail=f"Session '{session_id}' not found or expired.",
        )
    return session


def _validate_filename(name: str) -> None:
    """Basic filename validation — no path traversal, reasonable length."""
    if not name or len(name) > 128:
        raise HTTPException(status_code=400, detail=f"Invalid filename: '{name}'")
    if any(c in name for c in ("/", "\\", "\x00", "\n")):
        raise HTTPException(
            status_code=400,
            detail=f"Filename must not contain path separators or control characters: '{name}'",
        )


# ---------------------------------------------------------------------------
# POST /knowledge/import
# ---------------------------------------------------------------------------


@router.post("/import", response_model=ImportResponse)
def import_files(req: ImportRequest) -> ImportResponse:
    """
    Add or replace files in the user's knowledge section.

    - Files with the same name as an existing file replace it.
    - New file names are appended.
    - Content is written to HFS as the 'knowledge' vault section and
      the in-memory RAG index is rebuilt immediately.
    """
    session = _get_session_or_raise(req.session_id)

    # Validate incoming files
    for f in req.files:
        _validate_filename(f.name)
        if len(f.content.encode("utf-8")) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{f.name}' exceeds {MAX_FILE_BYTES // 1024} KB limit.",
            )

    existing = read_files(session)
    added = []
    replaced = []

    for f in req.files:
        if f.name in existing:
            replaced.append(f.name)
        else:
            added.append(f.name)
        existing[f.name] = f.content

    if len(existing) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Knowledge section is limited to {MAX_FILES} files.",
        )

    total_bytes = sum(len(v.encode("utf-8")) for v in existing.values())
    if total_bytes > MAX_TOTAL_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Total knowledge section size would exceed {MAX_TOTAL_BYTES // 1024 // 1024} MB.",
        )

    try:
        write_files(session, existing)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to write knowledge section to Hedera: {exc}",
        )

    total_chars = sum(len(v) for v in existing.values())
    return ImportResponse(
        added=added,
        replaced=replaced,
        total_files=len(existing),
        total_chars=total_chars,
    )


# ---------------------------------------------------------------------------
# GET /knowledge/files
# ---------------------------------------------------------------------------


@router.get("/files", response_model=FilesResponse)
def list_files(session_id: str = Query(...)) -> FilesResponse:
    """Return the list of imported files and their sizes."""
    session = _get_session_or_raise(session_id)
    files = read_files(session)
    entries = [FileEntry(name=name, size_chars=len(content)) for name, content in files.items()]
    total = sum(e.size_chars for e in entries)
    return FilesResponse(files=entries, total_chars=total)


# ---------------------------------------------------------------------------
# DELETE /knowledge/file
# ---------------------------------------------------------------------------


@router.delete("/file")
def delete_file(
    session_id: str = Query(...),
    name: str = Query(..., description="Filename to remove"),
):
    """Remove a single file from the knowledge section."""
    session = _get_session_or_raise(session_id)
    _validate_filename(name)

    files = read_files(session)
    if name not in files:
        raise HTTPException(status_code=404, detail=f"File '{name}' not found.")

    del files[name]

    try:
        write_files(session, files)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update knowledge section on Hedera: {exc}",
        )

    return {"deleted": name, "remaining": len(files)}
