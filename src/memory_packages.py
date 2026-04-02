"""
memory_packages.py — Episodic + Semantic Memory Package Layer

Implements the "relevance-gated memory package loading" concept from the patent:
- Each vault file (session archive, research doc, project file) = one encrypted HFS package
- A package index JSON stores metadata for all packages: name, category, keywords, file_id
- At load time, query the index by relevance threshold — load only what matters
- Package index file_id is stored in the vault index, so one contract lookup reaches everything

Four memory layer mapping:
short-term -> active context window (not stored here)
long-term -> Phase 1: SOUL.md, USER.md, Symbiote.md (vault.py)
episodic -> session archives (category="sessions")
semantic -> research + projects (category="research" | "projects")

Package index schema (encrypted JSON on HFS):
{
"version": "1.0",
"last_updated": "YYYY-MM-DD",
"packages": [
{
"name": "session_2026-03-16_sovereign-ai-patent-poc",
"category": "sessions",
"description": "Session archive: Sovereign AI patent PoC end-to-end run",
"keywords": ["patent", "hedera", "poc", "hfs", "soul", "token"],
"date": "2026-03-16",
"size": 2744,
"file_id": "0.0.8252800"
},
...
]
}

Usage:
from src.memory_packages import push_package, query_packages, push_package_index
"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

from src.context_storage import store_context, load_context, update_context
from src.crypto import compress, decompress
from src.vault import (
    get_package_key, get_index_key,
    _make_package_aad, _make_package_index_aad, _make_index_aad,
    load_local_index, save_local_index, CONTEXT_TOKEN_ID, verify_content,
)
from src.event_log import log_event

# ---------------------------------------------------------------------------
# Vault paths for each category
# ---------------------------------------------------------------------------
VAULT_ROOT = Path(r"D:\symbiote_suit")

PACKAGE_CATEGORIES: dict[str, Path] = {
    "sessions": VAULT_ROOT / "Archive",
    "research": VAULT_ROOT / "Research",
    "projects": VAULT_ROOT / "02 - Projects",
}

# Files to skip (READMEs, empty files, PDFs handled separately)
SKIP_NAMES = {"README.md", "EdTech Integration Service.md"}
SKIP_EXTENSIONS = {".pdf"}


# ---------------------------------------------------------------------------
# Package metadata model
# ---------------------------------------------------------------------------

@dataclass
class PackageMetadata:
    name: str  # filename without extension
    category: str  # sessions | research | projects
    description: str  # first meaningful line of the file
    keywords: list  # extracted from filename + content
    date: str  # ISO date string (extracted or today)
    size: int  # raw bytes
    file_id: str  # HFS file ID (set after push)
    bounded_context: str = "general"  # Bounded context for domain organization


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def extract_date_from_name(name: str) -> str:
    """Extract YYYY-MM-DD from filename if present, else return today."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if match:
        return match.group(1)
    return str(date.today())


def extract_keywords(name: str, content: str, max_keywords: int = 12) -> list[str]:
    """
    Extract keywords from filename tokens + first 500 chars of content.

    Strategy:
    - Split filename on underscores, dashes, spaces
    - Pull significant words from first paragraph of content
    - Deduplicate, lowercase, filter short words
    """
    # From filename
    name_tokens = re.split(r"[_\-\s]+", name.lower())
    name_tokens = [t for t in name_tokens if len(t) > 3 and not t.isdigit()]

    # From content header (first 500 chars)
    header = content[:500]
    heading_words = re.findall(r"#+ (.+)", header)
    heading_text = " ".join(heading_words)
    content_tokens = re.findall(r"\b[a-z][a-z0-9]{3,}\b", heading_text.lower())

    all_keywords = list(dict.fromkeys(name_tokens + content_tokens))  # dedup, preserve order
    return all_keywords[:max_keywords]


def extract_description(name: str, content: str) -> str:
    """Extract a short description from the file content."""
    lines = content.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:120]

    # Fallback: use the filename
    return name.replace("_", " ").replace("-", " ").title()


def build_metadata(path: Path, category: str, file_id: str = "") -> PackageMetadata:
    """Build PackageMetadata from a vault file path."""
    content = path.read_text(encoding="utf-8", errors="replace")
    name = path.stem  # filename without extension

    return PackageMetadata(
        name=name,
        category=category,
        description=extract_description(name, content),
        keywords=extract_keywords(name, content),
        date=extract_date_from_name(name),
        size=path.stat().st_size,
        file_id=file_id,
    )


# ---------------------------------------------------------------------------
# Push / pull individual packages
# ---------------------------------------------------------------------------

