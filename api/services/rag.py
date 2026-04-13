"""
api/services/rag.py — In-memory vault RAG engine.

Chunks the decrypted vault content at session open, builds a BM25 index,
and retrieves only the relevant chunks to inject into each chat turn's
system prompt.

This replaces full-section injection with relevance-gated loading — matching
P2 Provisional Claim 9 (relevance-gated memory loading): the vault may
contain more context than any model's context window; only what is relevant
to the current query enters.

Session lifecycle:
  - Built at session open from decrypted vault content (in-memory only)
  - Queried on every chat turn (sub-millisecond for typical vault sizes)
  - Destroyed at session close alongside crypto keys and decrypted content

No ML models. No disk writes. No API calls.
Uses BM25Okapi from rank-bm25 (pure Python, zero native deps).
"""

import re
from dataclasses import dataclass
from typing import Optional

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi

    _BM25_AVAILABLE = True
except ImportError:
    _BM25Okapi = None  # type: ignore[assignment]
    _BM25_AVAILABLE = False

# Maximum characters per chunk before splitting at paragraph boundaries.
# Must match _CHUNK_MAX_CHARS in vault.py health check — keep in sync.
_MAX_CHUNK_CHARS = 1200

# Sections always injected in full — never chunked or filtered by RAG.
# Harness is the AI's identity and directives: it must always be complete.
_ALWAYS_FULL_SECTIONS = {"harness"}

# Minimum BM25 score to include a chunk (0.0 = include any non-zero match)
_MIN_SCORE = 0.0


@dataclass
class VaultChunk:
    """A single chunk of decrypted vault content with provenance metadata."""

    section: str  # e.g. "user", "config", "session_state"
    header: str  # markdown header this chunk falls under (or section name if none)
    text: str  # chunk plaintext


class VaultIndex:
    """
    In-memory BM25 index over chunked vault content.

    Scoped to one session — built at open, destroyed at close.
    chunk_count == 0 means RAG is unavailable; callers should fall back
    to full-section injection.
    """

    def __init__(self, chunks: list[VaultChunk], bm25: Optional[object]):
        self._chunks = chunks
        self._bm25 = bm25

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def query(self, query: str, top_k: int = 8, min_score: float = _MIN_SCORE) -> list[VaultChunk]:
        """
        Return up to top_k chunks most relevant to the query.

        Returns an empty list if the index is empty or rank-bm25 is not installed.
        Callers should fall back to full-section injection on empty results.
        """
        if not self._bm25 or not self._chunks:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in ranked[:top_k] if scores[i] > min_score]

    def clear(self) -> None:
        """Destroy index content — called at session close alongside key zeroing."""
        self._chunks.clear()
        self._bm25 = None


def chunk_sections(context_sections: dict[str, str]) -> list[VaultChunk]:
    """
    Chunk all indexable vault sections and return the flat list of VaultChunks.

    Separated from BM25 construction so callers can import BM25Okapi themselves
    and pass it in — avoids rank_bm25 import issues at module init time.

    Harness is excluded — always injected in full.
    """
    all_chunks: list[VaultChunk] = []
    for section_name, content in context_sections.items():
        if section_name in _ALWAYS_FULL_SECTIONS:
            continue
        if not content or not content.strip():
            continue
        all_chunks.extend(_chunk_section(section_name, content))
    return all_chunks


