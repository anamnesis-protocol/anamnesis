"""
api/routes/vault.py — Dir bundle push/pull/list endpoints.

Extends the sovereign AI context system to let SaaS users store arbitrary
named knowledge bundles (sessions, projects, research, etc.) on HFS alongside
their identity sections — encrypted with the same HKDF-derived session key,
recoverable anytime via wallet signature.

Endpoints:
POST /vault/bundle — push a named dir bundle (requires active session)
GET /vault/bundles?session_id= — list bundle names in the vault index
GET /vault/bundle/{name}?session_id= — pull and decrypt a specific bundle

Bundle format (same as VAULT_DIRS bundles pushed by vault_push.py):
- Stored on HFS as a gzip-compressed AES-GCM ciphertext
- AAD: b"dir:dir:{bundle_name}:{token_id}" (matches push_dir_section convention)
- Section key: same HKDF-derived key as identity sections (from session)
- Section name in vault index: "dir:{bundle_name}"

Session close automatically includes any pushed bundles in the vault index update
(via update_section_id() which updates session.full_section_ids).
"""

import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.vault import bundle_from_dict, unbundle_to_dict
from src.crypto import compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.event_log import log_event

from api.limiter import limiter
from api.models import (
    BundlePushRequest,
    BundlePushResponse,
    BundleListResponse,
    BundlePullResponse,
    )
from api.session_store import get_session, update_section_id

router = APIRouter(prefix="/vault", tags=["vault"])

# Bundle name validation — alphanumeric, hyphens, underscores only, max 64 chars.
# Prevents path traversal and keeps HFS section names clean.
_BUNDLE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,62}[a-z0-9]$|^[a-z0-9]$")
_MAX_FILES = 500 # guard against oversized bundles
_MAX_FILE_CONTENT_BYTES = 512 * 1024 # 512 KB per file (uncompressed)


