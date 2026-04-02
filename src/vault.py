"""
vault.py — Symbiote Vault Sync Module

Encrypts and syncs core identity files from the local Symbiote Vault
to Hedera File Service (HFS), gated by the context token (0.0.8252163).

Architecture:
- Vault index: one encrypted JSON {section_name: file_id} stored on HFS
- Index file_id registered in ContextValidator contract under context token
- Key derived from: HKDF-SHA256(token_id + operator_ED25519_signature)
- Same crypto.py / context_storage.py primitives as the main PoC

Security improvements (book-derived):
- Context integrity verification on every pull (injection pattern detection + hash check)
- Purpose-separated key derivation: section key, index key, package key
- Full HCS audit trail on both push AND pull operations

Vault sections (Phase 1):
soul -> Knowledge/SOUL.md
user -> Personas/USER.md
symbiote -> Personas/Symbiote.md
session_state -> System/Session-State.md

Usage:
from src.vault import push_all, pull_section, get_vault_key
"""

import base64
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.config import get_client, get_treasury, get_validator_contract_id
from src.crypto import make_challenge, derive_key, encrypt_context, decrypt_context, compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.contract import (
    token_id_to_evm_address,
    register_file,
    get_registered_file_id,
)
from src.event_log import log_event

# ---------------------------------------------------------------------------
# Vault root — configurable per user via env var
# ---------------------------------------------------------------------------
VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))

# Core sections: section_name -> relative path from VAULT_ROOT
# Defaults are generic flat paths. Override via VAULT_SECTIONS_JSON env var
# (JSON object mapping section names to relative paths).
_sections_override = os.environ.get("VAULT_SECTIONS_JSON")
VAULT_SECTIONS: dict[str, str] = (
    json.loads(_sections_override)
    if _sections_override
    else {
        "soul": "soul.md",
        "user": "user.md",
        "symbiote": "symbiote.md",
        "session_state": "session_state.md",
    }
)

# Directory bundles: section_name -> relative directory path from VAULT_ROOT
# Empty by default — populate via VAULT_DIRS_JSON env var if needed.
_dirs_override = os.environ.get("VAULT_DIRS_JSON")
VAULT_DIRS: dict[str, str] = json.loads(_dirs_override) if _dirs_override else {}

# Per-directory push options
VAULT_DIR_OPTIONS: dict[str, dict] = {}

# File extensions included in directory bundles
_DIR_BUNDLE_EXTENSIONS: tuple[str, ...] = (".md",)

# Local cache of the vault index (file_id mapping)
VAULT_INDEX_CACHE = Path(__file__).parent.parent / ".vault_index.json"

# Context token — must be set via env var; no Drake default
CONTEXT_TOKEN_ID = os.environ.get("CONTEXT_TOKEN_ID", "")
CONTEXT_TOKEN_SERIAL = 1

# ---------------------------------------------------------------------------
# HKDF info labels — purpose-separated key derivation
# ---------------------------------------------------------------------------
_INFO_SECTION = b"sovereign-ai-section-v1"
_INFO_INDEX = b"sovereign-ai-index-v1"
_INFO_PACKAGE = b"sovereign-ai-package-v1"
_INFO_LEGACY = b"sovereign-ai-context-v1"

# ---------------------------------------------------------------------------
# Injection pattern detection (AI-Security.md — OWASP LLM01, LLM02)
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:previous|all|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"new\s+instructions\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"<\|system\|>", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
    re.compile(r"disregard\s+(?:previous|all|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"\[\[INJECT\]\]", re.IGNORECASE),
    re.compile(r"assistant:\s*sure,\s*here", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Key derivation — purpose-separated
# ---------------------------------------------------------------------------

def get_wallet_signature(token_id: str) -> bytes:
    """
    Sign the sovereign-ai-context challenge with the operator's ED25519 key.

    For PoC: uses OPERATOR_KEY from environment.
    Production: replace with hardware wallet / MetaMask signature flow.

    Returns:
        64-byte ED25519 signature over the challenge bytes
    """
    _, treasury_key = get_treasury()
    challenge = make_challenge(token_id)
    signature: bytes = treasury_key.sign(challenge)
    return signature


def get_vault_key(token_id: str) -> bytes:
    """
    Legacy key — backward compat for data encrypted before purpose-separation.
    Uses original info string: b"sovereign-ai-context-v1".
    """
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_LEGACY)


def get_section_key(token_id: str) -> bytes:
    """
    Purpose-separated key for vault section content (SOUL, USER, Symbiote, Session-State).
    info = b"sovereign-ai-section-v1"
    """
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_SECTION)