def push_package(
    path: Path,
    category: str,
    key: bytes,
    token_id: str,
    existing_file_id: Optional[str] = None,
) -> tuple["PackageMetadata", str]:
    """
    Encrypt and store one vault file as a memory package on HFS.

    Args:
        path: Local file path
        category: "sessions" | "research" | "projects"
        key: 32-byte AES key
        token_id: context token ID
        existing_file_id: HFS file ID if updating existing package

    Returns:
        (PackageMetadata with file_id populated, compression ratio string)
    """
    content = path.read_bytes()
    package_name = path.stem
    aad = _make_package_aad(package_name, token_id)
    payload = compress(content)
    ratio = f"{len(content)}B -> {len(payload)}B"

    if existing_file_id:
        update_context(key, existing_file_id, payload, token_id, aad)
        file_id = existing_file_id
    else:
        file_id = store_context(key, payload, token_id, aad)

    meta = build_metadata(path, category, file_id)
    return meta, ratio


def pull_package(
    file_id: str,
    key: bytes,
    token_id: str,
    package_name: str = "",
) -> bytes:
    """
    Fetch, verify, and decrypt a memory package from HFS.

    Args:
        file_id: HFS file ID
        key: 32-byte AES key
        token_id: context token ID
        package_name: label for audit log and error messages

    Returns:
        Verified, decrypted package bytes
    """
    label = package_name or file_id
    aad = _make_package_aad(package_name, token_id) if package_name else None
    raw = load_context(key, file_id, token_id, aad)
    content = decompress(raw)
    verify_content(content, label)

    log_event(
        event_type="PACKAGE_ACCESSED",
        payload={
            "token_id": token_id,
            "file_id": file_id,
            "package_name": label,
            "content_hash": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        },
    )

    return content


def _pull_package_task(args: tuple) -> tuple[str, bytes]:
    """Worker for pull_packages_parallel(). Each call creates its own client — thread-safe."""
    pkg_name, file_id, key, token_id = args
    content = pull_package(file_id, key, token_id, package_name=pkg_name)
    return pkg_name, content


def pull_packages_parallel(
    packages: list[tuple[str, str]],
    key: bytes,
    token_id: str,
    max_workers: int = 8,
) -> dict[str, bytes]:
    """
    Fetch multiple packages from HFS concurrently.

    Args:
        packages: list of (package_name, file_id) tuples
        key: 32-byte AES package key
        token_id: context token ID
        max_workers: max parallel fetches (default 8, capped at len(packages))

    Returns:
        dict of {package_name: content_bytes} — order not guaranteed
    """
    if not packages:
        return {}

    tasks = [(name, fid, key, token_id) for name, fid in packages]
    workers = min(len(tasks), max_workers)
    results: dict[str, bytes] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_pull_package_task, task): task[0] for task in tasks}
        for future in as_completed(futures):
            pkg_name, content = future.result()
            results[pkg_name] = content

    return results


# ---------------------------------------------------------------------------
# Package index push / pull
# ---------------------------------------------------------------------------

def push_package_index(
    packages: list[PackageMetadata],
    key: bytes,
    token_id: str,
    existing_index_file_id: Optional[str] = None,
) -> str:
    """
    Encrypt and store the package index on HFS.

    Args:
        packages: list of PackageMetadata
        key: 32-byte AES key
        token_id: context token ID
        existing_index_file_id: if set, updates the existing HFS file

    Returns:
        HFS file_id of the package index
    """
    index = {
        "version": "1.0",
        "last_updated": str(date.today()),
        "packages": [asdict(p) for p in packages],
    }
    index_bytes = json.dumps(index, indent=2).encode("utf-8")
    aad = _make_package_index_aad(token_id)

    if existing_index_file_id:
        update_context(key, existing_index_file_id, index_bytes, token_id, aad)
        return existing_index_file_id
    else:
        return store_context(key, index_bytes, token_id, aad)


def pull_package_index(index_file_id: str, key: bytes, token_id: str) -> list[PackageMetadata]:
    """
    Fetch and decrypt the package index from HFS.
    Validates JSON structure and emits PACKAGE_INDEX_ACCESSED to HCS.

    Returns:
        List of PackageMetadata objects
    """
    aad = _make_package_index_aad(token_id)
    raw = load_context(key, index_file_id, token_id, aad)

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"[integrity:package_index] Index corrupt or tampered: {e}")

    packages = [PackageMetadata(**p) for p in data.get("packages", [])]

    log_event(
        event_type="PACKAGE_INDEX_ACCESSED",
        payload={
            "token_id": token_id,
            "index_file_id": index_file_id,
            "package_count": len(packages),
        },
    )

    return packages


# ---------------------------------------------------------------------------
# Relevance-gated query
# ---------------------------------------------------------------------------

