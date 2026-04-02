"""
crypto.py — Key Derivation and Context Encryption

Implements :
KDF(context_token_id + wallet_signature) -> decryption_key

Design decisions:
- KDF: HKDF-SHA256 (RFC 5869). Deterministic. No stored state.
- Inputs: context_token_id (bytes) + wallet_signature (bytes from signing a challenge)
- Salt: SHA256(token_id) — token-specific, public, reproducible
- Info: b"sovereign-ai-context-v1" — domain separation
- Output: 32 bytes -> AES-256-GCM key
- Encryption: AES-256-GCM (authenticated, nonce included in ciphertext blob)
- Nonce: 12 random bytes prepended to ciphertext

The decryption key is NEVER stored anywhere. It is derived on-demand from
the wallet signature and the token ID, then discarded after decryption.

Usage:
from src.crypto import derive_key, encrypt_context, decrypt_context

# Wallet signs a challenge to prove ownership
challenge = b"sovereign-ai-context-challenge-" + token_id.encode()
wallet_sig = wallet.sign(challenge) # off-chain, wallet-specific

key = derive_key(token_id="0.0.67890", wallet_signature=wallet_sig)
ciphertext = encrypt_context(key, plaintext_context)
plaintext = decrypt_context(key, ciphertext)
"""

import gzip
import os
import hashlib

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Domain separator — update version string if algorithm changes
_HKDF_INFO = b"sovereign-ai-context-v1"
_NONCE_LEN = 12 # 96-bit GCM nonce
_TAG_LEN = 16 # 128-bit GCM auth tag (cryptography default)

# Compression magic: gzip header bytes — used to detect compressed plaintext on pull
_GZIP_MAGIC = b"\x1f\x8b"


def compress(data: bytes, level: int = 6) -> bytes:
"""
Gzip-compress bytes before encryption.

Compression happens before encryption so ciphertext size benefits.
Level 6 balances speed and ratio (same as gzip default).
Text markdown compresses ~60-70%.

Args:
data: Raw plaintext bytes
level: Compression level 1-9 (1=fast, 9=best, 6=default)

Returns:
Compressed bytes (starts with gzip magic \x1f\x8b)
"""
return gzip.compress(data, compresslevel=level)


def decompress(data: bytes) -> bytes:
"""
Decompress bytes after decryption.

Safe to call on already-decompressed data: if data does not start with
gzip magic bytes, returns data unchanged (backward-compatible with
uncompressed HFS files created before compression was added).

Args:
data: Bytes from decrypt_context() — may or may not be compressed

Returns:
Decompressed plaintext bytes
"""
    if data[:2] == _GZIP_MAGIC:
        return gzip.decompress(data)
    return data # Not compressed — pass through (backward compat)


def derive_key(token_id: str, wallet_signature: bytes, info: bytes | None = None) -> bytes:
"""
Derive the 32-byte AES-256 context key from token ID + wallet signature.

This is the core of . The key is deterministic given the
same inputs, but reveals nothing about the token ID or signature to a
party who does not hold the wallet.

Args:
token_id: Context token ID string (e.g. "0.0.67890")
wallet_signature: Raw bytes of the wallet's signature over a known challenge
info: Optional HKDF domain separation label. Defaults to
b"sovereign-ai-context-v1" (the original patent claim KDF).
Pass a different value for purpose-separated key derivation
(e.g. b"sovereign-ai-index-v1", b"sovereign-ai-package-v1").

Returns:
32-byte key (never store this)
"""
token_id_bytes = token_id.encode("utf-8")

# Salt = SHA256(token_id) — token-specific, reproducible, public
salt = hashlib.sha256(token_id_bytes).digest()

# IKM = token_id_bytes || wallet_signature (concatenation)
ikm = token_id_bytes + wallet_signature

key = HKDF(
algorithm=SHA256(),
length=32,
salt=salt,
info=info if info is not None else _HKDF_INFO,
).derive(ikm)

return key


def encrypt_context(key: bytes, plaintext: bytes, aad: bytes | None = None) -> bytes:
"""
Encrypt context data with AES-256-GCM.

Output format: nonce (12 bytes) || ciphertext+tag

Args:
key: 32-byte key from derive_key()
plaintext: Raw context bytes (JSON, markdown, etc.)
aad: Optional associated data (authenticated but not encrypted).
Binds the ciphertext to its logical purpose/location.
Decryption with wrong AAD raises InvalidTag.
Recommended format: b"section:{name}:{token_id}" etc.

Returns:
Ciphertext blob (nonce prepended) safe to store on HFS
"""
nonce = os.urandom(_NONCE_LEN)
aesgcm = AESGCM(key)
ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=aad)
return nonce + ciphertext


def decrypt_context(key: bytes, blob: bytes, aad: bytes | None = None) -> bytes:
"""
Decrypt a context blob produced by encrypt_context().

Args:
key: 32-byte key from derive_key()
blob: Ciphertext blob (nonce prepended)
aad: Associated data used during encryption — must match exactly.
If wrong or missing when original used AAD, raises InvalidTag.

Returns:
Original plaintext bytes

Raises:
cryptography.exceptions.InvalidTag if key is wrong, data is tampered,
or aad does not match what was used during encryption.
"""
nonce = blob[:_NONCE_LEN]
ciphertext = blob[_NONCE_LEN:]
aesgcm = AESGCM(key)
return aesgcm.decrypt(nonce, ciphertext, associated_data=aad)


def make_challenge(token_id: str) -> bytes:
"""
Produce a deterministic signing challenge for a given token.
The wallet signs this to prove ownership without revealing the private key.

Args:
token_id: Context token ID string

Returns:
Challenge bytes the wallet should sign
"""
return b"sovereign-ai-context-challenge-" + token_id.encode("utf-8")
