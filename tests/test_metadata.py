"""
test_metadata.py — Tests for vault section metadata management
"""

import pytest
from datetime import datetime, timedelta
from src.metadata import (
    SectionMetadata,
    parse_frontmatter,
    add_frontmatter,
    update_frontmatter,
    create_default_metadata,
    get_stale_sections,
    generate_health_report,
)


def test_section_metadata_creation():
    """Test creating metadata."""
    metadata = SectionMetadata(
        tags=["#type/identity", "#status/active"],
        created="2026-03-01",
        last_updated="2026-04-01",
        last_reviewed="2026-04-01",
        status="active",
    )
    
    assert metadata.status == "active"
    assert len(metadata.tags) == 2
    assert metadata.version == "1.0"


def test_metadata_is_stale():
    """Test staleness detection."""
    # Recent review - not stale
    recent = SectionMetadata(
        tags=["#status/active"],
        created="2026-01-01",
        last_updated="2026-04-01",
        last_reviewed=datetime.now().date().isoformat(),
        status="active",
    )
    assert not recent.is_stale(90)
    
    # Old review - stale
    old = SectionMetadata(
        tags=["#status/active"],
        created="2025-01-01",
        last_updated="2025-01-01",
        last_reviewed="2025-01-01",
        status="active",
    )
    assert old.is_stale(90)


def test_metadata_mark_reviewed():
    """Test marking as reviewed."""
    metadata = SectionMetadata(
        tags=["#status/active"],
        created="2026-01-01",
        last_updated="2026-01-01",
        last_reviewed="2026-01-01",
        status="active",
    )
    
    old_review = metadata.last_reviewed
    metadata.mark_reviewed()
    
    assert metadata.last_reviewed != old_review
    assert metadata.last_reviewed == datetime.now().date().isoformat()


def test_metadata_mark_updated():
    """Test marking as updated."""
    metadata = SectionMetadata(
        tags=["#status/active"],
        created="2026-01-01",
        last_updated="2026-01-01",
        last_reviewed="2026-01-01",
        status="active",
    )
    
    metadata.mark_updated()
    today = datetime.now().date().isoformat()
    
    assert metadata.last_updated == today
    assert metadata.last_reviewed == today


def test_parse_frontmatter_valid():
    """Test parsing valid frontmatter."""
    content = """---
tags:
  - "#type/identity"
  - "#status/active"
created: "2026-03-01"
last_updated: "2026-04-01"
last_reviewed: "2026-04-01"
status: "active"
version: "1.0"
---
# Section Content

This is the body.
"""
    
    metadata, body = parse_frontmatter(content)
    
    assert metadata is not None
    assert metadata.status == "active"
    assert len(metadata.tags) == 2
    assert "# Section Content" in body


def test_parse_frontmatter_no_frontmatter():
    """Test parsing content without frontmatter."""
    content = "# Just Content\n\nNo frontmatter here."
    
    metadata, body = parse_frontmatter(content)
    
    assert metadata is None
    assert body == content


def test_add_frontmatter():
    """Test adding frontmatter to content."""
    content = "# Section\n\nContent here."
    metadata = SectionMetadata(
        tags=["#status/active"],
        created="2026-04-01",
        last_updated="2026-04-01",
        last_reviewed="2026-04-01",
        status="active",
    )
    
    result = add_frontmatter(content, metadata)
    
    assert result.startswith("---\n")
    assert "status: active" in result
    assert "# Section" in result


def test_update_frontmatter_existing():
    """Test updating existing frontmatter."""
    content = """---
tags:
  - "#status/active"
created: "2026-03-01"
last_updated: "2026-03-01"
last_reviewed: "2026-03-01"
status: "active"
version: "1.0"
---
# Content
"""
    
    result = update_frontmatter(content, status="archived")
    
    assert "status: archived" in result
    assert "# Content" in result


def test_update_frontmatter_no_existing():
    """Test updating content without frontmatter creates it."""
    content = "# Content\n\nNo metadata."
    
    result = update_frontmatter(content, status="active")
    
    assert result.startswith("---\n")
    assert "status: active" in result
    assert "# Content" in result


def test_create_default_metadata():
    """Test creating default metadata."""
    metadata = create_default_metadata(tags=["#type/identity"])
    
    assert metadata.status == "active"
    assert "#type/identity" in metadata.tags
    assert metadata.created == datetime.now().date().isoformat()


def test_get_stale_sections():
    """Test finding stale sections."""
    sections = {
        "fresh": """---
tags: ["#status/active"]
created: "2026-01-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Fresh content
""".format(datetime.now().date().isoformat()),
        "stale": """---
tags: ["#status/active"]
created: "2025-01-01"
last_updated: "2025-01-01"
last_reviewed: "2025-01-01"
status: "active"
version: "1.0"
---
Stale content
""",
        "no_metadata": "# No metadata\n\nJust content.",
    }
    
    stale = get_stale_sections(sections, threshold_days=90)
    
    # Should find 2 stale sections (stale + no_metadata)
    assert len(stale) >= 2
    stale_names = [name for name, _ in stale]
    assert "stale" in stale_names
    assert "no_metadata" in stale_names
    assert "fresh" not in stale_names


def test_generate_health_report():
    """Test health report generation."""
    sections = {
        "active1": """---
tags: ["#status/active"]
created: "2026-04-01"
last_updated: "2026-04-01"
last_reviewed: "{}"
status: "active"
version: "1.0"
---
Content
""".format(datetime.now().date().isoformat()),
        "stale1": """---
tags: ["#status/active"]
created: "2025-01-01"
last_updated: "2025-01-01"
last_reviewed: "2025-01-01"
status: "active"
version: "1.0"
---
Content
""",
        "no_meta": "# No metadata",
    }
    
    report = generate_health_report(sections)
    
    assert report["total_sections"] == 3
    assert report["with_metadata"] == 2
    assert len(report["missing_metadata"]) == 1
    assert report["active"] >= 1
    assert report["stale"] >= 1
    assert 0 <= report["health_score"] <= 100
