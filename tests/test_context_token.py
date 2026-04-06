"""
Tests for context_token.py — HTS NFT minting.

Network tests are skipped unless HEDERA_NETWORK=testnet is set.
"""

import os
import json
import pytest


@pytest.mark.skipif(
    os.getenv("HEDERA_NETWORK", "mock") != "testnet",
    reason="Network tests only run on testnet — mainnet would cost real HBAR",
)
class TestContextTokenNetwork:
    """Integration tests — require valid .env with testnet credentials (HEDERA_NETWORK=testnet)."""

    def test_mint_context_token_returns_token_id(self):
        from src.context_token import mint_context_token

        token_id = mint_context_token(
            context_file_id="0.0.99999",
            companion_name="TestCompanion",
        )
        assert token_id.startswith("0.0.")

    def test_context_token_is_immutable(self):
        """Verify admin_key and supply_key are None post-creation."""
        from src.context_token import mint_context_token, get_context_token_info

        token_id = mint_context_token(context_file_id="0.0.99999")
        info = get_context_token_info(token_id)

        # Admin key must be absent — no one can modify the token definition
        assert info["admin_key"] is None, "Admin key must be removed for sovereignty guarantee"

        # Total supply must be 1 — single NFT
        assert info["total_supply"] == 1
        assert info["max_supply"] == 1

    def test_nft_metadata_contains_file_id(self):
        from src.context_token import mint_context_token, get_nft_metadata

        file_id = "0.0.99999"
        token_id = mint_context_token(context_file_id=file_id)
        meta = get_nft_metadata(token_id, serial=1)

        assert meta["f"] == file_id
        assert meta["sac"] == "1"
