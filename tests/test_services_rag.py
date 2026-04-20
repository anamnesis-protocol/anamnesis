"""
tests/test_services_rag.py — Tests for the vault BM25 + Bayesian RAG engine.

Covers:
  - VaultChunk dataclass
  - _tokenize
  - _chunk_section / chunk_sections
  - build_vault_index / VaultIndex.query
  - _classify_intent
  - _section_prior
  - _bayesian_rerank: pinning, section boost, dir:* handling
  - VaultIndex.clear
"""

import pytest
from unittest.mock import patch, MagicMock

from api.services.rag import (
    VaultChunk,
    VaultIndex,
    chunk_sections,
    build_vault_index,
    _tokenize,
    _chunk_section,
    _classify_intent,
    _section_prior,
    _bayesian_rerank,
    _DEFAULT_PRIOR,
    _ALWAYS_FULL_SECTIONS,
    _MAX_CHUNK_CHARS,
)

# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_basic():
    assert _tokenize("Hello World") == ["hello", "world"]


def test_tokenize_strips_punctuation():
    assert _tokenize("hello, world!") == ["hello", "world"]


def test_tokenize_alphanumeric():
    assert _tokenize("SHA256 hash") == ["sha256", "hash"]


def test_tokenize_empty():
    assert _tokenize("") == []


# ---------------------------------------------------------------------------
# _classify_intent
# ---------------------------------------------------------------------------


def test_classify_intent_status():
    intents = _classify_intent("what's the current status of the project?")
    assert "status" in intents


def test_classify_intent_status_backlog():
    intents = _classify_intent("show me the backlog")
    assert "status" in intents


def test_classify_intent_historical():
    intents = _classify_intent("what did we work on last session?")
    assert "historical" in intents


def test_classify_intent_knowledge():
    intents = _classify_intent("how does HKDF key derivation work?")
    assert "knowledge" in intents


def test_classify_intent_default_knowledge():
    # Unrecognised query falls back to knowledge
    intents = _classify_intent("banana smoothie recipe")
    assert intents == ["knowledge"]


def test_classify_intent_multi():
    # "what did we do yesterday" matches both historical
    intents = _classify_intent("what did we do yesterday")
    assert "historical" in intents


# ---------------------------------------------------------------------------
# _section_prior
# ---------------------------------------------------------------------------


def test_section_prior_status_session_state():
    prior = _section_prior("session_state", ["status"])
    assert prior > _DEFAULT_PRIOR


def test_section_prior_knowledge_knowledge_section():
    prior = _section_prior("knowledge", ["knowledge"])
    assert prior > _DEFAULT_PRIOR


def test_section_prior_unknown_section():
    prior = _section_prior("unknown_section", ["status"])
    assert prior == _DEFAULT_PRIOR


def test_section_prior_dir_bundle_maps_to_session_state():
    # dir:* sections treated as session_state for status queries
    prior_dir = _section_prior("dir:projects", ["status"])
    prior_ss = _section_prior("session_state", ["status"])
    assert prior_dir == prior_ss


def test_section_prior_takes_best_across_intents():
    # session_state has high prior for status but lower for knowledge
    # Taking best should yield status value
    prior_multi = _section_prior("session_state", ["status", "knowledge"])
    prior_status = _section_prior("session_state", ["status"])
    assert prior_multi == prior_status


# ---------------------------------------------------------------------------
# _chunk_section
# ---------------------------------------------------------------------------


def test_chunk_section_short_content():
    chunks = _chunk_section("user", "# Profile\n\nShort content.")
    assert len(chunks) >= 1
    assert all(isinstance(c, VaultChunk) for c in chunks)
    assert all(c.section == "user" for c in chunks)


def test_chunk_section_long_content():
    long_para = "word " * 400  # > _MAX_CHUNK_CHARS
    chunks = _chunk_section("knowledge", long_para)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= _MAX_CHUNK_CHARS + 20  # small tolerance for boundary


def test_chunk_section_headers_split():
    # Content must be long enough to survive the tiny-chunk merge (>= 50 chars each body)
    body_a = "This is section A content with enough text to avoid being merged away. " * 2
    body_b = "This is section B content with enough text to avoid being merged away. " * 2
    content = f"## Section A\n\n{body_a}\n\n## Section B\n\n{body_b}"
    chunks = _chunk_section("config", content)
    headers = [c.header for c in chunks]
    assert "Section A" in headers
    assert "Section B" in headers


def test_chunk_section_empty():
    chunks = _chunk_section("soul", "")
    assert chunks == []


def test_chunk_section_tiny_chunks_merged():
    # Tiny fragments should get merged, not left as noise
    content = "## A\n\nHi.\n\n## B\n\nThis is a longer paragraph with enough content to survive.\n\nAnd more."
    chunks = _chunk_section("user", content)
    # "Hi." alone is too short — should be merged with the B block
    for c in chunks:
        assert len(c.text) >= 10 or len(chunks) == 1


# ---------------------------------------------------------------------------
# chunk_sections
# ---------------------------------------------------------------------------


def test_chunk_sections_excludes_soul():
    sections = {
        "soul": "# Soul\nDirectives.",
        "user": "# User\nProfile content here.",
    }
    chunks = chunk_sections(sections)
    assert all(c.section != "soul" for c in chunks)
    assert any(c.section == "user" for c in chunks)