def get_index_key(token_id: str) -> bytes:
    """
    Purpose-separated key for vault index JSON.
    info = b"sovereign-ai-index-v1"
    """
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_INDEX)


def get_package_key(token_id: str) -> bytes:
    """
    Purpose-separated key for memory packages (sessions, research, projects).
    info = b"sovereign-ai-package-v1"
    """
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_PACKAGE)


# ---------------------------------------------------------------------------
# Context integrity verification (Claims 6-7 / AI-Security LLM01)
# ---------------------------------------------------------------------------

def verify_content(
    content: bytes,
    label: str,
    expected_hash: str | None = None,
) -> None:
    """
    Verify decrypted vault content before it is loaded into model context.

    Checks (in order):
    1. UTF-8 decodable — not corrupted or binary garbage
    2. Non-empty — not a blank/wiped section
    3. Injection patterns — scan for known prompt hijack strings (OWASP LLM01)
    4. Hash integrity — if expected_hash provided, verify SHA-256 match

    Args:
        content: Decrypted bytes from HFS
        label: Human label for error messages (section name or file_id)
        expected_hash: Optional SHA-256 hex digest to verify against

    Raises:
        ValueError: if any check fails — caller must NOT load this content
    """
    # 1. UTF-8 decodable
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"[integrity:{label}] UTF-8 decode failed — possible corruption: {e}"
        )

    # 2. Non-empty
    if not text.strip():
        raise ValueError(f"[integrity:{label}] Content is empty — possible wipe attack")

    # 3. Injection pattern scan — generic error to avoid leaking pattern details
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise ValueError(
                f"[integrity:{label}] Content failed security scan — "
                "possible injection attempt. Load aborted."
            )

    # 4. Hash integrity
    if expected_hash:
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected_hash:
            raise ValueError(
                f"[integrity:{label}] Hash mismatch — "
                f"expected {expected_hash[:16]}... got {actual[:16]}..."
            )


# ---------------------------------------------------------------------------
# AAD helpers — purpose-binding for AES-GCM (security audit H1 fix)
# ---------------------------------------------------------------------------

def _make_section_aad(section_name: str, token_id: str) -> bytes:
    """AAD for vault section ciphertexts: b"section:{name}:{token_id}"."""
    return f"section:{section_name}:{token_id}".encode("utf-8")


def _make_index_aad(token_id: str) -> bytes:
    """AAD for vault index ciphertext: b"index:{token_id}"."""
    return f"index:{token_id}".encode("utf-8")


def _make_package_aad(package_name: str, token_id: str) -> bytes:
    """AAD for memory package ciphertexts: b"package:{name}:{token_id}"."""
    return f"package:{package_name}:{token_id}".encode("utf-8")


def _make_package_index_aad(token_id: str) -> bytes:
    """AAD for package index ciphertext: b"package_index:{token_id}"."""
    return f"package_index:{token_id}".encode("utf-8")


# ---------------------------------------------------------------------------
# Directory bundle helpers (Phase 2)
# ---------------------------------------------------------------------------

