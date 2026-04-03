"""
Tests for crypto.py — KDF and AES-256-GCM encryption.

These tests are pure Python (no Hedera network calls required).
They validate the core cryptographic claims of the patent.
"""

import pytest
from cryptography.exceptions import InvalidTag
from src.crypto import derive_key, encrypt_context, decrypt_context, make_challenge, compress, decompress


TOKEN_ID = "0.0.67890"
WALLET_SIG = b"\xde\xad\xbe\xef" * 16 # 64 bytes of fake wallet sig


class TestDeriveKey:
    def test_returns_32_bytes(self):
        key = derive_key(TOKEN_ID, WALLET_SIG)
        assert len(key) == 32

    def test_deterministic(self):
        key1 = derive_key(TOKEN_ID, WALLET_SIG)
        key2 = derive_key(TOKEN_ID, WALLET_SIG)
        assert key1 == key2

    def test_different_token_different_key(self):
        key1 = derive_key("0.0.111", WALLET_SIG)
        key2 = derive_key("0.0.222", WALLET_SIG)
        assert key1 != key2

    def test_different_sig_different_key(self):
        key1 = derive_key(TOKEN_ID, b"\x01" * 64)
        key2 = derive_key(TOKEN_ID, b"\x02" * 64)
        assert key1 != key2

    def test_key_is_bytes(self):
        key = derive_key(TOKEN_ID, WALLET_SIG)
        assert isinstance(key, bytes)


class TestEncryptDecrypt:
    def setup_method(self):
        self.key = derive_key(TOKEN_ID, WALLET_SIG)
        self.plaintext = b'{"topic": "test context", "data": "some AI conversation state"}'

    def test_roundtrip(self):
        ciphertext = encrypt_context(self.key, self.plaintext)
        result = decrypt_context(self.key, ciphertext)
        assert result == self.plaintext

    def test_ciphertext_differs_from_plaintext(self):
        ciphertext = encrypt_context(self.key, self.plaintext)
        assert ciphertext != self.plaintext

    def test_nonce_is_random(self):
        ct1 = encrypt_context(self.key, self.plaintext)
        ct2 = encrypt_context(self.key, self.plaintext)
        # Different nonces produce different ciphertexts
        assert ct1 != ct2

    def test_wrong_key_raises(self):
        ciphertext = encrypt_context(self.key, self.plaintext)
        wrong_key = derive_key(TOKEN_ID, b"\xff" * 64)
        with pytest.raises(InvalidTag):
            decrypt_context(wrong_key, ciphertext)

    def test_tampered_ciphertext_raises(self):
        ciphertext = bytearray(encrypt_context(self.key, self.plaintext))
        ciphertext[-1] ^= 0xFF # flip last byte
        with pytest.raises(InvalidTag):
            decrypt_context(self.key, bytes(ciphertext))

    def test_large_context(self):
        large_plaintext = b"x" * 100_000 # 100 KB
        ciphertext = encrypt_context(self.key, large_plaintext)
        result = decrypt_context(self.key, ciphertext)
        assert result == large_plaintext

    def test_empty_context(self):
        ciphertext = encrypt_context(self.key, b"")
        result = decrypt_context(self.key, ciphertext)
        assert result == b""


class TestMakeChallenge:
    def test_returns_bytes(self):
        challenge = make_challenge(TOKEN_ID)
        assert isinstance(challenge, bytes)

    def test_includes_token_id(self):
        challenge = make_challenge(TOKEN_ID)
        assert TOKEN_ID.encode() in challenge

    def test_different_tokens_different_challenges(self):
        c1 = make_challenge("0.0.111")
        c2 = make_challenge("0.0.222")
        assert c1 != c2

    def test_deterministic(self):
        assert make_challenge(TOKEN_ID) == make_challenge(TOKEN_ID)


class TestCompressDecompress:
    """Gzip compression helpers — used before encryption to reduce HFS payload size."""

    MARKDOWN = b"# SOUL.md\n\nMission: $200k/year.\n\n" + b"Some context. " * 200

    def test_roundtrip(self):
        compressed = compress(self.MARKDOWN)
        result = decompress(compressed)
        assert result == self.MARKDOWN

    def test_compression_reduces_size(self):
        compressed = compress(self.MARKDOWN)
        assert len(compressed) < len(self.MARKDOWN)

    def test_text_compresses_significantly(self):
        """Markdown text should compress to at least 50% of original."""
        compressed = compress(self.MARKDOWN)
        assert len(compressed) < len(self.MARKDOWN) * 0.5

    def test_decompress_backward_compat_uncompressed(self):
        """decompress() on non-gzip data returns data unchanged (backward compat)."""
        raw = b"not compressed data without gzip magic"
        assert decompress(raw) == raw

    def test_decompress_backward_compat_ciphertext(self):
        """AES-GCM output does not start with gzip magic — decompress passes through."""
        key = derive_key(TOKEN_ID, b"\xaa" * 64)
        ciphertext = encrypt_context(key, b"plaintext")
        # Nonce (12 bytes) starts the blob — almost certainly not \x1f\x8b
        assert decompress(ciphertext) == ciphertext

    def test_compress_empty_bytes(self):
        assert decompress(compress(b"")) == b""

    def test_compress_binary_data(self):
        binary = bytes(range(256)) * 10
        assert decompress(compress(binary)) == binary

    def test_encrypt_compressed_roundtrip(self):
        """Full pipeline: compress -> encrypt -> decrypt -> decompress."""
        key = derive_key(TOKEN_ID, b"\xbb" * 64)
        plaintext = self.MARKDOWN
        blob = encrypt_context(key, compress(plaintext))
        recovered = decompress(decrypt_context(key, blob))
        assert recovered == plaintext
