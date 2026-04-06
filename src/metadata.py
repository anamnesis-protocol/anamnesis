"""
metadata.py — Vault Section Metadata Management

YAML frontmatter-based metadata for vault sections.
Provides organization and staleness detection for vault content.

Metadata Schema:
---
tags: ["#type/identity", "#status/active"]
created: "2026-03-01"
last_updated: "2026-04-01"
last_reviewed: "2026-04-01"
status: "active"
version: "1.0"
---

Features:
- Parse and update YAML frontmatter in markdown files
- Track creation, update, and review timestamps
- Detect stale sections (not reviewed in 90+ days)
- Tag-based organization
- Status tracking (active, stale, archived)
"""

import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional
import yaml


@dataclass
class SectionMetadata:
    """Metadata for a vault section."""

    tags: list[str]
    created: str  # ISO date: YYYY-MM-DD
    last_updated: str  # ISO date: YYYY-MM-DD
    last_reviewed: str  # ISO date: YYYY-MM-DD
    status: str  # active | stale | archived
    version: str = "1.0"

    def to_dict(self) -> dict:
        """Convert to dict for YAML serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SectionMetadata":
        """Create from dict (YAML deserialization)."""
        return cls(**data)

    def is_stale(self, days: int = 90) -> bool:
        """
        Check if section is stale (not reviewed recently).

        Args:
            days: Number of days before considering stale (default 90)

        Returns:
            True if last_reviewed is older than threshold
        """
        try:
            last_review = datetime.fromisoformat(self.last_reviewed)
            threshold = datetime.now() - timedelta(days=days)
            return last_review < threshold
        except (ValueError, TypeError):
            return True  # Invalid date = stale

    def mark_reviewed(self) -> None:
        """Update last_reviewed to today."""
        self.last_reviewed = datetime.now().date().isoformat()

    def mark_updated(self) -> None:
        """Update last_updated and last_reviewed to today."""
        today = datetime.now().date().isoformat()
        self.last_updated = today
        self.last_reviewed = today


def parse_frontmatter(content: str) -> tuple[Optional[SectionMetadata], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Full markdown file content

    Returns:
        Tuple of (metadata, body_content)
        metadata is None if no frontmatter found
    """
    # Match YAML frontmatter: ---\n...\n---
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return None, content

    try:
        yaml_str = match.group(1)
        body = match.group(2)
        data = yaml.safe_load(yaml_str)

        if not data:
            return None, content

        metadata = SectionMetadata.from_dict(data)
        return metadata, body
    except (yaml.YAMLError, TypeError, KeyError):
        # Invalid frontmatter - return as-is
        return None, content


def add_frontmatter(content: str, metadata: SectionMetadata) -> str:
    """
    Add or update YAML frontmatter in markdown content.

    Args:
        content: Markdown content (with or without existing frontmatter)
        metadata: Metadata to insert

    Returns:
        Content with frontmatter prepended
    """
    # Remove existing frontmatter if present
    _, body = parse_frontmatter(content)

    # Build YAML frontmatter
    yaml_str = yaml.dump(
        metadata.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    return f"---\n{yaml_str}---\n{body}"


def update_frontmatter(content: str, **updates) -> str:
    """
    Update specific fields in frontmatter.

    Args:
        content: Markdown content with frontmatter
        **updates: Fields to update (e.g., status="archived")

    Returns:
        Content with updated frontmatter

    Example:
        >>> content = update_frontmatter(content, status="archived", last_reviewed="2026-04-01")
    """
    metadata, body = parse_frontmatter(content)

    if metadata is None:
        # No existing frontmatter - create default
        metadata = SectionMetadata(
            tags=["#status/active"],
            created=datetime.now().date().isoformat(),
            last_updated=datetime.now().date().isoformat(),
            last_reviewed=datetime.now().date().isoformat(),
            status="active",
        )

    # Apply updates
    for key, value in updates.items():
        if hasattr(metadata, key):
            setattr(metadata, key, value)

    return add_frontmatter(body, metadata)


def create_default_metadata(
    tags: Optional[list[str]] = None, status: str = "active"
) -> SectionMetadata:
    """
    Create default metadata for a new section.

    Args:
        tags: Optional list of tags
        status: Section status (default "active")

    Returns:
        SectionMetadata with today's dates
    """
    today = datetime.now().date().isoformat()
    return SectionMetadata(
        tags=tags or ["#status/active"],
        created=today,
        last_updated=today,
        last_reviewed=today,
        status=status,
    )


def get_stale_sections(sections: dict[str, str], threshold_days: int = 90) -> list[tuple[str, int]]:
    """
    Find stale sections (not reviewed recently).

    Args:
        sections: Dict of {section_name: content}
        threshold_days: Days before considering stale

    Returns:
        List of (section_name, days_since_review) for stale sections
    """
    stale = []

    for name, content in sections.items():
        metadata, _ = parse_frontmatter(content)

        if metadata is None:
            # No metadata = treat as stale
            stale.append((name, 999))
            continue

        if metadata.is_stale(threshold_days):
            try:
                last_review = datetime.fromisoformat(metadata.last_reviewed)
                days_ago = (datetime.now() - last_review).days
                stale.append((name, days_ago))
            except (ValueError, TypeError):
                stale.append((name, 999))

    return sorted(stale, key=lambda x: x[1], reverse=True)


def generate_health_report(sections: dict[str, str]) -> dict:
    """
    Generate health report for vault sections.

    Args:
        sections: Dict of {section_name: content}

    Returns:
        Dict with health metrics
    """
    total = len(sections)
    with_metadata = 0
    active = 0
    stale = 0
    archived = 0

    stale_list = []
    missing_metadata = []

    for name, content in sections.items():
        metadata, _ = parse_frontmatter(content)

        if metadata is None:
            missing_metadata.append(name)
            continue

        with_metadata += 1

        if metadata.status == "active":
            active += 1
        elif metadata.status == "archived":
            archived += 1

        if metadata.is_stale(90):
            stale += 1
            try:
                last_review = datetime.fromisoformat(metadata.last_reviewed)
                days_ago = (datetime.now() - last_review).days
                stale_list.append((name, days_ago))
            except (ValueError, TypeError):
                stale_list.append((name, 999))

    health_score = int((with_metadata / total * 100)) if total > 0 else 0

    return {
        "total_sections": total,
        "with_metadata": with_metadata,
        "missing_metadata": missing_metadata,
        "active": active,
        "stale": stale,
        "archived": archived,
        "stale_sections": sorted(stale_list, key=lambda x: x[1], reverse=True),
        "health_score": health_score,
    }