def _validate_bundle_name(name: str) -> None:
    if not _BUNDLE_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail=(
            f"Invalid bundle_name '{name}'. "
            "Must be 1-64 chars, lowercase alphanumeric, hyphens, or underscores. "
            "Must start and end with an alphanumeric character."
            ),
            )


    def _full_name(bundle_name: str) -> str:
        """HFS section name: 'dir:{bundle_name}'."""
        return f"dir:{bundle_name}"


        def _bundle_aad(full_name: str, token_id: str) -> bytes:
            """
            AAD for bundle ciphertexts — must match push_dir_section() convention exactly.
            push_dir_section uses: f"dir:{dir_name}:{token_id}" where dir_name is already "dir:..."
            So for dir_name="dir:sessions": AAD = b"dir:dir:sessions:{token_id}"
            """
            return f"dir:{full_name}:{token_id}".encode("utf-8")


            # ---------------------------------------------------------------------------
            # POST /vault/bundle — push a named dir bundle
            # ---------------------------------------------------------------------------

            @router.post("/bundle", response_model=BundlePushResponse)
            @limiter.limit("20/minute")
            def push_bundle(request: Request, req: BundlePushRequest) -> BundlePushResponse:
                """
                Push a named dir bundle to HFS under the user's sovereign vault.

                The bundle is encrypted with the session's derived section key and stored
                on HFS. The bundle's file_id is recorded in the session so session close
                includes it in the vault index update.

                Bundle lifecycle:
                - First push → FileCreate on HFS (store_context)
                - Subsequent pushes with same bundle_name → FileUpdate + FileAppend (update_context)
                - Vault index updated at session close (not immediately — deferred for efficiency)
                """
                # ── Session lookup ────────────────────────────────────────────────────────
                session = get_session(req.session_id)
                if not session:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Session '{req.session_id}' not found or expired.",
                        )

                    # ── Input validation ─────────────────────────────────────────────────────
                    _validate_bundle_name(req.bundle_name)

                    if not req.files:
                        raise HTTPException(status_code=422, detail="files dict cannot be empty.")

                        if len(req.files) > _MAX_FILES:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Too many files ({len(req.files)}). Maximum is {_MAX_FILES}.",
                                )

                            for path, content in req.files.items():
                                if len(content.encode("utf-8")) > _MAX_FILE_CONTENT_BYTES:
                                    raise HTTPException(
                                        status_code=422,
                                        detail=f"File '{path}' exceeds {_MAX_FILE_CONTENT_BYTES // 1024} KB limit.",
                                        )

                                    # ── Bundle and encrypt ───────────────────────────────────────────────────
                                    token_id = session.token_id
                                    full_name = _full_name(req.bundle_name)
                                    aad = _bundle_aad(full_name, token_id)
                                    section_key = bytes(session.section_key)

                                    bundle_bytes = bundle_from_dict(req.files)
                                    payload = compress(bundle_bytes)

                                    existing_file_id: str | None = session.full_section_ids.get(full_name)

                                    try:
                                        if existing_file_id:
                                            update_context(section_key, existing_file_id, payload, token_id, aad)
                                            file_id = existing_file_id
                                        else:
                                            file_id = store_context(section_key, payload, token_id, aad)
                                    finally:
                                        # Explicit zero of local key copy (belt-and-suspenders)
                                        section_key = b"\x00" * len(section_key) # type: ignore[assignment]

                                        # ── Record file_id in session (picked up by session close → vault index) ─
                                        update_section_id(req.session_id, full_name, file_id)

                                        # ── Log BUNDLE_PUSHED to HCS ─────────────────────────────────────────────
                                        hcs_logged = False
                                        try:
                                            log_event(
                                                event_type="BUNDLE_PUSHED",
                                                payload={
                                                "token_id": token_id,
                                                "bundle_name": full_name,
                                                "file_id": file_id,
                                                "files_stored": len(req.files),
                                                "updated": existing_file_id is not None,
                                                },
                                                )
                                            hcs_logged = True
                                        except Exception:
                                            pass # Non-fatal — bundle is on HFS regardless

                                            return BundlePushResponse(
                                                bundle_name=req.bundle_name,
                                                file_id=file_id,
                                                files_stored=len(req.files),
                                                hcs_logged=hcs_logged,
                                                )


                                            # ---------------------------------------------------------------------------
                                            # GET /vault/bundles — list bundle names in vault index
                                            # ---------------------------------------------------------------------------

                @router.get("/bundles", response_model=BundleListResponse)
                def list_bundles(session_id: str) -> BundleListResponse:
                    """
                    List all dir bundle names available in this vault's index.

                    Returns bundle names without the 'dir:' prefix (e.g. 'sessions', 'projects').
                    Bundles are identified by keys starting with 'dir:' in the vault index.
                    """
                    session = get_session(session_id)
                    if not session:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Session '{session_id}' not found or expired.",
                            )

                        bundles = [
                            name[4:] # strip "dir:" prefix
                            for name in session.full_section_ids
                            if name.startswith("dir:") and isinstance(session.full_section_ids[name], str)
                            ]

                        return BundleListResponse(bundles=sorted(bundles))


                        # ---------------------------------------------------------------------------
                        # GET /vault/bundle/{bundle_name} — pull a specific bundle
                        # ---------------------------------------------------------------------------

                    @router.get("/bundle/{bundle_name}", response_model=BundlePullResponse)
                    def pull_bundle(bundle_name: str, session_id: str) -> BundlePullResponse:
                        """
                        Pull and decrypt a specific dir bundle from HFS.

                        Returns the bundle's files as a {relative_path: utf-8 content} dict.
                        Requires an active session — decryption uses the session's derived key.

                        Note: The bundle must have been pushed (and the vault index updated at
                        session close) before it can be pulled in a subsequent session.
                        Bundles pushed in the current session are available immediately.
                        """
                        session = get_session(session_id)
                        if not session:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Session '{session_id}' not found or expired.",
                                )

                            _validate_bundle_name(bundle_name)

                            full_name = _full_name(bundle_name)
                            file_id: str | None = session.full_section_ids.get(full_name)

                            if not file_id or not isinstance(file_id, str):
                                raise HTTPException(
                                    status_code=404,
                                    detail=(
                                    f"Bundle '{bundle_name}' not found in vault index. "
                                    "Push the bundle first with POST /vault/bundle."
                                    ),
                                    )

                                token_id = session.token_id
                                aad = _bundle_aad(full_name, token_id)
                                section_key = bytes(session.section_key)

                                try:
                                    raw = load_context(section_key, file_id, token_id, aad)
                                    bundle_bytes = decompress(raw)
                                    files = unbundle_to_dict(bundle_bytes)
                                except Exception as exc:
                                    raise HTTPException(
                                        status_code=502,
                                        detail=f"Failed to decrypt bundle '{bundle_name}': {exc}",
                                        )
                                finally:
                                    section_key = b"\x00" * len(section_key) # type: ignore[assignment]

                                    return BundlePullResponse(bundle_name=bundle_name, files=files)