def bundle_directory(
    dir_path: Path,
    extensions: tuple[str, ...] = _DIR_BUNDLE_EXTENSIONS,
    recursive: bool = True,
) -> bytes:
    """
    Bundle all matching files in a directory into a JSON manifest (bytes).

    Format: {"relative/path/file.md": "<base64-encoded content>", ...}
    Files are sorted for deterministic output (same files → same hash).

    Args:
        dir_path: Absolute path to the directory to bundle
        extensions: File extensions to include (default: .md only)
        recursive: If True (default), recurse into subdirectories via rglob.
            If False, only include direct children via glob.

    Returns:
        UTF-8 JSON bytes of the manifest (before compression/encryption)
    """
    manifest: dict[str, str] = {}
    file_iter = sorted(dir_path.rglob("*")) if recursive else sorted(dir_path.glob("*"))
    for filepath in file_iter:
        if filepath.is_file() and filepath.suffix in extensions:
            rel = filepath.relative_to(dir_path).as_posix()
            manifest[rel] = base64.b64encode(filepath.read_bytes()).decode("ascii")
    return json.dumps(manifest, indent=2, ensure_ascii=True).encode("utf-8")


def unbundle_directory(bundle_bytes: bytes, output_dir: Path) -> list[str]:
    """
    Unpack a directory bundle manifest back to disk.

    Creates subdirectories as needed. Overwrites existing files.

    Args:
        bundle_bytes: JSON manifest bytes from bundle_directory()
        output_dir: Directory to write files into

    Returns:
        List of written file paths (as strings)
    """
    manifest: dict[str, str] = json.loads(bundle_bytes.decode("utf-8"))
    written: list[str] = []
    for rel_path, content_b64 in manifest.items():
        out_path = output_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(content_b64))
        written.append(str(out_path))
    return written


def bundle_from_dict(files: dict[str, str]) -> bytes:
    """
    Create a dir bundle manifest from an in-memory {path: utf-8 string} dict.

    Args:
        files: {relative_path: utf-8 content string}
            Example: {"2026-03-17-session.md": "# Session\n..."}

    Returns:
        UTF-8 JSON bytes of the manifest (before compression/encryption)
    """
    manifest: dict[str, str] = {
        path: base64.b64encode(content.encode("utf-8")).decode("ascii")
        for path, content in sorted(files.items())
    }
    return json.dumps(manifest, indent=2, ensure_ascii=True).encode("utf-8")


def unbundle_to_dict(bundle_bytes: bytes) -> dict[str, str]:
    """
    Decode a dir bundle manifest back to an in-memory {path: utf-8 string} dict.

    Args:
        bundle_bytes: JSON manifest bytes (from bundle_from_dict or bundle_directory)

    Returns:
        {relative_path: utf-8 content string}
    """
    manifest: dict[str, str] = json.loads(bundle_bytes.decode("utf-8"))
    return {
        path: base64.b64decode(content_b64).decode("utf-8", errors="replace")
        for path, content_b64 in manifest.items()
    }


def push_dir_section(
    dir_name: str,
    dir_path: Path,
    key: bytes,
    token_id: str,
    existing_file_id: str | None = None,
    recursive: bool = True,
) -> str:
    """
    Bundle, compress, encrypt, and store a directory section on HFS.

    Args:
        dir_name: Section key name (e.g. "dir:research")
        dir_path: Absolute path to the directory
        key: 32-byte section key from get_section_key()
        token_id: Context token ID (for AAD and audit log)
        existing_file_id: HFS file ID to update, or None to create new
        recursive: If False, only bundle direct children (no subdirs).

    Returns:
        HFS file ID string
    """
    aad = f"dir:{dir_name}:{token_id}".encode("utf-8")
    bundle = bundle_directory(dir_path, recursive=recursive)
    payload = compress(bundle)
    ratio = f"{len(bundle)}B -> {len(payload)}B (gzip)"

    if existing_file_id:
        update_context(key, existing_file_id, payload, token_id, aad)
        print(f" Updated dir '{dir_name}' -> {existing_file_id} ({ratio})")
        return existing_file_id
    else:
        file_id = store_context(key, payload, token_id, aad)
        print(f" Stored dir '{dir_name}' -> {file_id} ({ratio})")
        return file_id


