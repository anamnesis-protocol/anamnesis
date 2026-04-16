"""
api/routes/vault.py — Dir bundle push/pull/list + vault health check endpoints.

Extends the sovereign AI context system to let SaaS users store arbitrary
named knowledge bundles (sessions, projects, research, etc.) on HFS alongside
their identity sections — encrypted with the same HKDF-derived session key,
recoverable anytime via wallet signature.

Endpoints:
  POST /vault/bundle               — push a named dir bundle (requires active session)
  GET  /vault/bundles?session_id=  — list bundle names in the vault index
  GET  /vault/bundle/{name}?session_id= — pull and decrypt a specific bundle
  GET  /vault/health?session_id=   — health check on the user's decrypted HFS vault

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

from src.vault import (
    bundle_from_dict,
    unbundle_to_dict,
    push_section as _push_section,
    update_index as _update_index,
)
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
_MAX_FILES = 500  # guard against oversized bundles
_MAX_FILE_CONTENT_BYTES = 512 * 1024  # 512 KB per file (uncompressed)

# Expected identity sections — used for completeness check
_EXPECTED_SECTIONS = {"soul", "user", "config", "session_state", "system"}

# Context size thresholds (characters)
_SIZE_EMPTY_THRESHOLD = 100  # below this → effectively empty
_SIZE_LARGE_THRESHOLD = 50_000  # above this → warn (approaching model limits)
_SIZE_CRITICAL_THRESHOLD = 200_000  # above this → will overflow most models


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------


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

    # ── Input validation ──────────────────────────────────────────────────────
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

    # ── Bundle and encrypt ────────────────────────────────────────────────────
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
        section_key = b"\x00" * len(section_key)  # type: ignore[assignment]

    # ── Record file_id in session (picked up by session close → vault index) ─
    update_section_id(req.session_id, full_name, file_id)

    # ── Log BUNDLE_PUSHED to HCS ──────────────────────────────────────────────
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
        pass  # Non-fatal — bundle is on HFS regardless

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
        name[4:]  # strip "dir:" prefix
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
        section_key = b"\x00" * len(section_key)  # type: ignore[assignment]

    return BundlePullResponse(bundle_name=bundle_name, files=files)


# ---------------------------------------------------------------------------
# GET /vault/health — health check on the user's decrypted HFS vault
# ---------------------------------------------------------------------------


@router.get("/health")
def vault_health(session_id: str) -> dict:
    """
    Run health checks on the user's decrypted vault (in-memory from active session).

    Checks:
      completeness  — are all expected sections present and non-empty?
      size          — are any sections approaching model context limits?
      structure     — do sections have parseable markdown structure?
      staleness     — when was the vault last meaningfully updated?
      metadata      — do sections contain expected fields for their role?
      rag_index     — is the in-memory BM25 index built and populated?
      hfs_registry  — are all loaded sections registered in the vault index?

    Overall status:
      healthy   — all checks pass
      degraded  — at least one warning (non-critical issues)
      critical  — at least one check failed (vault may not function correctly)

    Requires an active session — vault content is already decrypted in memory.
    No additional Hedera calls are made.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired.",
        )

    sections = session.context_sections
    checks: dict[str, dict] = {}
    has_warning = False
    has_critical = False

    # ── 1. Completeness ───────────────────────────────────────────────────────
    present = {name for name, content in sections.items() if content.strip()}
    missing = sorted(_EXPECTED_SECTIONS - present)
    empty = sorted(
        name for name in _EXPECTED_SECTIONS if name in sections and not sections[name].strip()
    )
    completeness_status = "pass"
    if missing:
        completeness_status = "critical"
        has_critical = True
    elif empty:
        completeness_status = "warn"
        has_warning = True
    checks["completeness"] = {
        "status": completeness_status,
        "sections_present": sorted(present),
        "sections_missing": missing,
        "sections_empty": empty,
    }

    # ── 2. Size ───────────────────────────────────────────────────────────────
    size_issues: list[dict] = []
    size_status = "pass"
    for name in _EXPECTED_SECTIONS:
        content = sections.get(name, "")
        char_count = len(content)
        token_estimate = char_count // 4  # ~4 chars per token (rough)
        issue = None
        if char_count < _SIZE_EMPTY_THRESHOLD and char_count > 0:
            issue = "very short — likely placeholder content"
            size_status = "warn"
            has_warning = True
        elif char_count >= _SIZE_CRITICAL_THRESHOLD:
            issue = f"critical: {char_count:,} chars (~{token_estimate:,} tokens) — will overflow most models"
            size_status = "critical"
            has_critical = True
        elif char_count >= _SIZE_LARGE_THRESHOLD:
            issue = f"large: {char_count:,} chars (~{token_estimate:,} tokens) — monitor growth"
            if size_status == "pass":
                size_status = "warn"
            has_warning = True
        size_issues.append(
            {
                "section": name,
                "chars": char_count,
                "tokens_estimate": token_estimate,
                "issue": issue,
            }
        )
    checks["size"] = {
        "status": size_status,
        "sections": size_issues,
    }

    # ── 3. Structure ──────────────────────────────────────────────────────────
    structure_issues: list[dict] = []
    structure_status = "pass"
    for name in present:
        content = sections.get(name, "")
        has_header = bool(re.search(r"^#{1,4}\s+\S", content, re.MULTILINE))
        has_content = len(content.strip()) > 50
        issues = []
        if not has_header:
            issues.append("no markdown headers — content may be unstructured")
        if not has_content:
            issues.append("minimal content")
        if issues:
            structure_issues.append({"section": name, "issues": issues})
            if structure_status == "pass":
                structure_status = "warn"
            has_warning = True
    checks["structure"] = {
        "status": structure_status,
        "issues": structure_issues,
    }

    # ── 4. Staleness ──────────────────────────────────────────────────────────
    # Parse ISO dates (YYYY-MM-DD) from session_state to determine last update.
    # Flags the vault as stale if no recent date is found — stale context means
    # the AI is working from an outdated picture of the user's state.
    from datetime import datetime, timezone as _tz

    _STALE_WARN_DAYS = 14
    _STALE_CRITICAL_DAYS = 30
    _ISO_DATE_RE = re.compile(r"\b(20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b")

    state_content = sections.get("session_state", "")
    found_dates = _ISO_DATE_RE.findall(state_content)
    staleness_status = "pass"
    last_date_str = None
    days_since = None

    if found_dates:
        # Parse all found dates, take the most recent
        parsed = []
        for ds in found_dates:
            try:
                parsed.append(datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=_tz.utc))
            except ValueError:
                pass
        if parsed:
            most_recent = max(parsed)
            last_date_str = most_recent.strftime("%Y-%m-%d")
            days_since = (datetime.now(_tz.utc) - most_recent).days
            if days_since >= _STALE_CRITICAL_DAYS:
                staleness_status = "critical"
                has_critical = True
            elif days_since >= _STALE_WARN_DAYS:
                staleness_status = "warn"
                has_warning = True
        else:
            staleness_status = "warn"
            has_warning = True
    else:
        staleness_status = "warn"
        has_warning = True

    staleness_note = (
        f"last update: {last_date_str} ({days_since} days ago)"
        if days_since is not None
        else "no date found in session_state — update it regularly to keep context fresh"
    )
    checks["staleness"] = {
        "status": staleness_status,
        "last_date": last_date_str,
        "days_since_update": days_since,
        "note": staleness_note,
        "warn_threshold_days": _STALE_WARN_DAYS,
        "critical_threshold_days": _STALE_CRITICAL_DAYS,
    }

    # ── 5. Metadata ───────────────────────────────────────────────────────────
    # Each section has a role — check that it contains the structural elements
    # expected for that role. Missing metadata means the AI gets incomplete context.
    _SECTION_METADATA: dict[str, list[tuple[str, str]]] = {
        "soul": [
            (
                r"(?i)(directive|instruction|rule|you are|persona|identity|mission)",
                "identity/directive content",
            ),
            (r"^#{1,4}\s+\S", "at least one markdown header"),
        ],
        "user": [
            (r"(?i)(name|role|prefer|goal|work|background|profession)", "user profile fields"),
            (r"^#{1,4}\s+\S", "at least one markdown header"),
        ],
        "config": [
            (
                r"(?i)(model|provider|setting|config|prefer|tone|style|format|language)",
                "AI configuration fields",
            ),
        ],
        "session_state": [
            (r"\b20\d{2}-\d{2}-\d{2}\b", "at least one date entry"),
            (
                r"(?i)(session|last|active|current|working|project|status)",
                "session tracking content",
            ),
        ],
        "system": [
            (r"(?i)(vault|hedera|rag|mcp|skill|health)", "system capability content"),
            (r"^#{1,4}\s+\S", "at least one markdown header"),
        ],
    }

    metadata_issues: list[dict] = []
    metadata_status = "pass"
    for section_name, checks_list in _SECTION_METADATA.items():
        content = sections.get(section_name, "")
        if not content.strip():
            continue  # completeness check already flags empty sections
        section_issues = []
        for pattern, description in checks_list:
            if not re.search(pattern, content, re.MULTILINE):
                section_issues.append(f"missing: {description}")
        if section_issues:
            metadata_issues.append({"section": section_name, "issues": section_issues})
            if metadata_status == "pass":
                metadata_status = "warn"
            has_warning = True
    checks["metadata"] = {
        "status": metadata_status,
        "issues": metadata_issues,
    }

    # ── 6. Duplicate content ──────────────────────────────────────────────────
    # Detect when sections contain substantially the same content — a sign that
    # context was copy-pasted across sections rather than being purpose-separated.
    # Duplicate content wastes tokens and pollutes RAG retrieval (same chunks score
    # equally, diluting the relevance signal).
    #
    # Method: fingerprint each section's paragraphs (100+ chars); flag any paragraph
    # that appears verbatim in more than one section.
    _MIN_DUPE_CHARS = 120  # ignore short fragments — only flag substantial overlaps
    para_map: dict[str, list[str]] = {}  # fingerprint → [section_names]
    for sec_name, content in sections.items():
        for para in content.split("\n\n"):
            para = para.strip()
            if len(para) >= _MIN_DUPE_CHARS:
                fingerprint = para[:200]  # first 200 chars as fingerprint
                para_map.setdefault(fingerprint, []).append(sec_name)

    duplicate_pairs: list[dict] = []
    seen_fps: set[str] = set()
    for fp, sec_names in para_map.items():
        if len(sec_names) > 1 and fp not in seen_fps:
            seen_fps.add(fp)
            duplicate_pairs.append(
                {
                    "sections": sorted(set(sec_names)),
                    "preview": fp[:80] + ("..." if len(fp) > 80 else ""),
                }
            )

    dupe_status = "warn" if duplicate_pairs else "pass"
    if duplicate_pairs:
        has_warning = True
    checks["duplicate_content"] = {
        "status": dupe_status,
        "duplicate_count": len(duplicate_pairs),
        "duplicates": duplicate_pairs,
        "note": (
            f"{len(duplicate_pairs)} paragraph(s) appear in multiple sections — "
            "remove duplicates to improve RAG precision and reduce token usage"
            if duplicate_pairs
            else "no duplicate content detected"
        ),
    }

    # ── 7. RAG chunk quality ──────────────────────────────────────────────────
    # The BM25 index is only as good as its chunks. Check that:
    # - No chunks are too small to carry meaning (< 50 chars → retrieval noise)
    # - No chunks are too large (> 1200 chars → precision loss; should have been split)
    # - Average chunk size is in the retrieval-effective range (150–800 chars)
    _CHUNK_MIN_CHARS = 50
    _CHUNK_MAX_CHARS = 1200  # must match _MAX_CHUNK_CHARS in api/services/rag.py
    _CHUNK_IDEAL_MIN = 150
    _CHUNK_IDEAL_MAX = 800
    vault_index = session.vault_index

    if vault_index is None:
        rag_status = "unavailable"
        rag_chunks = 0
        rag_avg_chars = 0
        rag_tiny = 0
        rag_large = 0
        rag_note = "rank-bm25 not installed — run: pip install rank-bm25"
        has_warning = True
    elif vault_index.chunk_count == 0:
        rag_status = "warn"
        rag_chunks = 0
        rag_avg_chars = 0
        rag_tiny = 0
        rag_large = 0
        rag_note = "index is empty — sections may lack headers/paragraphs for chunking"
        has_warning = True
    else:
        rag_chunks = vault_index.chunk_count
        chunk_sizes = [len(c.text) for c in vault_index._chunks]
        rag_avg_chars = sum(chunk_sizes) // max(len(chunk_sizes), 1)
        rag_tiny = sum(1 for s in chunk_sizes if s < _CHUNK_MIN_CHARS)
        rag_large = sum(1 for s in chunk_sizes if s > _CHUNK_MAX_CHARS)
        quality_issues = []
        if rag_tiny > 0:
            quality_issues.append(
                f"{rag_tiny} chunk(s) under {_CHUNK_MIN_CHARS} chars — too small to retrieve meaningfully"
            )
        if rag_large > 0:
            quality_issues.append(
                f"{rag_large} chunk(s) over {_CHUNK_MAX_CHARS} chars — consider adding headers to split them"
            )
        if not (_CHUNK_IDEAL_MIN <= rag_avg_chars <= _CHUNK_IDEAL_MAX):
            quality_issues.append(
                f"avg chunk size {rag_avg_chars} chars is outside ideal range {_CHUNK_IDEAL_MIN}–{_CHUNK_IDEAL_MAX}"
            )
        if quality_issues:
            rag_status = "warn"
            has_warning = True
            rag_note = "; ".join(quality_issues)
        else:
            rag_status = "pass"
            rag_note = f"{rag_chunks} chunks, avg {rag_avg_chars} chars — retrieval quality good"
    checks["rag_index"] = {
        "status": rag_status,
        "chunks": rag_chunks,
        "avg_chars_per_chunk": rag_avg_chars,
        "tiny_chunks": rag_tiny,
        "oversized_chunks": rag_large,
        "note": rag_note,
    }

    # ── 8. Session state growth ───────────────────────────────────────────────
    # session_state is auto-updated on every session close. If it keeps growing
    # unchecked it will eventually dominate the context window. Warn before it
    # becomes a problem so the user knows to summarise/prune it.
    _STATE_WARN_CHARS = 8_000  # ~2k tokens — worth watching
    _STATE_CRITICAL_CHARS = 20_000  # ~5k tokens — will crowd out other sections
    state_chars = len(sections.get("session_state", ""))
    state_token_est = state_chars // 4

    if state_chars >= _STATE_CRITICAL_CHARS:
        growth_status = "critical"
        has_critical = True
        growth_note = (
            f"session_state is {state_chars:,} chars (~{state_token_est:,} tokens) — "
            "summarise or prune old entries before it crowds out soul/user/config"
        )
    elif state_chars >= _STATE_WARN_CHARS:
        growth_status = "warn"
        has_warning = True
        growth_note = (
            f"session_state is {state_chars:,} chars (~{state_token_est:,} tokens) — "
            "growing; consider condensing older entries"
        )
    else:
        growth_status = "pass"
        growth_note = f"{state_chars:,} chars (~{state_token_est:,} tokens) — within healthy range"
    checks["session_state_growth"] = {
        "status": growth_status,
        "chars": state_chars,
        "tokens_estimate": state_token_est,
        "warn_threshold_chars": _STATE_WARN_CHARS,
        "critical_threshold_chars": _STATE_CRITICAL_CHARS,
        "note": growth_note,
    }

    # ── 9. HFS registry ───────────────────────────────────────────────────────
    identity_ids = {
        k: v
        for k, v in session.full_section_ids.items()
        if k in _EXPECTED_SECTIONS and isinstance(v, str)
    }
    registered = sorted(identity_ids.keys())
    unregistered = sorted(name for name in session.sections_loaded if name not in identity_ids)
    hfs_status = "warn" if unregistered else "pass"
    if unregistered:
        has_warning = True
    checks["hfs_registry"] = {
        "status": hfs_status,
        "registered_sections": registered,
        "unregistered_sections": unregistered,
        "index_file_id": session.index_file_id,
    }

    # ── Overall status ────────────────────────────────────────────────────────
    if has_critical:
        overall = "critical"
    elif has_warning:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "session_id": session_id,
        "token_id": session.token_id,
        "overall": overall,
        "sections_loaded": session.sections_loaded,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# POST /vault/health/repair — apply auto-fixable repairs to the active session
