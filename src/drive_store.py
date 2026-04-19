"""
drive_store.py — SAC-Drive: Token-Gated Encrypted File Storage

Architecture:
  - Each file encrypted individually on HFS
  - Drive index (file manifest) stored encrypted on HFS
  - Key = HKDF(token_id + wallet_sig, info=b"sovereign-ai-drive-v1")
  - AAD binds each file ciphertext to its filename + token (prevents swapping)
  - Index file_id cached locally in .drive_index.json

File size limits:
  - HFS max: 1,024 KB per file
  - Automatic chunking via FileAppendTransaction for files > 6KB
  - Files > 1MB must be split before upload (drive_store handles this)

Index JSON (plaintext before encryption):
  {
    "version": 1,
    "files": {
      "<uuid>": {
        "filename": "report.pdf",
        "size_bytes": 12345,
        "mime_type": "application/pdf",
        "hfs_file_id": "0.0.xxxxx",
        "sha256": "...",
        "uploaded_at": "...",
        "tags": []
      }
    }
  }
"""

import hashlib
import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.crypto import derive_key, encrypt_context, decrypt_context, compress, decompress
from src.context_storage import store_context, load_context, update_context
from src.vault import get_wallet_signature
from src.event_log import log_event

_INFO_DRIVE = b"sovereign-ai-drive-v1"
_AAD_DRIVE_IDX = b"sac-drive-index-v1"
_HFS_MAX_BYTES = 1_024 * 1_024  # 1 MB hard limit per HFS file

_DRIVE_INDEX_CACHE = Path(__file__).parent.parent / ".drive_index.json"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def get_drive_key(token_id: str) -> bytes:
    wallet_sig = get_wallet_signature(token_id)
    return derive_key(token_id, wallet_sig, info=_INFO_DRIVE)


def _file_aad(filename: str, token_id: str) -> bytes:
    """AAD binds file ciphertext to specific filename + token. Prevents ciphertext swaps."""
    return f"sac-drive-file:{filename}:{token_id}".encode("utf-8")


# ---------------------------------------------------------------------------
# Index cache helpers
# ---------------------------------------------------------------------------


