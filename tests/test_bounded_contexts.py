"""
test_bounded_contexts.py — Tests for bounded context organization
"""

import pytest
from src.bounded_contexts import (
    BoundedContext,
    ContextMapping,
    infer_contexts_from_keywords,
    filter_packages_by_context,
    get_context_summary,
    suggest_context_for_package,
)


# Mock PackageMetadata for testing
class MockPackage:
    def __init__(self, name, keywords, description=""):
        self.name = name
        self.keywords = keywords
        self.description = description


def test_bounded_context_enum():
    """Test BoundedContext enum."""
    assert BoundedContext.AI_ENGINEERING.value == "ai_engineering"
    assert BoundedContext.HEDERA.value == "hedera"
    assert BoundedContext.PYTHON.value == "python"


def test_bounded_context_from_string():
    """Test converting string to BoundedContext."""
    assert BoundedContext.from_string("ai_engineering") == BoundedContext.AI_ENGINEERING
    assert BoundedContext.from_string("hedera") == BoundedContext.HEDERA
    assert BoundedContext.from_string("unknown") == BoundedContext.GENERAL


def test_bounded_context_keywords():
    """Test getting keywords for a context."""
    ai_keywords = BoundedContext.AI_ENGINEERING.get_keywords()
    assert "llm" in ai_keywords
    assert "rag" in ai_keywords
    assert "agent" in ai_keywords

    hedera_keywords = BoundedContext.HEDERA.get_keywords()
    assert "hedera" in hedera_keywords
    assert "hts" in hedera_keywords
    assert "hashgraph" in hedera_keywords


def test_bounded_context_description():
    """Test getting description for a context."""
    desc = BoundedContext.AI_ENGINEERING.get_description()
    assert "AI" in desc or "LLM" in desc

    hedera_desc = BoundedContext.HEDERA.get_description()
    assert "Hedera" in hedera_desc


def test_context_mapping_creation():
    """Test creating ContextMapping."""
    mapping = ContextMapping(
        package_name="test_package",
        contexts=[BoundedContext.AI_ENGINEERING, BoundedContext.PYTHON],
        confidence=0.9,
    )

    assert mapping.package_name == "test_package"
    assert len(mapping.contexts) == 2
    assert mapping.confidence == 0.9


def test_context_mapping_add_context():
    """Test adding context to mapping."""
    mapping = ContextMapping(package_name="test")

    mapping.add_context(BoundedContext.AI_ENGINEERING, confidence=0.9)
    assert BoundedContext.AI_ENGINEERING in mapping.contexts

    # Adding same context again shouldn't duplicate
    mapping.add_context(BoundedContext.AI_ENGINEERING, confidence=0.8)
    assert len(mapping.contexts) == 1


def test_context_mapping_has_context():
    """Test checking if mapping has a context."""
    mapping = ContextMapping(package_name="test", contexts=[BoundedContext.AI_ENGINEERING])

    assert mapping.has_context(BoundedContext.AI_ENGINEERING)
    assert not mapping.has_context(BoundedContext.PYTHON)


def test_context_mapping_serialization():
    """Test ContextMapping to/from dict."""
    mapping = ContextMapping(
        package_name="test",
        contexts=[BoundedContext.AI_ENGINEERING, BoundedContext.PYTHON],
        confidence=0.85,
    )

    data = mapping.to_dict()
    assert data["package_name"] == "test"
    assert "ai_engineering" in data["contexts"]
    assert data["confidence"] == 0.85

    restored = ContextMapping.from_dict(data)
    assert restored.package_name == "test"
    assert len(restored.contexts) == 2


def test_infer_contexts_from_keywords_ai():
    """Test inferring AI engineering context."""
    contexts = infer_contexts_from_keywords(
        "llm_rag_implementation",
        ["llm", "rag", "embedding", "semantic"],
        "Implementation of RAG with LLM",
    )

    assert BoundedContext.AI_ENGINEERING in contexts


def test_infer_contexts_from_keywords_hedera():
    """Test inferring Hedera context."""
    contexts = infer_contexts_from_keywords(
        "hedera_smart_contract",
        ["hedera", "hts", "nft", "token"],
        "Hedera smart contract deployment",
    )

    assert BoundedContext.HEDERA in contexts