# ---------------------------------------------------------------------------


@router.post("/health/repair")
def vault_health_repair(session_id: str) -> dict:
    """
    Apply all auto-fixable repairs to the user's in-memory vault and rebuild
    the RAG index.

    Auto-fixable issues:
      rag_chunk_quality — tiny/oversized chunks: rebuild the index using the
                          improved chunker (merges sub-50-char fragments).
                          No vault content is modified; only the in-memory
                          search index is rebuilt.

    Non-auto-fixable (require user action on vault content):
      completeness      — missing sections must be added manually
      staleness         — session_state must be updated with recent dates
      metadata          — missing fields must be authored
      duplicate_content — duplicate paragraphs must be removed manually
      session_state_growth — old entries must be pruned or summarised

    Returns a summary of what was repaired and the updated health status.
    Requires an active session — all operations are in-memory only.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired.",
        )

    repairs: list[dict] = []

    # ── Repair: rebuild RAG index with improved chunker ───────────────────────
    # Import is done at call time and forced fresh via importlib to bypass any
    # stale module cache that might be holding an older version of the chunker.
    try:
        from rank_bm25 import BM25Okapi
        from api.services.rag import chunk_sections, VaultIndex, _tokenize

        old_count = session.vault_index.chunk_count if session.vault_index else 0

        if session.vault_index is not None:
            session.vault_index.clear()

        chunks = chunk_sections(session.context_sections)
        if chunks:
            corpus = [_tokenize(c.text) for c in chunks]
            session.vault_index = VaultIndex(chunks=chunks, bm25=BM25Okapi(corpus))
        else:
            session.vault_index = VaultIndex(chunks=[], bm25=None)
        new_count = session.vault_index.chunk_count

        new_tiny = (
            sum(1 for c in session.vault_index._chunks if len(c.text) < 50) if new_count > 0 else 0
        )

        if new_count == 0:
            repairs.append(
                {
                    "repair": "rag_index_rebuilt",
                    "status": "failed",
                    "chunks_before": old_count,
                    "chunks_after": 0,
                    "tiny_chunks_remaining": 0,
                    "note": "Rebuild returned empty index — vault sections may lack parseable structure",
                }
            )
        else:
            repairs.append(
                {
                    "repair": "rag_index_rebuilt",
                    "status": "fixed" if new_tiny == 0 else "improved",
                    "chunks_before": old_count,
                    "chunks_after": new_count,
                    "tiny_chunks_remaining": new_tiny,
                    "note": (
                        f"RAG index rebuilt — {new_count} chunks indexed"
                        if new_tiny == 0
                        else f"RAG index rebuilt — {new_count} chunks, {new_tiny} tiny chunk(s) remain"
                    ),
                }
            )
    except Exception as exc:
        import traceback

        repairs.append(
            {
                "repair": "rag_index_rebuilt",
                "status": "failed",
                "note": f"{type(exc).__name__}: {exc} | {traceback.format_exc().splitlines()[-2]}",
            }
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    fixed = [r for r in repairs if r["status"] == "fixed"]
    improved = [r for r in repairs if r["status"] == "improved"]
    failed = [r for r in repairs if r["status"] == "failed"]

    return {
        "session_id": session_id,
        "repairs_applied": len(repairs),
        "fixed": len(fixed),
        "improved": len(improved),
        "failed": len(failed),
        "repairs": repairs,
        "note": (
            "Run GET /vault/health to see the updated status. "
            "Some issues (staleness, duplicate content, missing metadata) "
            "require manual updates to your vault content."
        ),
    }


# ---------------------------------------------------------------------------
# System section content — shared with provisioning (user.py)
# ---------------------------------------------------------------------------


def _system_section_content(token_id: str, created_at: str) -> bytes:
    """
    Generate the system capabilities section for a vault.

    Describes the vault architecture, RAG index, MCP server, skill packages,
    and health check tools so the AI companion understands what it has access to.
    Injected as part of the system prompt at every session open.
    """
    return f"""# System Capabilities

