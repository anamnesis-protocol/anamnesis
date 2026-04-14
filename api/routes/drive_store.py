"""
api/routes/drive_store.py — SAC-Drive: Token-Gated Encrypted File Storage endpoints.

All routes require an active vault session (session_id query param or body field).
token_id is resolved from the session — client never sends it directly.

Endpoints:
  POST   /drive/init                       — create drive index (first time only)
  GET    /drive/files?session_id=          — list files (metadata only)
  POST   /drive/upload?session_id=         — upload and encrypt a file (multipart)
  GET    /drive/file/{uuid}?session_id=    — download and decrypt a file
  DELETE /drive/file/{uuid}?session_id=    — remove file from index
"""

import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.drive_store import (
    init_drive,
    upload_file,
    download_file,
    list_files,
    delete_file,
)
from api.session_store import get_session

router = APIRouter(prefix="/drive", tags=["drive"])

_MAX_UPLOAD_BYTES = 1_024 * 1_024  # 1 MB — matches HFS hard limit


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InitRequest(BaseModel):
    session_id: str


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
def drive_init(req: InitRequest):
    """Create a new drive index on HFS for this token. Call once at account setup."""
    token_id = _resolve_session(req.session_id)
    try:
        file_id = init_drive(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"initialized": True, "index_file_id": file_id}


@router.get("/files")
def drive_list_files(session_id: str = Query(...)):
    """Return file listing with metadata. No content downloaded."""
    token_id = _resolve_session(session_id)
    try:
        files = list_files(token_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"files": files}


@router.post("/upload")
async def drive_upload(
    session_id: str = Query(...),
    tags: str = Query(default=""),
    file: UploadFile = File(...),
):
    """
    Encrypt and upload a file to HFS.
    Returns drive file UUID (not the HFS file_id).

    - Max file size: 1 MB (HFS limit)
    - File written to a temp path, passed to upload_file(), then cleaned up
    - tags: comma-separated list of tags (optional)
    """
    token_id = _resolve_session(session_id)

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(content):,} bytes. Limit is 1 MB.",
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Write to temp file so upload_file() can use pathlib.read_bytes()
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        file_uuid = upload_file(token_id, tmp_path, tags=tag_list)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"file_uuid": file_uuid, "filename": file.filename, "size_bytes": len(content)}


@router.get("/file/{file_uuid}")
def drive_download(file_uuid: str, session_id: str = Query(...)):
    """
    Fetch, decrypt, and return a file. Integrity verified (SHA-256) before delivery.
    Returns raw file bytes with appropriate Content-Type.
    """
    token_id = _resolve_session(session_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            out_path = download_file(token_id, file_uuid, output_dir=tmp_dir)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            # Integrity check failed
            raise HTTPException(status_code=422, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        content = Path(out_path).read_bytes()
        filename = Path(out_path).name

    import mimetypes

    mime, _ = mimetypes.guess_type(filename)

    return Response(
        content=content,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/file/{file_uuid}")
def drive_delete(file_uuid: str, session_id: str = Query(...)):
    """Remove a file from the drive index. Encrypted blob remains on HFS."""
    token_id = _resolve_session(session_id)
    try:
        delete_file(token_id, file_uuid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": file_uuid}
