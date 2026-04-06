"""
vault_enhancements.py — Advanced Vault Content Management

Provides automated metadata generation, smart tagging, and cross-reference detection
for vault content. Enhances the vault with intelligent content analysis.

Features:
- Automated metadata generation from content analysis
- Smart tag suggestions based on content and keywords
- Cross-reference detection between vault sections
- Content summarization for metadata
"""

import re
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime
from collections import Counter

from src.metadata import SectionMetadata, create_default_metadata, add_frontmatter

# Common tag patterns for different content types
TAG_PATTERNS = {
    "type": {
        "identity": ["profile", "user", "personal", "identity"],
        "project": ["project", "initiative", "development"],
        "research": ["research", "analysis", "study", "investigation"],
        "knowledge": ["knowledge", "learning", "documentation"],
        "process": ["process", "workflow", "procedure"],
        "resource": ["resource", "tool", "reference"],
    },
    "domain": {
        "ai": ["ai", "llm", "gpt", "claude", "machine learning", "neural"],
        "blockchain": ["blockchain", "hedera", "hashgraph", "web3", "crypto"],
        "development": ["code", "programming", "development", "software"],
        "frontend": ["react", "ui", "ux", "javascript", "css", "html"],
        "backend": ["api", "database", "server", "backend"],
        "devops": ["docker", "kubernetes", "ci/cd", "deployment"],
        "security": ["security", "encryption", "authentication", "audit"],
    },
    "status": {
        "active": ["active", "current", "ongoing", "in progress"],
        "archived": ["archived", "completed", "deprecated", "obsolete"],
        "draft": ["draft", "wip", "work in progress", "incomplete"],
    },
}


def analyze_content_keywords(content: str, top_n: int = 10) -> List[str]:
    """
    Extract top keywords from content using term frequency.

    Filters out common stop words and extracts meaningful terms.

    Args:
        content: Markdown content to analyze
        top_n: Number of top keywords to return

    Returns:
        List of top keywords
    """
    # Remove markdown formatting
    text = re.sub(r"[#*`\[\]()]", " ", content)
    text = re.sub(r"https?://\S+", "", text)  # Remove URLs

    # Tokenize and filter
    tokens = re.findall(r"\b[a-z]{3,}\b", text.lower())

    # Common stop words to filter
    stop_words = {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "man",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "boy",
        "did",
        "its",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
        "this",
        "that",
        "with",
        "from",
        "have",
        "will",
        "what",
        "when",
        "your",
        "they",
        "been",
        "than",
        "then",
        "them",
        "these",
        "would",
        "there",
        "their",
        "which",
        "about",
    }

    # Filter and count
    filtered = [t for t in tokens if t not in stop_words]
    counts = Counter(filtered)

    return [word for word, _ in counts.most_common(top_n)]


def suggest_tags(content: str, existing_tags: Optional[List[str]] = None) -> List[str]:
    """
    Suggest tags based on content analysis.

    Analyzes content and suggests appropriate tags from predefined patterns.

    Args:
        content: Markdown content to analyze
        existing_tags: Optional list of existing tags to preserve

    Returns:
        List of suggested tags in #category/value format
    """
    suggested = set(existing_tags or [])
    content_lower = content.lower()

    # Check each tag pattern category
    for category, patterns in TAG_PATTERNS.items():
        for tag_value, keywords in patterns.items():
            # Check if any keyword appears in content
            if any(keyword in content_lower for keyword in keywords):
                suggested.add(f"#{category}/{tag_value}")

    # Extract keywords and add as tags
    keywords = analyze_content_keywords(content, top_n=5)
    for keyword in keywords:
        suggested.add(f"#keyword/{keyword}")

    return sorted(list(suggested))


def generate_metadata_from_content(
    content: str, file_path: Optional[Path] = None, status: str = "active"
) -> SectionMetadata:
    """
    Generate metadata automatically from content analysis.

    Analyzes content to suggest appropriate tags and metadata fields.
    Uses file modification time if available.

    Args:
        content: Markdown content
        file_path: Optional path to file (for timestamps)
        status: Initial status (default "active")

    Returns:
        Generated SectionMetadata
    """
    # Suggest tags from content
    tags = suggest_tags(content)

    # Use file modification time if available
    if file_path and file_path.exists():
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        created = mtime.date().isoformat()
    else:
        created = datetime.now().date().isoformat()

    today = datetime.now().date().isoformat()

    return SectionMetadata(
        tags=tags,
        created=created,
        last_updated=today,
        last_reviewed=today,
        status=status,
    )