**Token:** {token_id}
**Initialized:** {created_at}

This companion runs within the Arty Fitchels sovereign AI context system.
Context is stored encrypted on Hedera Hashgraph — only your wallet signature can decrypt it.
Nothing unencrypted ever touches a server at rest or in transit beyond your active session.

## Vault Sections
Five sections are loaded into every session:
- **soul** — your AI's core directives, mission, and operating principles
- **user** — your profile, preferences, background, and goals
- **config** — AI name, tone, style, and response configuration
- **session_state** — auto-updated after every session to carry forward what was worked on
- **system** — this section (platform capabilities — reference only)

Each section is stored as AES-GCM ciphertext on Hedera File Service (HFS).
Keys are derived fresh from your wallet signature on every session open using HKDF-SHA256, then zeroed on close.
The vault index (section → HFS file_id mapping) is also encrypted on HFS and resolved via the ContextValidator contract.

## Context Retrieval (RAG)
Vault content is indexed with BM25 at session open.
Relevant context chunks are retrieved automatically on each conversation turn and injected
alongside your message — you do not need to supply background manually.
The index is rebuilt in-memory on every session open from the decrypted vault sections.
Check retrieval quality: GET /vault/health → rag_index check

## Skill Packages
Skill packages are MCP tool definitions stored encrypted in your vault.
When the AI learns a reusable task, it can be packaged as a skill and stored permanently.
Skills load automatically at session open and become available as callable tools in any future
session with any AI model — no re-teaching required.
Manage skills: GET /skills | POST /skills | DELETE /skills/{{skill_id}}
Skills as MCP tools: GET /skills/tools