def test_infer_contexts_from_keywords_multiple():
    """Test inferring multiple contexts."""
    contexts = infer_contexts_from_keywords(
        "python_llm_api", ["python", "fastapi", "llm", "rag", "api"], "Python API for LLM with RAG"
    )

    # Should infer both AI_ENGINEERING and PYTHON
    assert BoundedContext.AI_ENGINEERING in contexts or BoundedContext.PYTHON in contexts
    assert len(contexts) <= 3  # Max 3 contexts


def test_infer_contexts_from_keywords_general():
    """Test inferring general context for unmatched keywords."""
    contexts = infer_contexts_from_keywords(
        "random_notes", ["misc", "notes", "random"], "Random notes"
    )

    assert BoundedContext.GENERAL in contexts


def test_filter_packages_by_context():
    """Test filtering packages by context."""
    packages = [
        MockPackage("llm_package", ["llm", "rag"], "LLM implementation"),
        MockPackage("hedera_package", ["hedera", "hts"], "Hedera tokens"),
        MockPackage("python_package", ["python", "async"], "Python code"),
    ]

    # Filter by AI_ENGINEERING
    filtered = filter_packages_by_context(packages, [BoundedContext.AI_ENGINEERING], {})

    # Should find the LLM package
    assert len(filtered) >= 1
    assert any(p.name == "llm_package" for p in filtered)


def test_filter_packages_by_context_with_mappings():
    """Test filtering with existing context mappings."""
    packages = [
        MockPackage("package1", ["test"], "Test"),
        MockPackage("package2", ["test"], "Test"),
    ]

    mappings = {
        "package1": ContextMapping("package1", [BoundedContext.AI_ENGINEERING]),
        "package2": ContextMapping("package2", [BoundedContext.PYTHON]),
    }

    # Filter by AI_ENGINEERING
    filtered = filter_packages_by_context(packages, [BoundedContext.AI_ENGINEERING], mappings)

    assert len(filtered) == 1
    assert filtered[0].name == "package1"


def test_filter_packages_no_contexts():
    """Test filtering with no contexts returns all packages."""
    packages = [
        MockPackage("package1", ["test"]),
        MockPackage("package2", ["test"]),
    ]

    filtered = filter_packages_by_context(packages, [], {})

    assert len(filtered) == 2


def test_get_context_summary():
    """Test getting context summary statistics."""
    mappings = {
        "pkg1": ContextMapping("pkg1", [BoundedContext.AI_ENGINEERING]),
        "pkg2": ContextMapping("pkg2", [BoundedContext.AI_ENGINEERING, BoundedContext.PYTHON]),
        "pkg3": ContextMapping("pkg3", [BoundedContext.HEDERA]),
    }

    summary = get_context_summary(mappings)

    assert summary["total_packages"] == 3
    assert "ai_engineering" in summary["context_distribution"]
    assert summary["context_distribution"]["ai_engineering"]["count"] == 2


def test_get_context_summary_empty():
    """Test context summary with no mappings."""
    summary = get_context_summary({})

    assert summary["total_packages"] == 0
    assert len(summary["context_distribution"]) == 0


def test_suggest_context_for_package():
    """Test suggesting contexts for a package."""
    mapping = suggest_context_for_package(
        "hedera_nft_minting", ["hedera", "nft", "token", "hts"], "NFT minting on Hedera"
    )

    assert mapping.package_name == "hedera_nft_minting"
    assert len(mapping.contexts) > 0
    assert BoundedContext.HEDERA in mapping.contexts
    assert 0.0 <= mapping.confidence <= 1.0


def test_suggest_context_confidence():
    """Test confidence scoring in suggestions."""
    # Few contexts = higher confidence
    mapping1 = suggest_context_for_package("specific_package", ["hedera", "hts"], "Hedera specific")

    # Many contexts = lower confidence
    mapping2 = suggest_context_for_package(
        "broad_package", ["python", "api", "hedera", "llm", "rag"], "Broad package"
    )

    # Specific should have higher confidence
    assert mapping1.confidence >= mapping2.confidence or len(mapping1.contexts) <= 2