def detect_cross_references(content: str, all_section_names: List[str]) -> List[str]:
    """
    Detect cross-references to other vault sections.

    Finds references to other sections using common patterns:
    - [[Section Name]] - Wiki-style links
    - See Section Name - Explicit references
    - Section Name mentioned in context

    Args:
        content: Markdown content to analyze
        all_section_names: List of all vault section names

    Returns:
        List of referenced section names
    """
    references = set()

    # Pattern 1: Wiki-style links [[Section Name]]
    wiki_links = re.findall(r"\[\[([^\]]+)\]\]", content)
    references.update(wiki_links)

    # Pattern 2: Markdown links [text](Section Name)
    md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    for text, link in md_links:
        # Check if link is a section name (not URL)
        if not link.startswith(("http://", "https://", "/")):
            references.add(link)

    # Pattern 3: Direct section name mentions
    # Only match if section name appears as a distinct phrase
    for section_name in all_section_names:
        # Create pattern that matches section name as whole words
        pattern = r"\b" + re.escape(section_name) + r"\b"
        if re.search(pattern, content, re.IGNORECASE):
            references.add(section_name)

    return sorted(list(references))


def add_cross_reference_links(content: str, references: List[str]) -> str:
    """
    Add cross-reference section to content.

    Appends a "Related Sections" section with links to referenced content.

    Args:
        content: Original markdown content
        references: List of referenced section names

    Returns:
        Content with cross-reference section appended
    """
    if not references:
        return content

    # Check if cross-reference section already exists
    if "## Related Sections" in content or "## Cross-References" in content:
        return content

    # Build cross-reference section
    xref_section = "\n\n---\n\n## Related Sections\n\n"
    for ref in references:
        xref_section += f"- [[{ref}]]\n"

    return content + xref_section


def enhance_vault_file(
    file_path: Path,
    all_section_names: List[str],
    add_xrefs: bool = True,
    update_metadata: bool = True,
) -> Tuple[str, Dict[str, any]]:
    """
    Enhance a vault file with automated metadata and cross-references.

    Performs full enhancement:
    1. Generate/update metadata from content
    2. Detect cross-references
    3. Add cross-reference links (optional)

    Args:
        file_path: Path to vault markdown file
        all_section_names: List of all vault section names
        add_xrefs: Whether to add cross-reference section
        update_metadata: Whether to update/generate metadata

    Returns:
        Tuple of (enhanced_content, enhancement_info)
        enhancement_info contains: tags, references, metadata_generated
    """
    content = file_path.read_text(encoding="utf-8")

    info = {
        "tags": [],
        "references": [],
        "metadata_generated": False,
        "xrefs_added": False,
    }

    # Detect cross-references
    references = detect_cross_references(content, all_section_names)
    info["references"] = references

    # Generate/update metadata
    if update_metadata:
        from src.metadata import parse_frontmatter

        existing_metadata, body = parse_frontmatter(content)

        if existing_metadata is None:
            # Generate new metadata
            metadata = generate_metadata_from_content(content, file_path)
            content = add_frontmatter(body, metadata)
            info["metadata_generated"] = True
            info["tags"] = metadata.tags
        else:
            # Update existing metadata with suggested tags
            suggested_tags = suggest_tags(content, existing_metadata.tags)
            if set(suggested_tags) != set(existing_metadata.tags):
                existing_metadata.tags = suggested_tags
                content = add_frontmatter(body, existing_metadata)
                info["tags"] = suggested_tags

    # Add cross-reference links
    if add_xrefs and references:
        enhanced = add_cross_reference_links(content, references)
        if enhanced != content:
            content = enhanced
            info["xrefs_added"] = True

    return content, info


def batch_enhance_vault(
    vault_path: Path, dry_run: bool = False, add_xrefs: bool = True, update_metadata: bool = True
) -> Dict[str, any]:
    """
    Enhance all markdown files in a vault directory.

    Processes all .md files and applies enhancements.

    Args:
        vault_path: Path to vault directory
        dry_run: If True, don't write changes (just report)
        add_xrefs: Whether to add cross-reference sections
        update_metadata: Whether to update/generate metadata

    Returns:
        Summary dict with enhancement statistics
    """
    md_files = list(vault_path.glob("**/*.md"))
    section_names = [f.stem for f in md_files]

    summary = {
        "total_files": len(md_files),
        "enhanced": 0,
        "metadata_generated": 0,
        "xrefs_added": 0,
        "total_references": 0,
        "errors": [],
    }

    for file_path in md_files:
        try:
            content, info = enhance_vault_file(
                file_path, section_names, add_xrefs=add_xrefs, update_metadata=update_metadata
            )

            if info["metadata_generated"] or info["xrefs_added"]:
                summary["enhanced"] += 1

                if not dry_run:
                    file_path.write_text(content, encoding="utf-8")

            if info["metadata_generated"]:
                summary["metadata_generated"] += 1

            if info["xrefs_added"]:
                summary["xrefs_added"] += 1

            summary["total_references"] += len(info["references"])

        except Exception as e:
            summary["errors"].append(f"{file_path.name}: {str(e)}")

    return summary