def pull_dir_section(
    dir_name: str,
    file_id: str,
    key: bytes,
    token_id: str,
    output_dir: Path,
) -> list[str]:
    """
    Fetch, decrypt, and unpack a directory section from HFS to disk.

    Args:
        dir_name: Section key name (e.g. "dir:research")
        file_id: HFS file ID
        key: 32-byte section key
        token_id: Context token ID (for AAD binding and audit log)
        output_dir: Local directory to write recovered files into

    Returns:
        List of written file paths
    """
    aad = f"dir:{dir_name}:{token_id}".encode("utf-8")
    raw = load_context(key, file_id, token_id, aad)
    bundle_bytes = decompress(raw)
    written = unbundle_directory(bundle_bytes, output_dir)

    log_event(
        event_type="DIR_SECTION_PULLED",
        payload={
            "token_id": token_id,
            "dir_name": dir_name,
            "file_id": file_id,
            "files_written": len(written),
        },
    )

    return written


# ---------------------------------------------------------------------------
# Section push / pull
# ---------------------------------------------------------------------------

def push_section(
    section_name: str,
    content: bytes,
    key: bytes,
    token_id: str,
    existing_file_id: str | None = None,
) -> str:
    """
    Compress, encrypt, and store a vault section on HFS.
    AAD binds ciphertext to section name + token.
    """
    aad = _make_section_aad(section_name, token_id)
    payload = compress(content)
    ratio = f"{len(content)}B -> {len(payload)}B"
    if existing_file_id:
        update_context(key, existing_file_id, payload, token_id, aad)
        print(f" Updated section '{section_name}' -> {existing_file_id} ({ratio})")
        return existing_file_id
    else:
        file_id = store_context(key, payload, token_id, aad)
        print(f" Stored section '{section_name}' -> {file_id} ({ratio})")
        return file_id


def pull_section(
    file_id: str,
    key: bytes,
    token_id: str,
    section_name: str = "",
    expected_hash: str | None = None,
) -> bytes:
    """
    Fetch, verify, and decrypt a vault section from HFS.

    - Uses AAD to bind decryption to this specific section name + token
    - Runs integrity verification (injection scan + optional hash check)
    - Emits VAULT_SECTION_ACCESSED event to HCS audit trail

    Args:
        file_id: HFS file ID
        key: 32-byte AES key
        token_id: context token ID
        section_name: label for AAD binding, audit log, and error messages
        expected_hash: optional SHA-256 hex of expected plaintext

    Returns:
        Verified, decrypted file bytes

    Raises:
        ValueError: if integrity verification fails
        InvalidTag: if key, AAD, or ciphertext is wrong
    """
    aad = _make_section_aad(section_name, token_id) if section_name else None
    raw = load_context(key, file_id, token_id, aad)
    content = decompress(raw)
    label = section_name or file_id
    verify_content(content, label, expected_hash)

    log_event(
        event_type="VAULT_SECTION_ACCESSED",
        payload={
            "token_id": token_id,
            "file_id": file_id,
            "section_name": label,
            "content_hash": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        },
    )

    return content


# ---------------------------------------------------------------------------
# Vault index push / pull
# ---------------------------------------------------------------------------

def push_index(
    index: dict[str, str],
    key: bytes,
    token_id: str,
    section_hashes: dict[str, str] | None = None,
) -> str:
    """
    Encrypt and store the vault index JSON on HFS.
    AAD binds ciphertext to index domain.

    If section_hashes is provided, it is embedded in the index as '_section_hashes'.
    """
    aad = _make_index_aad(token_id)
    payload = dict(index)
    if section_hashes:
        payload["_section_hashes"] = section_hashes
    index_bytes = json.dumps(payload, indent=2).encode("utf-8")
    file_id = store_context(key, index_bytes, token_id, aad)
    print(f" Vault index stored -> {file_id}")
    return file_id


