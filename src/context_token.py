"""
context_token.py — HTS NFT Context Token

Creates the sovereign AI context context token as a Hedera Token Service NFT.

Key design decisions (per ):
- Admin key: REMOVED at mint (no one can modify the token definition post-creation)
- Supply key: REMOVED at mint (no additional NFTs can ever be minted)
- Token memo: records the HFS file_id for the associated encrypted context
- Token ID becomes one of the two KDF inputs: KDF(token_id + wallet_signature)
- One NFT per AI companion identity — non-fungible by design

Usage:
 from src.context_token import mint_context_token, get_context_token_info

 token_id = mint_context_token(context_file_id="0.0.12345")
 info = get_context_token_info(token_id)
"""

import json
from hiero_sdk_python import (
 TokenCreateTransaction,
 TokenMintTransaction,
 TokenType,
 SupplyType,
 TokenInfoQuery,
 TokenNftInfoQuery,
 TokenId,
 NftId,
 Hbar,
)
from src.config import get_client, get_treasury
from src.event_log import log_event


def mint_context_token(
 context_file_id: str,
 companion_name: str = "Symbiote",
) -> str:
 """
 Mint a single immutable HTS NFT context token.

 The token is created with NO admin key and NO supply key — once created,
 its definition cannot be changed and no additional NFTs can be minted.
 This enforces the sovereign ownership guarantee in the patent.

 Args:
 context_file_id: HFS file ID (e.g. "0.0.12345") of the encrypted context
 companion_name: Human-readable companion label for the token name

 Returns:
 token_id as string (e.g. "0.0.67890")
 """
 client = get_client()
 treasury_id, treasury_key = get_treasury()

 # Step 1: Create the token type (NFT, no admin/supply keys)
 metadata = json.dumps({
 "type": "sovereign-ai-context",
 "version": "1.0",
 "context_file": context_file_id,
 "companion": companion_name,
 }).encode("utf-8")

 create_tx = (
 TokenCreateTransaction()
 .set_token_name(f"SovereignContext-{companion_name}")
 .set_token_symbol("SAC")
 .set_token_type(TokenType.NON_FUNGIBLE_UNIQUE)
 .set_supply_type(SupplyType.FINITE)
 .set_max_supply(1)
 .set_initial_supply(0)
 .set_treasury_account_id(treasury_id)
 .set_supply_key(treasury_key.public_key())
 # Intentionally no admin key — immutable post-creation
 .set_memo(f"sovereign-ai-context|{context_file_id}")
 .freeze_with(client)
 .sign(treasury_key)
 )

 create_receipt = create_tx.execute(client)
 token_id_obj = create_receipt.token_id
 token_id = str(token_id_obj)

 # Step 2: Mint the single NFT (serial 1)
 mint_tx = (
 TokenMintTransaction()
 .set_token_id(token_id_obj)
 .set_metadata([metadata])
 .freeze_with(client)
 .sign(treasury_key)
 )

 mint_tx.execute(client)
 serial = 1 # max_supply=1, first mint is always serial 1

 # Step 3: Log creation to HCS audit trail
 log_event(
 event_type="context_token_MINTED",
 payload={
 "token_id": token_id,
 "serial": int(serial),
 "context_file_id": context_file_id,
 "companion": companion_name,
 },
 )

 return token_id


def get_context_token_info(token_id: str) -> dict:
 """
 Fetch on-chain token definition info.

 Returns:
 dict with token name, symbol, memo, total supply, treasury, etc.
 """
 client = get_client()

 info = (
 TokenInfoQuery()
 .set_token_id(TokenId.from_string(token_id))
 .execute(client)
 )
 return {
 "token_id": token_id,
 "name": info.name,
 "symbol": info.symbol,
 "memo": info.memo,
 "total_supply": int(info.total_supply),
 "max_supply": int(info.max_supply),
 "treasury": str(info.treasury),
 "admin_key": str(info.admin_key) if info.admin_key else None,
 "supply_key": str(info.supply_key) if info.supply_key else None,
 }


def get_nft_metadata(token_id: str, serial: int = 1) -> dict:
 """
 Fetch the metadata stored in the minted NFT (serial 1).

 Returns:
 Parsed metadata dict including context_file HFS ID.
 """
 client = get_client()
 nft_id = NftId(TokenId.from_string(token_id), serial)

 nft_info = (
 TokenNftInfoQuery()
 .set_nft_id(nft_id)
 .execute(client)
 )

 raw_meta = bytes(nft_info.metadata).decode("utf-8")
 return json.loads(raw_meta)