def build_vault_index(context_sections: dict[str, str]) -> "VaultIndex":
    """
    Chunk vault sections and build an in-memory BM25 index.

    Falls back to an empty VaultIndex if rank-bm25 is not importable.
    Callers that need a guaranteed index should use chunk_sections() directly
    and construct VaultIndex themselves after importing BM25Okapi.
    """
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return VaultIndex(chunks=[], bm25=None)

    chunks = chunk_sections(context_sections)
    if not chunks:
        return VaultIndex(chunks=[], bm25=None)
    corpus = [_tokenize(c.text) for c in chunks]
    return VaultIndex(chunks=chunks, bm25=BM25Okapi(corpus))


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer — strips punctuation, keeps alphanumerics."""
    return re.findall(r"\b\w+\b", text.lower())


def _chunk_section(section_name: str, content: str) -> list[VaultChunk]:
    """
    Split a markdown section into chunks by headers.

    Strategy:
    1. Split on markdown headers (## through ####)
    2. Keep each header + its body as one logical chunk
    3. If a chunk exceeds _MAX_CHUNK_CHARS, split further at paragraph boundaries
    """
    chunks: list[VaultChunk] = []

    # Split on header lines, keeping headers in the result list
    parts = re.split(r"^(#{1,4}\s+.+)$", content, flags=re.MULTILINE)

    current_header = section_name
    current_body: list[str] = []

    for part in parts:
        part_stripped = part.strip()
        if not part_stripped:
            continue
        if re.match(r"^#{1,4}\s+", part_stripped):
            # Flush the current chunk before starting a new header block
            if current_body:
                body = "\n\n".join(current_body).strip()
                if body:
                    chunks.extend(_split_by_paragraphs(section_name, current_header, body))
            current_header = _strip_header_markers(part_stripped)
            current_body = []
        else:
            current_body.append(part_stripped)

    # Flush the final chunk
    if current_body:
        body = "\n\n".join(current_body).strip()
        if body:
            chunks.extend(_split_by_paragraphs(section_name, current_header, body))

    # Post-process: merge any tiny chunks into their nearest neighbor.
    # A chunk under _MIN_CHUNK_CHARS carries no useful retrieval signal and
    # pollutes BM25 scoring. Merge forward; if last chunk, merge backward.
    _MIN_CHUNK_CHARS = 50
    merged: list[VaultChunk] = []
    for chunk in chunks:
        if len(chunk.text) < _MIN_CHUNK_CHARS and merged:
            # Append tiny chunk's text to the previous chunk
            prev = merged[-1]
            merged[-1] = VaultChunk(
                section=prev.section,
                header=prev.header,
                text=prev.text + "\n\n" + chunk.text,
            )
        else:
            merged.append(chunk)

    # If the very first chunk is tiny and there's a second chunk, merge forward
    if len(merged) >= 2 and len(merged[0].text) < _MIN_CHUNK_CHARS:
        second = merged[1]
        merged[1] = VaultChunk(
            section=second.section,
            header=second.header,
            text=merged[0].text + "\n\n" + second.text,
        )
        merged = merged[1:]

    return merged


def _strip_header_markers(header_line: str) -> str:
    """'## My Section' → 'My Section'"""
    return re.sub(r"^#+\s+", "", header_line).strip()


def _hard_split(section: str, header: str, text: str) -> list[VaultChunk]:
    """
    Last-resort splitter for paragraphs that are themselves longer than
    _MAX_CHUNK_CHARS with no blank-line breaks to split on.

    Splits at the nearest sentence boundary ('. ', '! ', '? ') before the
    limit. Falls back to a hard cut at exactly _MAX_CHUNK_CHARS if no
    sentence boundary exists in the window.
    """
    chunks: list[VaultChunk] = []
    remaining = text
    while len(remaining) > _MAX_CHUNK_CHARS:
        window = remaining[:_MAX_CHUNK_CHARS]
        # Find the last sentence boundary in the window
        cut = -1
        for sep in (". ", "! ", "? "):
            idx = window.rfind(sep)
            if idx > cut:
                cut = idx + len(sep) - 1  # keep the punctuation, cut before the space
        if cut > 0:
            chunk_text = remaining[:cut].strip()
            remaining = remaining[cut:].strip()
        else:
            # No sentence boundary — hard cut
            chunk_text = remaining[:_MAX_CHUNK_CHARS].strip()
            remaining = remaining[_MAX_CHUNK_CHARS:].strip()
        if chunk_text:
            chunks.append(VaultChunk(section=section, header=header, text=chunk_text))
    if remaining:
        chunks.append(VaultChunk(section=section, header=header, text=remaining))
    return chunks


def _split_by_paragraphs(section: str, header: str, text: str) -> list[VaultChunk]:
    """
    If text fits within _MAX_CHUNK_CHARS, return it as one chunk.
    Otherwise split at blank-line paragraph boundaries.
    If a single paragraph is still over the limit, _hard_split() handles it.
    """
    if len(text) <= _MAX_CHUNK_CHARS:
        return [VaultChunk(section=section, header=header, text=text)]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[VaultChunk] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len + 2 > _MAX_CHUNK_CHARS:
            chunks.append(
                VaultChunk(
                    section=section,
                    header=header,
                    text="\n\n".join(current),
                )
            )
            current = []
            current_len = 0
        # If a single paragraph is itself over the limit, hard-split it immediately
        if para_len > _MAX_CHUNK_CHARS:
            if current:
                chunks.append(
                    VaultChunk(
                        section=section,
                        header=header,
                        text="\n\n".join(current),
                    )
                )
                current = []
                current_len = 0
            chunks.extend(_hard_split(section, header, para))
        else:
            current.append(para)
            current_len += para_len + 2

    if current:
        remainder = "\n\n".join(current)
        if chunks and len(remainder) < 50:
            # Tiny remainder — absorb into the last chunk rather than creating noise
            chunks[-1] = VaultChunk(
                section=chunks[-1].section,
                header=chunks[-1].header,
                text=chunks[-1].text + "\n\n" + remainder,
            )
        else:
            chunks.append(
                VaultChunk(
                    section=section,
                    header=header,
                    text=remainder,
                )
            )

    return chunks