def update_index(
    index_file_id: str,
    index: dict,
    key: bytes,
    token_id: str,
    section_hashes: dict[str, str] | None = None,
) -> None:
    """
    Update an existing vault index file on HFS in place.

    Args:
        index_file_id: Existing HFS file ID for the vault index
        index: Full index dict {section_name: file_id, ...}
        key: 32-byte index key (from session store)
        token_id: Context token ID (for AAD binding and audit log)
        section_hashes: Updated {section_name: sha256_hex} map to embed
    """
    aad = _make_index_aad(token_id)
    payload = dict(index)
    if section_hashes:
        payload["_section_hashes"] = section_hashes
    index_bytes = json.dumps(payload, indent=2).encode("utf-8")
    update_context(key, index_file_id, index_bytes, token_id, aad)
    print(f" Vault index updated in place -> {index_file_id}")


def pull_index(index_file_id: str, key: bytes, token_id: str) -> dict[str, str]:
    """
    Fetch and decrypt the vault index from HFS.
    Validates JSON structure and emits VAULT_INDEX_ACCESSED to HCS.
    """
    aad = _make_index_aad(token_id)
    raw = load_context(key, index_file_id, token_id, aad)

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"[integrity:vault_index] Index corrupt or tampered: {e}")

    log_event(
        event_type="VAULT_INDEX_ACCESSED",
        payload={
            "token_id": token_id,
            "index_file_id": index_file_id,
            "sections": list(parsed.keys()),
        },
    )

    return parsed


# ---------------------------------------------------------------------------
# Local index cache
# ---------------------------------------------------------------------------

def load_local_index() -> dict:
    """
    Load the local .vault_index.json cache, or return empty dict.

    Verifies the _integrity hash before returning data. If the hash is
    missing (legacy cache) the file is accepted but flagged. If the hash
    is present and wrong, raises ValueError.
    """
    if not VAULT_INDEX_CACHE.exists():
        return {}

    with open(VAULT_INDEX_CACHE, encoding="utf-8") as f:
        cache_data = json.load(f)

    stored_hash = cache_data.pop("_integrity", None)
    if stored_hash is not None:
        canonical = json.dumps(cache_data, sort_keys=True, separators=(",", ":"))
        computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if computed != stored_hash:
            raise ValueError(
                "[integrity:cache] Local vault index has been tampered with — "
                "hash mismatch. Run vault_push.py --force-new to rebuild from HFS."
            )

    return cache_data