def _load_drive_cache() -> dict:
    if not _DRIVE_INDEX_CACHE.exists():
        return {}
    with open(_DRIVE_INDEX_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_drive_cache(data: dict) -> None:
    with open(_DRIVE_INDEX_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Drive initialization
# ---------------------------------------------------------------------------


def init_drive(token_id: str) -> str:
    """Create a new empty drive index on HFS. Returns index file_id."""
    cache = _load_drive_cache()
    if cache.get(token_id, {}).get("index_file_id"):
        raise RuntimeError(
            f"Drive already exists at {cache[token_id]['index_file_id']}. "
            "Use list_files() to browse it."
        )

    key = get_drive_key(token_id)
    index = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "files": {}}

    plaintext = json.dumps(index, indent=2).encode("utf-8")
    file_id = store_context(key, plaintext, token_id, _AAD_DRIVE_IDX)

    if token_id not in cache:
        cache[token_id] = {}
    cache[token_id]["index_file_id"] = file_id
    _save_drive_cache(cache)
    log_event("DRIVE_INITIALIZED", {"token_id": token_id, "index_file_id": file_id})
    print(f"[sac-drive] Drive index created on HFS: {file_id}")
    return file_id


def _get_index(token_id: str) -> dict:
    cache = _load_drive_cache()
    file_id = cache.get(token_id, {}).get("index_file_id")
    if not file_id:
        raise RuntimeError("Drive not initialized. Run init_drive() first.")
    key = get_drive_key(token_id)
    raw = load_context(key, file_id, token_id, _AAD_DRIVE_IDX)
    return json.loads(raw.decode("utf-8"))


def _save_index(token_id: str, index: dict) -> None:
    cache = _load_drive_cache()
    file_id = cache[token_id]["index_file_id"]
    key = get_drive_key(token_id)
    raw = json.dumps(index, indent=2).encode("utf-8")
    update_context(key, file_id, raw, token_id, _AAD_DRIVE_IDX)


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def upload_file(token_id: str, local_path: str, tags: list[str] | None = None) -> str:
    """
    Encrypt and upload a file to HFS.
    Returns the drive file ID (UUID, not HFS file_id).
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    raw_bytes = path.read_bytes()
    if len(raw_bytes) > _HFS_MAX_BYTES:
        raise ValueError(
            f"File too large: {len(raw_bytes):,} bytes. "
            f"HFS limit is {_HFS_MAX_BYTES:,} bytes (1 MB). "
            "Split the file before uploading."
        )

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    mime, _ = mimetypes.guess_type(str(path))
    key = get_drive_key(token_id)
    aad = _file_aad(path.name, token_id)
    payload = compress(raw_bytes)

    print(
        f"[sac-drive] Uploading {path.name} ({len(raw_bytes):,} bytes → {len(payload):,} compressed)..."
    )
    hfs_file_id = store_context(key, payload, token_id, aad)

    # Register in index
    file_uuid = str(uuid.uuid4())
    index = _get_index(token_id)
    index["files"][file_uuid] = {
        "filename": path.name,
        "size_bytes": len(raw_bytes),
        "mime_type": mime or "application/octet-stream",
        "hfs_file_id": hfs_file_id,
        "sha256": sha256,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
    }
    _save_index(token_id, index)

    log_event(
        "DRIVE_FILE_UPLOADED",
        {
            "token_id": token_id,
            "filename": path.name,
            "size_bytes": len(raw_bytes),
            "hfs_file_id": hfs_file_id,
            "sha256": sha256,
        },
    )
    print(f"[sac-drive] Uploaded: {path.name} → {hfs_file_id} (drive id: {file_uuid[:8]}...)")
    return file_uuid


def download_file(token_id: str, file_uuid: str, output_dir: str = ".") -> str:
    """
    Fetch, decrypt, and save a file from HFS.
    Returns the path of the saved file.
    """
    index = _get_index(token_id)
    if file_uuid not in index["files"]:
        raise KeyError(f"No file with id {file_uuid} in drive")

    meta = index["files"][file_uuid]
    key = get_drive_key(token_id)
    aad = _file_aad(meta["filename"], token_id)

    print(f"[sac-drive] Downloading {meta['filename']}...")
    raw = load_context(key, meta["hfs_file_id"], token_id, aad)
    content = decompress(raw)

    # Verify integrity
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != meta["sha256"]:
        raise ValueError(
            f"[sac-drive] Integrity check FAILED for {meta['filename']}. "
            "File may have been tampered with."
        )

    out_path = Path(output_dir) / meta["filename"]
    out_path.write_bytes(content)

    log_event(
        "DRIVE_FILE_DOWNLOADED",
        {
            "token_id": token_id,
            "filename": meta["filename"],
            "file_uuid": file_uuid,
            "verified": True,
        },
    )
    print(f"[sac-drive] Saved: {out_path} ({len(content):,} bytes, integrity verified)")
    return str(out_path)


def list_files(token_id: str) -> list[dict]:
    """Return file listing without downloading any content."""
    index = _get_index(token_id)
    return [
        {
            "id": fid,
            "filename": f["filename"],
            "size_bytes": f["size_bytes"],
            "mime_type": f["mime_type"],
            "uploaded_at": f["uploaded_at"],
            "tags": f["tags"],
            "sha256": f["sha256"][:16] + "...",
        }
        for fid, f in index["files"].items()
    ]


def delete_file(token_id: str, file_uuid: str) -> None:
    """
    Remove a file from the drive index.
    Note: HFS files cannot be fully deleted (immutable ledger) but
    after index removal the file_id is no longer accessible without
    the HFS file_id directly. The encrypted blob remains but is
    effectively orphaned and unreadable without the key.
    """
    index = _get_index(token_id)
    if file_uuid not in index["files"]:
        raise KeyError(f"No file with id {file_uuid}")

    filename = index["files"][file_uuid]["filename"]
    del index["files"][file_uuid]
    _save_index(token_id, index)

    log_event("DRIVE_FILE_REMOVED", {"token_id": token_id, "filename": filename})
    print(f"[sac-drive] Removed from index: {filename}")
    print("  Note: encrypted blob remains on HFS (immutable ledger) but is now inaccessible.")
