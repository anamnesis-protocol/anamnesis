"""
Tests for context_storage.py — HFS operations.

Network tests are skipped when HEDERA_NETWORK is not set or is "mock".
Crypto layer tests run without network access.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from src.crypto import derive_key, encrypt_context, decrypt_context

TOKEN_ID = "0.0.67890"
WALLET_SIG = b"\xde\xad\xbe\xef" * 16
SAMPLE_CONTEXT = b'{"session": "test", "memory": ["item1", "item2"]}'


class TestCryptoLayerOnly:
    """Verify encrypt/decrypt roundtrip that underpins context_storage — no network."""

    def test_context_survives_encrypt_decrypt(self):
        key = derive_key(TOKEN_ID, WALLET_SIG)
        ciphertext = encrypt_context(key, SAMPLE_CONTEXT)
        assert decrypt_context(key, ciphertext) == SAMPLE_CONTEXT

    def test_chunking_logic(self):
        """Verify that content larger than _CHUNK_SIZE would be split correctly."""
        from src.context_storage import _CHUNK_SIZE

        key = derive_key(TOKEN_ID, WALLET_SIG)
        large_content = b"A" * (_CHUNK_SIZE * 3 + 100)
        ciphertext = encrypt_context(key, large_content)

        chunks = []
        for i in range(0, len(ciphertext), _CHUNK_SIZE):
            chunks.append(ciphertext[i : i + _CHUNK_SIZE])

        # Reassemble
        reassembled = b"".join(chunks)
        assert reassembled == ciphertext
        assert decrypt_context(key, reassembled) == large_content


@pytest.mark.skipif(
    os.getenv("HEDERA_NETWORK", "mock") == "mock",
    reason="Requires live Hedera testnet credentials in .env",
)
class TestContextStorageNetwork:
    """Integration tests — require HEDERA_NETWORK=testnet and valid .env."""

    def test_store_and_load_roundtrip(self):
        from src.context_storage import store_context, load_context

        key = derive_key(TOKEN_ID, WALLET_SIG)
        file_id = store_context(key, SAMPLE_CONTEXT, token_id=TOKEN_ID)
        assert file_id.startswith("0.0.")

        loaded = load_context(key, file_id, token_id=TOKEN_ID)
        assert loaded == SAMPLE_CONTEXT

    def test_get_file_info(self):
        from src.context_storage import store_context, get_file_info

        key = derive_key(TOKEN_ID, WALLET_SIG)
        file_id = store_context(key, SAMPLE_CONTEXT)

        info = get_file_info(file_id)
        assert info["file_id"] == file_id
        assert info["size_bytes"] > 0
        assert not info["is_deleted"]