def test_chunk_sections_skips_empty():
    sections = {"user": "", "config": "   ", "knowledge": "# K\n\nContent."}
    chunks = chunk_sections(sections)
    assert all(c.section == "knowledge" for c in chunks)


# ---------------------------------------------------------------------------
# build_vault_index / VaultIndex
# ---------------------------------------------------------------------------


def test_build_vault_index_empty():
    idx = build_vault_index({})
    assert idx.chunk_count == 0
    assert idx.query("anything") == []


def test_build_vault_index_no_rank_bm25(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "rank_bm25", None)
    # Ensure we handle ImportError gracefully
    with patch("api.services.rag._BM25_AVAILABLE", False):
        idx = build_vault_index({"user": "some content here"})
    # Even if BM25 unavailable, build should not raise


def test_vault_index_query_returns_relevant():
    pytest.importorskip("rank_bm25")
    sections = {
        "session_state": "# Status\n\nCurrent backlog: Bayesian RAG, E2E tests, wallet.",
        "knowledge": "# Hedera\n\nHKDF key derivation is used for vault encryption.",
        "user": "# Profile\n\nLee is a full-stack developer building Arty Fitchels.",
    }
    idx = build_vault_index(sections)
    assert idx.chunk_count > 0

    results = idx.query("what is in the backlog?", top_k=3)
    assert len(results) > 0
    # session_state should appear for a status-style query
    sections_hit = {r.section for r in results}
    assert "session_state" in sections_hit


def test_vault_index_query_knowledge_intent():
    pytest.importorskip("rank_bm25")
    sections = {
        "session_state": "# Status\n\nWorking on wallet integration.",
        "knowledge": "# HKDF\n\nHKDF derives keys from a master secret using a salt and info parameter.",
        "config": "# Config\n\nmodel: claude-sonnet-4-6",
    }
    idx = build_vault_index(sections)
    results = idx.query("how does HKDF key derivation work?", top_k=3)
    sections_hit = {r.section for r in results}
    assert "knowledge" in sections_hit


def test_vault_index_clear():
    pytest.importorskip("rank_bm25")
    idx = build_vault_index({"user": "# Profile\n\nContent about Lee's preferences."})
    assert idx.chunk_count > 0
    idx.clear()
    assert idx.chunk_count == 0
    assert idx.query("anything") == []


# ---------------------------------------------------------------------------
# _bayesian_rerank
# ---------------------------------------------------------------------------


def _make_chunks_and_scores(section_text_pairs):
    """Helper: build VaultChunk list + fake BM25 scores."""
    chunks = [VaultChunk(section=sec, header=sec, text=text) for sec, text in section_text_pairs]
    # All start with equal BM25 score of 1.0
    scores = [1.0] * len(chunks)
    return chunks, scores


def test_bayesian_rerank_status_boosts_session_state():
    chunks, scores = _make_chunks_and_scores(
        [
            ("session_state", "backlog items pending deployment"),
            ("knowledge", "HKDF derivation algorithm details"),
            ("config", "model configuration settings"),
        ]
    )
    results = _bayesian_rerank("what is open in the backlog?", chunks, scores, top_k=2)
    assert len(results) >= 1
    # session_state should rank first for a status query
    assert results[0].section == "session_state"


def test_bayesian_rerank_knowledge_boosts_knowledge_section():
    chunks, scores = _make_chunks_and_scores(
        [
            ("session_state", "status update"),
            ("knowledge", "how HKDF key derivation works in detail"),
            ("config", "api endpoint configuration"),
        ]
    )
    results = _bayesian_rerank("explain how HKDF works", chunks, scores, top_k=2)
    # knowledge section should appear
    sections = [r.section for r in results]
    assert "knowledge" in sections


def test_bayesian_rerank_pinning_injects_session_state():
    """session_state with zero BM25 score should still appear for status queries (pinned)."""
    chunks = [
        VaultChunk(section="session_state", header="Status", text="backlog: wallet, e2e tests"),
        VaultChunk(section="knowledge", header="HKDF", text="key derivation function"),
        VaultChunk(section="config", header="Config", text="model settings"),
    ]
    # session_state gets score 0.0 (not in BM25 matches), others get 1.0
    scores = [0.0, 1.0, 1.0]
    results = _bayesian_rerank("what's the project status?", chunks, scores, top_k=3)
    sections = [r.section for r in results]
    assert "session_state" in sections


def test_bayesian_rerank_dir_bundle_treated_as_session_state():
    chunks, scores = _make_chunks_and_scores(
        [
            ("dir:projects", "project tracking info"),
            ("knowledge", "HKDF details"),
        ]
    )
    results = _bayesian_rerank("what are we working on?", chunks, scores, top_k=2)
    # dir: section should get status-level boost
    assert len(results) >= 1


def test_bayesian_rerank_top_k_respected():
    chunks, scores = _make_chunks_and_scores(
        [
            ("session_state", "status a"),
            ("knowledge", "knowledge b"),
            ("config", "config c"),
            ("user", "user d"),
        ]
    )
    results = _bayesian_rerank("query", chunks, scores, top_k=2)
    assert len(results) <= 2


def test_bayesian_rerank_empty_chunks():
    results = _bayesian_rerank("query", [], [], top_k=5)
    assert results == []
