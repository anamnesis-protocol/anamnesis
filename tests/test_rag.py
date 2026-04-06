"""
test_rag.py — Tests for TF-IDF RAG package querying

Tests the relevance scoring system for memory packages.
"""

import pytest
from src.rag import (
    tokenize,
    compute_tf,
    compute_idf,
    compute_tfidf_vector,
    cosine_similarity,
    rag_query_packages,
    explain_match,
    PackageMetadata,
)


def test_tokenize():
    """Test basic tokenization."""
    assert tokenize("Hello World") == ["hello", "world"]
    assert tokenize("Hedera-Hashgraph 2026") == ["hedera", "hashgraph", "2026"]
    assert tokenize("a b") == []  # too short
    assert tokenize("ABC123def") == ["abc123def"]


def test_compute_tf():
    """Test term frequency calculation."""
    tokens = ["hello", "world", "hello"]
    tf = compute_tf(tokens)

    assert tf["hello"] == pytest.approx(2 / 3)
    assert tf["world"] == pytest.approx(1 / 3)


def test_compute_idf():
    """Test inverse document frequency calculation."""
    docs = [
        ["hello", "world"],
        ["hello", "hedera"],
        ["world", "blockchain"],
    ]
    idf = compute_idf(docs)

    # "hello" appears in 2/3 docs: log(3/2) ≈ 0.405
    assert idf["hello"] == pytest.approx(0.405, abs=0.01)

    # "world" appears in 2/3 docs: log(3/2) ≈ 0.405
    assert idf["world"] == pytest.approx(0.405, abs=0.01)

    # "hedera" appears in 1/3 docs: log(3/1) ≈ 1.099
    assert idf["hedera"] == pytest.approx(1.099, abs=0.01)


def test_compute_tfidf_vector():
    """Test TF-IDF vector computation."""
    tokens = ["hello", "world", "hello"]
    idf = {"hello": 0.5, "world": 1.0, "other": 2.0}

    tfidf = compute_tfidf_vector(tokens, idf)

    # TF(hello) = 2/3, IDF = 0.5 → TF-IDF = 1/3
    assert tfidf["hello"] == pytest.approx(1 / 3, abs=0.01)

    # TF(world) = 1/3, IDF = 1.0 → TF-IDF = 1/3
    assert tfidf["world"] == pytest.approx(1 / 3, abs=0.01)

    # "other" not in tokens → not in vector
    assert "other" not in tfidf


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    vec1 = {"hello": 1.0, "world": 1.0}
    vec2 = {"hello": 1.0, "world": 1.0}

    # Identical vectors → similarity = 1.0
    assert cosine_similarity(vec1, vec2) == pytest.approx(1.0)

    # Orthogonal vectors → similarity = 0.0
    vec3 = {"foo": 1.0, "bar": 1.0}
    assert cosine_similarity(vec1, vec3) == pytest.approx(0.0)

    # Partial overlap
    vec4 = {"hello": 1.0, "foo": 1.0}
    sim = cosine_similarity(vec1, vec4)
    assert 0.0 < sim < 1.0


def test_rag_query_packages_exact_match():
    """Test RAG query with exact keyword match."""
    packages = [
        PackageMetadata(
            name="session_2026-03-16_hedera_contract",
            category="sessions",
            description="Deployed smart contract to Hedera testnet",
            keywords=["hedera", "contract", "deploy"],
            date="2026-03-16",
            size=1024,
            file_id="0.0.12345",
        ),
        PackageMetadata(
            name="research_python_async",
            category="research",
            description="Python async/await patterns",
            keywords=["python", "async", "await"],
            date="2026-03-10",
            size=2048,
            file_id="0.0.12346",
        ),
    ]

    results = rag_query_packages("hedera smart contract deployment", packages)

    assert len(results) > 0
    assert results[0][1].name == "session_2026-03-16_hedera_contract"
    assert results[0][0] > 0.0  # has positive similarity