## MCP Server
Your vault exposes a Model Context Protocol server that any MCP-compatible AI client can connect to.

Static tools available in every session:
- open_session — decrypt vault from Hedera, return session_id
- close_session — sync changed sections to Hedera, zero session keys
- get_vault_section — read any vault section by name
- update_vault_section — queue a section update to be synced at close
- list_skills — list all skill packages in this vault
- save_skill_to_vault — package a learned task as a permanent vault skill

Dynamic tools: each skill package stored in your vault is registered as a live MCP tool at session open.
Run the MCP server: python -m api.mcp_server --transport stdio

## Vault Health and Auto-Repair
Check your vault state against your live decrypted content at any time (requires active session):
- GET /vault/health?session_id=<id> — completeness, RAG quality, staleness, structure, HFS registry, duplicates
- POST /vault/health/repair?session_id=<id> — rebuilds RAG index, applies all auto-fixes
- POST /vault/upgrade?session_id=<id> — adds missing system capabilities section (this file)

Health report: overall status (healthy / degraded / critical) with per-check breakdowns and actionable notes.

## Session Lifecycle
Sessions are valid for 4 hours. Concurrent sessions for the same token are blocked (409 Conflict) to
prevent key collision. At close, changed sections are diffed against session-open hashes — only
changed content is re-encrypted and pushed to Hedera. If a chat happened and session_state was not
manually updated, a brief summary is auto-generated and written back to the vault.
""".encode(
        "utf-8"
    )


# ---------------------------------------------------------------------------
# POST /vault/upgrade — add system section to vaults provisioned before it existed
# ---------------------------------------------------------------------------


@router.post("/upgrade")
def vault_upgrade(session_id: str) -> dict:
    """
    Add the system capabilities section to a vault that was provisioned before
    system directives were introduced.

    - Safe to call multiple times — returns immediately if the section already exists.
    - Pushes the system section to Hedera HFS using the active session's derived key.
    - Updates the encrypted vault index on HFS to include the new section file_id.
    - Injects the section into the current session context so it is available immediately.
    - At session close, the updated index is written back as normal.

    Requires an active session — the session key is used to encrypt the new section.
    """
    import hashlib as _hashlib
    from datetime import datetime, timezone as _tz

    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or expired.",
        )

    # Already upgraded — nothing to do.
    if "system" in session.full_section_ids and isinstance(
        session.full_section_ids.get("system"), str
    ):
        return {
            "status": "already_present",
            "section": "system",
            "file_id": session.full_section_ids["system"],
            "message": "System capabilities section already exists in this vault.",
        }

    token_id = session.token_id
    created_at = datetime.now(_tz.utc).isoformat()
    content = _system_section_content(token_id, created_at)
    content_hash = _hashlib.sha256(content).hexdigest()

    # Take local copies of the keys (zeroed in the finally block).
    section_key = bytes(session.section_key)
    index_key = bytes(session.index_key)

    try:
        # ── Push new system section to HFS ────────────────────────────────────
        file_id = _push_section(
            section_name="system",
            content=content,
            key=section_key,
            token_id=token_id,
            existing_file_id=None,
        )

        # ── Rebuild vault index with the new section ──────────────────────────
        _META_KEYS = {"_section_hashes"}
        clean_index = {
            k: v
            for k, v in session.full_section_ids.items()
            if k not in _META_KEYS and isinstance(v, str)
        }
        clean_index["system"] = file_id

        new_hashes = dict(session.start_hashes)
        new_hashes["system"] = content_hash

        _update_index(
            index_file_id=session.index_file_id,
            index=clean_index,
            key=index_key,
            token_id=token_id,
            section_hashes=new_hashes,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to push system section to Hedera: {exc}",
        )
    finally:
        section_key = b"\x00" * len(section_key)
        index_key = b"\x00" * len(index_key)

    # ── Update in-memory session so this section is available immediately ─────
    session.full_section_ids["system"] = file_id
    session.start_hashes["system"] = content_hash
    session.context_sections["system"] = content.decode("utf-8")
    if "system" not in session.sections_loaded:
        session.sections_loaded.append("system")

    # ── Log to HCS ────────────────────────────────────────────────────────────
    try:
        log_event(
            event_type="VAULT_UPGRADED",
            payload={
                "token_id": token_id,
                "section": "system",
                "file_id": file_id,
                "session_id": session_id,
            },
        )
    except Exception:
        pass  # Non-fatal

    return {
        "status": "upgraded",
        "section": "system",
        "file_id": file_id,
        "message": (
            "System capabilities section added to vault and vault index updated on Hedera. "
            "The section is available in the current session immediately."
        ),
    }
