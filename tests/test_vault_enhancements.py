"""
test_vault_enhancements.py — Tests for vault enhancement features
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from src.vault_enhancements import (
    analyze_content_keywords,
    suggest_tags,
    generate_metadata_from_content,
    detect_cross_references,
    add_cross_reference_links,
    enhance_vault_file,
    batch_enhance_vault,
)


def test_analyze_content_keywords():
    """Test keyword extraction from content."""
    content = """
    # Hedera Smart Contracts
    
    This document covers Hedera smart contract deployment using Solidity.
    Smart contracts on Hedera provide decentralized execution.
    """
    
    keywords = analyze_content_keywords(content, top_n=5)
    
    assert "hedera" in keywords
    assert "smart" in keywords or "contract" in keywords
    assert len(keywords) <= 5


def test_suggest_tags():
    """Test tag suggestion from content."""
    content = """
    # React Frontend Development
    
    Building a React application with TypeScript and TailwindCSS.
    This is an active project for UI development.
    """
    
    tags = suggest_tags(content)
    
    # Should suggest type/project, domain/frontend, status/active
    assert any("#type/project" in tag for tag in tags)
    assert any("#domain/frontend" in tag for tag in tags)
    assert any("react" in tag.lower() for tag in tags)


def test_suggest_tags_preserves_existing():
    """Test that existing tags are preserved."""
    content = "Some content"
    existing = ["#custom/tag", "#type/identity"]
    
    tags = suggest_tags(content, existing_tags=existing)
    
    assert "#custom/tag" in tags
    assert "#type/identity" in tags


def test_generate_metadata_from_content():
    """Test automated metadata generation."""
    content = """
    # AI Research Project
    
    Research on large language models and prompt engineering.
    Active development with Claude and GPT-4.
    """
    
    metadata = generate_metadata_from_content(content, status="active")
    
    assert metadata.status == "active"
    assert len(metadata.tags) > 0
    assert metadata.created == datetime.now().date().isoformat()
    assert any("ai" in tag.lower() for tag in metadata.tags)


def test_detect_cross_references_wiki_links():
    """Test detection of wiki-style cross-references."""
    content = """
    See [[Hedera Basics]] for more information.
    Also check [[Smart Contracts]] documentation.
    """
    
    sections = ["Hedera Basics", "Smart Contracts", "Other Section"]
    refs = detect_cross_references(content, sections)
    
    assert "Hedera Basics" in refs
    assert "Smart Contracts" in refs


def test_detect_cross_references_markdown_links():
    """Test detection of markdown link cross-references."""
    content = """
    Read more in [this section](Project Overview).
    External link: [Google](https://google.com)
    """
    
    sections = ["Project Overview", "Other Section"]
    refs = detect_cross_references(content, sections)
    
    assert "Project Overview" in refs
    # Should not include external URLs
    assert "https://google.com" not in refs


def test_detect_cross_references_direct_mentions():
    """Test detection of direct section name mentions."""
    content = """
    The Development Process section covers this in detail.
    See also the Security Audit documentation.
    """
    
    sections = ["Development Process", "Security Audit", "Random"]
    refs = detect_cross_references(content, sections)
    
    assert "Development Process" in refs
    assert "Security Audit" in refs


def test_add_cross_reference_links():
    """Test adding cross-reference section."""
    content = "# Original Content\n\nSome text."
    references = ["Section A", "Section B"]
    
    enhanced = add_cross_reference_links(content, references)
    
    assert "## Related Sections" in enhanced
    assert "[[Section A]]" in enhanced
    assert "[[Section B]]" in enhanced


def test_add_cross_reference_links_no_duplicates():
    """Test that cross-reference section isn't duplicated."""
    content = "# Content\n\n## Related Sections\n- Existing"
    references = ["New Section"]
    
    enhanced = add_cross_reference_links(content, references)
    
    # Should not add duplicate section
    assert enhanced == content


def test_enhance_vault_file():
    """Test full file enhancement."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"
        content = """# Test Section

This is about Hedera development and smart contracts.
See also Project Overview for context.
"""
        file_path.write_text(content, encoding='utf-8')
        
        sections = ["Test Section", "Project Overview", "Other"]
        enhanced, info = enhance_vault_file(
            file_path,
            sections,
            add_xrefs=True,
            update_metadata=True
        )
        
        assert info["metadata_generated"]
        assert "Project Overview" in info["references"]
        assert "---" in enhanced  # Has frontmatter
        assert "## Related Sections" in enhanced


def test_enhance_vault_file_preserves_existing_metadata():
    """Test that existing metadata is updated, not replaced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"
        content = """---
tags: ["#custom/tag"]
created: "2026-01-01"
last_updated: "2026-01-01"
last_reviewed: "2026-01-01"
status: "active"
version: "1.0"
---
# Test

Content about React development.
"""
        file_path.write_text(content, encoding='utf-8')
        
        sections = ["Test"]
        enhanced, info = enhance_vault_file(
            file_path,
            sections,
            update_metadata=True
        )
        
        # Should preserve custom tag and add new ones
        assert "#custom/tag" in enhanced
        # Should have added React-related tags
        assert "react" in enhanced.lower()


def test_batch_enhance_vault():
    """Test batch enhancement of multiple files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        
        # Create test files
        (vault_path / "file1.md").write_text("# File 1\nContent", encoding='utf-8')
        (vault_path / "file2.md").write_text("# File 2\nSee File 1", encoding='utf-8')
        
        summary = batch_enhance_vault(
            vault_path,
            dry_run=False,
            add_xrefs=True,
            update_metadata=True
        )
        
        assert summary["total_files"] == 2
        assert summary["enhanced"] >= 1
        assert summary["metadata_generated"] >= 1


def test_batch_enhance_vault_dry_run():
    """Test dry run doesn't modify files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        file_path = vault_path / "test.md"
        original = "# Test\nContent"
        file_path.write_text(original, encoding='utf-8')
        
        summary = batch_enhance_vault(
            vault_path,
            dry_run=True,
            update_metadata=True
        )
        
        # File should not be modified
        assert file_path.read_text(encoding='utf-8') == original
        assert summary["total_files"] == 1
