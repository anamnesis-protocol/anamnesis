"""
context_storage.py — HFS Encrypted Context Storage

Stores and retrieves AI companion context on Hedera File Service.
Context is encrypted before upload — only the context token owner can decrypt it.

HFS limits:
- Max file size: 1024 KB
- Max per-transaction content: 6 KB (FileCreateTransaction)
- Larger content: FileCreateTransaction (first chunk) + FileAppendTransaction (subsequent)
- FileId is immutable reference — share it in the NFT metadata

Flow (store):
 plaintext_context -> encrypt(key) -> split into chunks -> HFS

Flow (load):
 HFS file_id -> read ciphertext -> derive_key(token_id, wallet_sig) -> decrypt -> context

Usage:
 from src.context_storage import store_context, load_context

 file_id = store_context(key, context_bytes)
 context = load_context(key, file_id)
"""

import re

from hiero_sdk_python import (
 FileCreateTransaction,
 FileAppendTransaction,
 FileUpdateTransaction,
 FileContentsQuery,
 FileInfoQuery,
 Hbar,
)
from hiero_sdk_python.file.file_id import FileId
from src.config import get_client, get_treasury
from src.crypto import encrypt_context, decrypt_context
from src.event_log import log_event

# HFS per-transaction byte limit (safe margin under 6 KB)
_CHUNK_SIZE = 4096

# Hedera ID format: shard.realm.num (e.g. "0.0.8252159")
_HEDERA_ID_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _validate_file_id(file_id: str) -> None:
    """Reject malformed file_id strings before they reach the Hedera SDK."""
    if not file_id or not _HEDERA_ID_RE.match(file_id):
        raise ValueError(
            f"[context_storage] Invalid file_id: {file_id!r}. "
            "Expected Hedera ID format '0.0.XXXXX'."
        )


def store_context(key: bytes, plaintext: bytes, token_id: str = "", aad: bytes | None = None) -> str:
    """
    Encrypt context and store it on Hedera File Service.

    Uses FileCreateTransaction for the first chunk, then FileAppendTransaction
    for any remaining chunks (handles context > 4 KB transparently).

    Args:
        key: 32-byte AES-256 key from crypto.derive_key()
        plaintext: Raw context bytes to store
        token_id: Context token ID — used for HCS audit log only
        aad: Optional associated data for AES-GCM authentication.
            Binds ciphertext to its logical purpose (section, index, package).
            Must pass the same value to load_context() for decryption.

    Returns:
        file_id as string (e.g. "0.0.22222") — store this in the NFT metadata
    """
    client = get_client()
    _, treasury_key = get_treasury()

    ciphertext = encrypt_context(key, plaintext, aad)

    # File key controls future updates — treasury key for PoC
    file_key = treasury_key

    # Create with first chunk
    first_chunk = ciphertext[:_CHUNK_SIZE]
    remaining = ciphertext[_CHUNK_SIZE:]

    create_tx = (
        FileCreateTransaction()
        .set_keys([file_key.public_key()])
        .set_contents(first_chunk)
        .freeze_with(client)
        .sign(file_key)
    )

    create_receipt = create_tx.execute(client)
    file_id = create_receipt.file_id

    # Append remaining chunks
    offset = 0
    while offset < len(remaining):
        chunk = remaining[offset: offset + _CHUNK_SIZE]
        (
            FileAppendTransaction()
            .set_file_id(file_id)
            .set_contents(chunk)
            .freeze_with(client)
            .sign(file_key)
            .execute(client)
        )
        offset += _CHUNK_SIZE

    file_id_str = str(file_id)

    log_event(
        event_type="CONTEXT_STORED",
        payload={
            "file_id": file_id_str,
            "token_id": token_id,
            "plaintext_size_bytes": len(plaintext),
            "ciphertext_size_bytes": len(ciphertext),
        },
    )

    return file_id_str


def load_context(key: bytes, file_id: str, token_id: str = "", aad: bytes | None = None) -> bytes:
    """
    Read encrypted context from HFS and decrypt it.

    Args:
        key: 32-byte AES-256 key from crypto.derive_key()
        file_id: HFS file ID string (e.g. "0.0.22222")
        token_id: Context token ID — used for HCS audit log only
        aad: Associated data that was used during encryption.
            Must match exactly — wrong AAD raises InvalidTag.

    Returns:
        Decrypted plaintext bytes

    Raises:
        ValueError: if file_id format is invalid
        cryptography.exceptions.InvalidTag if key is wrong, file is tampered,
        or aad does not match encryption-time value
    """
    _validate_file_id(file_id)
    client = get_client()

    ciphertext = (
        FileContentsQuery()
        .set_file_id(FileId.from_string(file_id))
        .execute(client)
    )

    plaintext = decrypt_context(key, bytes(ciphertext), aad)

    log_event(
        event_type="CONTEXT_LOADED",
        payload={
            "file_id": file_id,
            "token_id": token_id,
            "plaintext_size_bytes": len(plaintext),
        },
    )

    return plaintext


def update_context(key: bytes, file_id: str, new_plaintext: bytes, token_id: str = "", aad: bytes | None = None) -> None:
    """
    Replace the encrypted context for an existing HFS file.

    Uses FileUpdateTransaction for the first chunk, then FileAppendTransaction
    for any remaining chunks (handles content > 4 KB transparently).
    This mirrors the store_context() chunking pattern to avoid TRANSACTION_OVERSIZE
    errors on large bundles.

    Args:
        key: 32-byte AES-256 key (new key if rotating, same key if not)
        file_id: HFS file ID to update
        new_plaintext: New context bytes to encrypt and store
        token_id: For audit log
        aad: Associated data for AES-GCM — must match load_context() call.
    """
    _validate_file_id(file_id)
    client = get_client()
    _, treasury_key = get_treasury()

    new_ciphertext = encrypt_context(key, new_plaintext, aad)

    # FileUpdateTransaction replaces file contents — send first chunk only
    first_chunk = new_ciphertext[:_CHUNK_SIZE]
    remaining = new_ciphertext[_CHUNK_SIZE:]

    (
        FileUpdateTransaction()
        .set_file_id(FileId.from_string(file_id))
        .set_contents(first_chunk)
        .freeze_with(client)
        .sign(treasury_key)
        .execute(client)
    )

    # Append remaining chunks (same pattern as store_context)
    offset = 0
    while offset < len(remaining):
        chunk = remaining[offset: offset + _CHUNK_SIZE]
        (
            FileAppendTransaction()
            .set_file_id(FileId.from_string(file_id))
            .set_contents(chunk)
            .freeze_with(client)
            .sign(treasury_key)
            .execute(client)
        )
        offset += _CHUNK_SIZE

    log_event(
        event_type="CONTEXT_UPDATED",
        payload={
            "file_id": file_id,
            "token_id": token_id,
            "new_size_bytes": len(new_ciphertext),
        },
    )


def get_file_info(file_id: str) -> dict:
    """Fetch HFS file metadata (size, keys, expiration) without reading content."""
    client = get_client()

    info = (
        FileInfoQuery()
        .set_file_id(FileId.from_string(file_id))
        .execute(client)
    )

    return {
        "file_id": file_id,
        "size_bytes": int(info.size),
        "expiration_time": str(info.expiration_time),
        "is_deleted": bool(info.is_deleted),
    }
