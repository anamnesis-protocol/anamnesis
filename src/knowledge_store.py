"""
src/knowledge_store.py — Context Import: user-managed knowledge section.

Stores user-imported markdown files as the 'knowledge' vault section.
Uses the same HKDF key + push_section/update_index primitives as identity sections,
so it is loaded at session open and RAG-indexed automatically.

Section format (markdown with file markers):
  <!-- knowledge-file: filename.md -->
  # filename.md

  file content here...

  <!-- /knowledge-file -->

  <!-- knowledge-file: notes.txt -->
  ...

File markers allow per-file add/remove without breaking RAG chunking.
"""

import hashlib
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vault import push_section, update_index

if TYPE_CHECKING:
    from api.session_store import Session

_SECTION_NAME = "knowledge"
_META_KEYS = {"_section_hashes"}

# Matches <!-- knowledge-file: some-name.md -->
_FILE_START_RE = re.compile(r"<!-- knowledge-file: (.+?) -->")
_FILE_END = "<!-- /knowledge-file -->"

# Limits
MAX_FILE_BYTES = 200 * 1024  # 200 KB per file
MAX_TOTAL_BYTES = 2 * 1024 * 1024  # 2 MB total knowledge section
MAX_FILES = 100


# ---------------------------------------------------------------------------
# Parsing / serialisation
# ---------------------------------------------------------------------------


def parse_files(content: str) -> dict[str, str]:
    """
    Extract file name → content dict from knowledge section markdown.
    Returns an empty dict for empty/missing content.

    build_content() adds a `# {name}` header after the file marker.
    parse_files() strips that generated header so the stored original
    content round-trips cleanly.
    """
    files: dict[str, str] = {}
    if not content or not content.strip():
        return files

    parts = _FILE_START_RE.split(content)
    # After split: [text_before, name1, body1, name2, body2, ...]
    i = 1
    while i < len(parts) - 1:
        name = parts[i].strip()
        body = parts[i + 1]
        end = body.find(_FILE_END)
        if end >= 0:
            body = body[:end]
        body = body.strip()
        # Strip the generated `# {name}` header line if present
        generated_header = f"# {name}"
        if body.startswith(generated_header):
            body = body[len(generated_header) :].lstrip("\n")
        files[name] = body
        i += 2

    return files


def build_content(files: dict[str, str]) -> str:
    """Build knowledge section markdown from filename → content dict."""
    if not files:
        return ""
    parts = []
    for name, content in files.items():
        parts.append(
            f"<!-- knowledge-file: {name} -->\n"
            f"# {name}\n\n"
            f"{content.strip()}\n\n"
            f"<!-- /knowledge-file -->"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Session-scoped read / write
# ---------------------------------------------------------------------------


def read_files(session: "Session") -> dict[str, str]:
    """
    Return the current knowledge files from the session context.
    Empty dict if the knowledge section is absent.
    """
    content = session.context_sections.get(_SECTION_NAME, "").strip()
    return parse_files(content)


def write_files(session: "Session", files: dict[str, str]) -> None:
    """
    Persist files to the knowledge section on HFS and update the vault index.

    Also updates session.context_sections["knowledge"] in-memory so
    subsequent requests see the change immediately without reopening.

    After writing, the session's RAG vault_index is rebuilt so imports
    are immediately searchable in chat.
    """
    content = build_content(files)
    section_key_bytes = bytes(session.section_key)
    index_key_bytes = bytes(session.index_key)
    token_id = session.token_id

    try:
        existing_file_id = session.full_section_ids.get(_SECTION_NAME)
        # push_section always returns the file_id — same ID on update, new ID on create
        new_file_id = push_section(
            _SECTION_NAME,
            content.encode("utf-8"),
            section_key_bytes,
            token_id,
            existing_file_id=existing_file_id,
        )
        session.full_section_ids[_SECTION_NAME] = new_file_id

        # Update hashes
        _META_KEYS_LOCAL = {"_section_hashes"}
        clean_index = {
            k: v
            for k, v in session.full_section_ids.items()
            if k not in _META_KEYS_LOCAL and isinstance(v, str)
        }

        stored_hashes = dict(session.start_hashes)
        stored_hashes[_SECTION_NAME] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        update_index(
            index_file_id=session.index_file_id,
            index=clean_index,
            key=index_key_bytes,
            token_id=token_id,
            section_hashes=stored_hashes,
        )

        # Update in-memory context so chat picks up changes immediately
        session.context_sections[_SECTION_NAME] = content

        # Rebuild RAG index
        _rebuild_rag(session)

    finally:
        # Belt-and-suspenders zero of local key copies
        section_key_bytes = b"\x00" * len(section_key_bytes)
        index_key_bytes = b"\x00" * len(index_key_bytes)


def _rebuild_rag(session: "Session") -> None:
    """
    Rebuild the session's in-memory BM25 vault index after a knowledge write.
    Non-fatal — chat falls back to full-section injection if this fails.
    """
    try:
        from rank_bm25 import BM25Okapi
        from api.services.rag import chunk_sections, VaultIndex, _tokenize

        chunks = chunk_sections(session.context_sections)
        if chunks:
            corpus = [_tokenize(c.text) for c in chunks]
            session.vault_index = VaultIndex(chunks=chunks, bm25=BM25Okapi(corpus))
        else:
            session.vault_index = VaultIndex(chunks=[], bm25=None)
    except Exception:
        pass