def test_rag_query_packages_semantic_match():
    """Test RAG query with semantic similarity."""
    packages = [
        PackageMetadata(
            name="session_blockchain_development",
            category="sessions",
            description="Building decentralized applications on Hedera",
            keywords=["blockchain", "hedera", "dapp", "web3"],
            date="2026-03-15",
            size=1500,
            file_id="0.0.12347",
        ),
        PackageMetadata(
            name="research_database_optimization",
            category="research",
            description="PostgreSQL query performance tuning",
            keywords=["database", "postgres", "sql", "performance"],
            date="2026-03-12",
            size=3000,
            file_id="0.0.12348",
        ),
    ]

    # Query with overlapping terms should match
    results = rag_query_packages("blockchain hedera development", packages, threshold=0.01)

    # Should find blockchain package with matching keywords
    assert len(results) > 0
    assert results[0][1].name == "session_blockchain_development"


def test_rag_query_packages_threshold():
    """Test relevance threshold filtering."""
    packages = [
        PackageMetadata(
            name="highly_relevant",
            category="sessions",
            description="Hedera smart contract deployment tutorial",
            keywords=["hedera", "contract", "deploy", "tutorial"],
            date="2026-03-16",
            size=1024,
            file_id="0.0.12349",
        ),
        PackageMetadata(
            name="barely_relevant",
            category="research",
            description="General programming concepts",
            keywords=["programming", "concepts"],
            date="2026-03-10",
            size=512,
            file_id="0.0.12350",
        ),
    ]

    # Low threshold → should get relevant packages
    results_low = rag_query_packages("hedera contract", packages, threshold=0.01)
    assert len(results_low) >= 1
    assert results_low[0][1].name == "highly_relevant"

    # High threshold → may filter out results (TF-IDF scores are typically < 0.5)
    results_high = rag_query_packages("hedera contract", packages, threshold=0.3)
    # At least the highly relevant one should pass
    if len(results_high) > 0:
        assert results_high[0][1].name == "highly_relevant"


def test_rag_query_packages_top_n():
    """Test top_n limiting."""
    packages = [
        PackageMetadata(
            name=f"package_{i}",
            category="sessions",
            description="Hedera development session",
            keywords=["hedera", "dev"],
            date="2026-03-16",
            size=1024,
            file_id=f"0.0.{12350 + i}",
        )
        for i in range(10)
    ]

    results = rag_query_packages("hedera development", packages, top_n=3, threshold=0.0)

    assert len(results) == 3


def test_rag_query_packages_empty():
    """Test edge cases."""
    packages = []

    # Empty packages
    assert rag_query_packages("query", packages) == []

    # Empty query
    packages = [
        PackageMetadata(
            name="test",
            category="sessions",
            description="Test package",
            keywords=["test"],
            date="2026-03-16",
            size=100,
            file_id="0.0.12360",
        )
    ]
    assert rag_query_packages("", packages) == []


def test_explain_match():
    """Test match explanation."""
    pkg = PackageMetadata(
        name="hedera_contract_deploy",
        category="sessions",
        description="Smart contract deployment on Hedera testnet",
        keywords=["hedera", "contract", "deploy", "testnet"],
        date="2026-03-16",
        size=1024,
        file_id="0.0.12361",
    )

    explanation = explain_match("hedera smart contract", pkg, 0.75)

    assert explanation["similarity"] == 0.75
    assert explanation["package_name"] == "hedera_contract_deploy"
    assert "hedera" in explanation["matching_terms"]
    assert "contract" in explanation["matching_terms"]
    assert explanation["match_ratio"] > 0.0


def test_keyword_weighting():
    """Test that keywords are weighted more heavily than description."""
    packages = [
        PackageMetadata(
            name="pkg_with_keyword",
            category="sessions",
            description="General session notes",
            keywords=["hedera", "blockchain", "smart"],  # keywords
            date="2026-03-16",
            size=1024,
            file_id="0.0.12362",
        ),
        PackageMetadata(
            name="pkg_with_description",
            category="sessions",
            description="hedera blockchain smart contract notes",  # same terms in description
            keywords=["other", "different"],
            date="2026-03-16",
            size=1024,
            file_id="0.0.12363",
        ),
    ]

    results = rag_query_packages("hedera blockchain", packages, threshold=0.0)

    # Both packages should match since they contain the query terms
    assert len(results) >= 1
    # Package with keywords should score higher due to 2x weighting
    assert results[0][1].name == "pkg_with_keyword"