def save_local_index(data: dict) -> None:
    """
    Write the local .vault_index.json cache with an integrity hash.
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    integrity_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    cache_with_hash = {**data, "_integrity": integrity_hash}

    with open(VAULT_INDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache_with_hash, f, indent=2)
    print(f" Local index cache updated: {VAULT_INDEX_CACHE}")


# ---------------------------------------------------------------------------
# High-level: push_all / pull_all
# ---------------------------------------------------------------------------

def push_all(force_new: bool = False) -> dict[str, str]:
    """
    Push all vault sections and directory bundles to HFS, then register the index.

    Phase 1 — Identity sections (section_key): soul, user, symbiote, session_state
    Phase 2 — Directory bundles (section_key, dir: prefix)
    Index (index_key): Encrypted JSON mapping all section names to HFS file IDs.
    """
    token_id = CONTEXT_TOKEN_ID
    print(f"\n[vault] Deriving purpose-separated keys for context token {token_id}...")
    section_key = get_section_key(token_id)
    index_key = get_index_key(token_id)

    existing = {} if force_new else load_local_index()
    existing_section_ids: dict[str, str] = existing.get("sections", {})
    stored_hashes: dict[str, str] = existing.get("section_hashes", {})
    existing_dir_ids: dict[str, str] = existing.get("dir_sections", {})
    stored_dir_hashes: dict[str, str] = existing.get("dir_section_hashes", {})

    # -------------------------------------------------------------------
    # Phase 1: identity sections
    # -------------------------------------------------------------------
    print(f"\n[vault] Pushing {len(VAULT_SECTIONS)} identity sections (section_key)...")
    section_file_ids: dict[str, str] = {}
    current_hashes: dict[str, str] = {}
    sections_changed = False

    for section_name, rel_path in VAULT_SECTIONS.items():
        local_path = VAULT_ROOT / rel_path
        if not local_path.exists():
            print(f" WARN: {local_path} not found — skipping '{section_name}'")
            continue

        content = local_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        current_hashes[section_name] = content_hash

        existing_file_id = existing_section_ids.get(section_name) if not force_new else None

        if not force_new and existing_file_id and stored_hashes.get(section_name) == content_hash:
            print(f" [{section_name}] unchanged — skipping upload")
            section_file_ids[section_name] = existing_file_id
            continue

        print(f" [{section_name}] {local_path.name} ({len(content)} bytes)")
        sections_changed = True
        file_id = push_section(section_name, content, section_key, token_id, existing_file_id)
        section_file_ids[section_name] = file_id

    # -------------------------------------------------------------------
    # Phase 2: directory bundles
    # -------------------------------------------------------------------
    print(f"\n[vault] Pushing {len(VAULT_DIRS)} directory bundles (section_key)...")
    dir_file_ids: dict[str, str] = {}
    current_dir_hashes: dict[str, str] = {}
    dirs_changed = False

    for dir_name, rel_dir in VAULT_DIRS.items():
        dir_path = VAULT_ROOT / rel_dir
        if not dir_path.is_dir():
            print(f" WARN: {dir_path} not found — skipping '{dir_name}'")
            continue

        options = VAULT_DIR_OPTIONS.get(dir_name, {})
        recursive = options.get("recursive", True)

        bundle = bundle_directory(dir_path, recursive=recursive)
        bundle_hash = hashlib.sha256(bundle).hexdigest()
        current_dir_hashes[dir_name] = bundle_hash

        existing_file_id = existing_dir_ids.get(dir_name) if not force_new else None

        if not force_new and existing_file_id and stored_dir_hashes.get(dir_name) == bundle_hash:
            print(f" [{dir_name}] unchanged — skipping upload")
            dir_file_ids[dir_name] = existing_file_id
            continue

        manifest = json.loads(bundle.decode("utf-8"))
        print(f" [{dir_name}] {len(manifest)} files ({len(bundle):,} bytes uncompressed)")
        dirs_changed = True
        file_id = push_dir_section(
            dir_name, dir_path, section_key, token_id, existing_file_id, recursive=recursive
        )
        dir_file_ids[dir_name] = file_id

    # -------------------------------------------------------------------
    # Vault index — all sections + dir bundles in one encrypted JSON
    # -------------------------------------------------------------------
    all_section_ids = {**section_file_ids, **dir_file_ids}
    any_changed = sections_changed or dirs_changed

    print(f"\n[vault] Pushing vault index (index_key)...")
    existing_index_file_id = existing.get("index_file_id") if not force_new else None

    if not any_changed and existing_index_file_id:
        print(f" Nothing changed — reusing index {existing_index_file_id}")
        index_file_id = existing_index_file_id
    elif existing_index_file_id and not force_new:
        index_payload = {**all_section_ids, "_section_hashes": current_hashes}
        index_bytes = json.dumps(index_payload, indent=2).encode("utf-8")
        update_context(
            index_key, existing_index_file_id, index_bytes, token_id, _make_index_aad(token_id)
        )
        index_file_id = existing_index_file_id
        print(f" Vault index updated -> {index_file_id}")
    else:
        index_file_id = push_index(
            all_section_ids, index_key, token_id, section_hashes=current_hashes
        )
        contract_id = get_validator_contract_id()
        if contract_id:
            token_evm = token_id_to_evm_address(token_id)
            registered = get_registered_file_id(contract_id, token_evm, CONTEXT_TOKEN_SERIAL)
            if registered != index_file_id:
                print(f"\n[vault] Registering index in contract {contract_id}...")
                register_file(contract_id, token_evm, CONTEXT_TOKEN_SERIAL, index_file_id)
            else:
                print(f"\n[vault] Index already registered in contract ({index_file_id})")
        else:
            print("\n[vault] No VALIDATOR_CONTRACT_ID set — skipping contract registration.")

    cache_data = {
        "token_id": token_id,
        "serial": CONTEXT_TOKEN_SERIAL,
        "index_file_id": index_file_id,
        "sections": section_file_ids,
        "section_hashes": current_hashes,
        "dir_sections": dir_file_ids,
        "dir_section_hashes": current_dir_hashes,
    }
    save_local_index(cache_data)

    log_event(
        event_type="VAULT_PUSHED",
        payload={
            "token_id": token_id,
            "index_file_id": index_file_id,
            "sections": list(section_file_ids.keys()),
            "dir_sections": list(dir_file_ids.keys()),
        },
    )

    print(f"\n[vault] Push complete.")
    print(f" Index file: {index_file_id}")
    print(f" Identity: {list(section_file_ids.keys())}")
    print(f" Dir bundles: {list(dir_file_ids.keys())}")
    return {**section_file_ids, **dir_file_ids, "index": index_file_id}


def _pull_section_task(args: tuple) -> tuple[str, bytes]:
    """
    Worker for parallel section fetch in pull_all().
    Each call creates its own Hedera client — thread-safe.

    Routing:
    - Identity sections (soul, user, etc.) → pull_section() — AAD: "section:{name}:{token}"
    - Dir bundle sections (dir:*) → load_context() direct — AAD: "dir:{name}:{token}"
    """
    section_name, file_id, section_key, token_id = args
    if section_name.startswith("dir:"):
        aad = f"dir:{section_name}:{token_id}".encode("utf-8")
        raw = load_context(section_key, file_id, token_id, aad)
        content = decompress(raw)
    else:
        content = pull_section(file_id, section_key, token_id, section_name=section_name)
    return section_name, content


def pull_all(output_dir: Path | None = None) -> dict[str, bytes]:
    """
    Pull, verify, and decrypt all vault sections from HFS.

    Each section is individually integrity-verified (injection scan).
    Individual VAULT_SECTION_ACCESSED events emitted to HCS per section.
    """
    token_id = CONTEXT_TOKEN_ID
    print(f"\n[vault] Deriving purpose-separated keys for context token {token_id}...")
    section_key = get_section_key(token_id)
    index_key = get_index_key(token_id)

    local = load_local_index()
    index_file_id = local.get("index_file_id")

    if not index_file_id:
        print("[vault] No local cache — fetching index file_id from contract...")
        contract_id = get_validator_contract_id()
        token_evm = token_id_to_evm_address(token_id)
        index_file_id = get_registered_file_id(contract_id, token_evm, CONTEXT_TOKEN_SERIAL)
        if not index_file_id:
            raise RuntimeError("No vault index registered in contract. Run vault_push first.")

    print(f"[vault] Fetching vault index from HFS: {index_file_id}")
    section_ids = pull_index(index_file_id, index_key, token_id)
    print(f" Sections found: {list(section_ids.keys())}")

    _META_KEYS = {"packages", "_section_hashes"}
    tasks = [
        (name, fid, section_key, token_id)
        for name, fid in section_ids.items()
        if name not in _META_KEYS and isinstance(fid, str)
    ]
    print(f" Fetching {len(tasks)} sections in parallel...")

    results: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(_pull_section_task, task): task[0] for task in tasks}
        for future in as_completed(futures):
            section_name, content = future.result()
            results[section_name] = content
            print(f" Pulled '{section_name}': {len(content)} bytes -- verified")

    if output_dir:
        for section_name, content in results.items():
            out_path = output_dir / f"{section_name}.md"
            out_path.write_bytes(content)
            print(f" Written: {out_path}")

    log_event(
        event_type="VAULT_PULLED",
        payload={
            "token_id": token_id,
            "index_file_id": index_file_id,
            "sections": list(results.keys()),
        },
    )

    print(f"\n[vault] Pull complete. {len(results)} sections loaded.")
    return results