def query_packages(
    query: str,
    packages: list[PackageMetadata],
    top_n: int = 5,
    threshold: float = 0.0,
    use_rag: bool = True,
) -> list[tuple[float, PackageMetadata]]:
    """
    Score and rank packages by relevance to the query.

    Args:
        query: Natural language query string
        packages: List of PackageMetadata to search
        top_n: Maximum results to return
        threshold: Minimum score to include (0.0 = return all matches)
        use_rag: Use TF-IDF RAG scoring (default True)

    Returns:
        List of (score, PackageMetadata) sorted by score descending
    """
    if use_rag:
        from src.rag import rag_query_packages
        return rag_query_packages(query, packages, top_n, threshold)

    # Fallback: simple keyword overlap
    query_tokens = set(re.findall(r"\b[a-z][a-z0-9]{2,}\b", query.lower()))

    if not query_tokens:
        return []

    scored = []
    for pkg in packages:
        pkg_tokens = set(
            re.findall(
                r"\b[a-z][a-z0-9]{2,}\b",
                " ".join([
                    pkg.name,
                    pkg.description,
                    " ".join(pkg.keywords),
                    pkg.category,
                ]).lower(),
            )
        )

        overlap = query_tokens & pkg_tokens
        if not overlap:
            continue

        score = len(overlap) / len(query_tokens)

        if score >= threshold:
            scored.append((score, pkg))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# High-level: push_all_packages
# ---------------------------------------------------------------------------

def push_all_packages(
    categories: Optional[list[str]] = None,
    force_new: bool = False,
) -> str:
    """
    Push all vault packages for the specified categories to HFS.
    Updates the vault index with the package_index_file_id.

    Args:
        categories: list of categories to push, or None for all
        force_new: if True, create new HFS files for everything

    Returns:
        HFS file_id of the package index
    """
    token_id = CONTEXT_TOKEN_ID
    package_key = get_package_key(token_id)
    index_key = get_index_key(token_id)
    local = load_local_index()
    existing_packages_map: dict[str, str] = local.get("packages_map", {})
    existing_index_file_id = None if force_new else local.get("packages_index_file_id")

    stored_hashes: dict[str, str] = local.get("packages_hashes", {})
    current_hashes: dict[str, str] = dict(stored_hashes)
    packages_changed = False

    cats = categories or list(PACKAGE_CATEGORIES.keys())
    all_metadata: list[PackageMetadata] = []

    for category in cats:
        cat_dir = PACKAGE_CATEGORIES[category]
        if not cat_dir.exists():
            print(f" [WARN] {cat_dir} not found — skipping '{category}'")
            continue

        files = [
            f for f in sorted(cat_dir.iterdir())
            if f.is_file()
            and f.name not in SKIP_NAMES
            and f.suffix not in SKIP_EXTENSIONS
            and f.stat().st_size > 0
        ]

        print(f"\n[packages] {category} ({len(files)} files)...")

        for path in files:
            content = path.read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
            current_hashes[path.stem] = content_hash

            existing_fid = existing_packages_map.get(path.stem) if not force_new else None

            if not force_new and existing_fid and stored_hashes.get(path.stem) == content_hash:
                print(f" {path.name:<55} unchanged -- skipping")
                all_metadata.append(build_metadata(path, category, existing_fid))
                continue

            packages_changed = True
            meta, ratio = push_package(path, category, package_key, token_id, existing_fid)
            all_metadata.append(meta)
            print(f" {path.name:<55} -> {meta.file_id} ({ratio})")
            existing_packages_map[path.stem] = meta.file_id

    if not packages_changed and existing_index_file_id:
        print(f"\n[packages] No packages changed -- reusing index {existing_index_file_id}")
        index_file_id = existing_index_file_id
    else:
        print(f"\n[packages] Pushing package index ({len(all_metadata)} packages, package_key)...")
        index_file_id = push_package_index(
            all_metadata, package_key, token_id, existing_index_file_id
        )
        print(f" Package index -> {index_file_id}")

    _update_vault_index_with_packages(index_key, token_id, local, index_file_id)

    local["packages_index_file_id"] = index_file_id
    local["packages_map"] = existing_packages_map
    local["packages_hashes"] = current_hashes
    save_local_index(local)

    log_event(
        event_type="PACKAGES_PUSHED",
        payload={
            "token_id": token_id,
            "packages_index_file_id": index_file_id,
            "count": len(all_metadata),
            "categories": cats,
        },
    )

    return index_file_id


def _update_vault_index_with_packages(
    key: bytes,
    token_id: str,
    local: dict,
    packages_index_file_id: str,
) -> None:
    """
    Update the encrypted vault index on HFS to include the package index file_id.
    This allows a single contract lookup to reach all data.
    """
    from src.context_storage import load_context, update_context

    vault_index_file_id = local.get("index_file_id")
    if not vault_index_file_id:
        print(" [WARN] No vault index file_id in local cache — skipping vault index update")
        return

    index_aad = _make_index_aad(token_id)

    raw = load_context(key, vault_index_file_id, token_id, index_aad)
    vault_index = json.loads(raw.decode("utf-8"))

    vault_index["packages"] = packages_index_file_id

    updated = json.dumps(vault_index, indent=2).encode("utf-8")
    update_context(key, vault_index_file_id, updated, token_id, index_aad)
    print(f" Vault index updated with packages pointer -> {vault_index_file_id}")
