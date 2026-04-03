"""
session_memory.py — HTS Fungible Session Memory Tokens

Session memory tokens represent earned/accumulated AI session interactions.
They are HTS fungible tokens minted by the system (not freely mintable by users).

Purpose in patent (Claims 16-17):
- Procedural memory packages are represented as transferable token units
- Token balance represents the quantity of packaged memory modules
- Transfer = marketplace transaction for skill/memory modules

Flow:
 1. Create memory token type (once per companion identity)
 2. Mint N tokens when a memory package is captured
 3. Transfer tokens when packages are sold/shared (marketplace)

Usage:
 from src.session_memory import create_memory_token, mint_memory, transfer_memory

 memory_token_id = create_memory_token(companion_name="Assistant")
 mint_memory(memory_token_id, amount=1)
 transfer_memory(memory_token_id, to_account="0.0.99999", amount=1)
"""

from hiero_sdk_python import (
 TokenCreateTransaction,
 TokenMintTransaction,
 TransferTransaction,
 TokenAssociateTransaction,
 TokenType,
 SupplyType,
 TokenId,
 AccountId,
 Hbar,
)
from src.config import get_client, get_treasury
from src.event_log import log_event


def create_memory_token(companion_name: str = "Symbiote") -> str:
 """
 Create a fungible HTS token representing packaged memory modules.

 Supply key is held by the treasury (system) — users cannot self-mint.
 No admin key — token definition is immutable post-creation.

 Args:
 companion_name: Label for the token (appears in token explorer)

 Returns:
 token_id as string (e.g. "0.0.33333")
 """
 client = get_client()
 treasury_id, treasury_key = get_treasury()

 tx = (
 TokenCreateTransaction()
 .set_token_name(f"MemoryModule-{companion_name}")
 .set_token_symbol("MMEM")
 .set_token_type(TokenType.FUNGIBLE_COMMON)
 .set_supply_type(SupplyType.INFINITE)
 .set_initial_supply(0)
 .set_decimals(0)
 .set_treasury_account_id(treasury_id)
 .set_supply_key(treasury_key.public_key())
 # No admin key — immutable
 .set_memo(f"sovereign-ai-context|memory-module|{companion_name}")
 .freeze_with(client)
 .sign(treasury_key)
 )

 receipt = tx.execute(client)
 token_id = str(receipt.token_id)

 log_event(
 event_type="MEMORY_TOKEN_CREATED",
 payload={"token_id": token_id, "companion": companion_name},
 )

 return token_id


def mint_memory(token_id: str, amount: int = 1) -> None:
 """
 Mint memory module tokens when a procedural memory package is captured.

 Args:
 token_id: Memory module token ID
 amount: Number of modules to mint (default 1 per package)
 """
 client = get_client()
 _, treasury_key = get_treasury()

 (
 TokenMintTransaction()
 .set_token_id(TokenId.from_string(token_id))
 .set_amount(amount)
 .freeze_with(client)
 .sign(treasury_key)
 .execute(client)
 )

 log_event(
 event_type="MEMORY_MINTED",
 payload={"token_id": token_id, "amount": amount},
 )


def transfer_memory(token_id: str, to_account: str, amount: int = 1) -> None:
 """
 Transfer memory module tokens (marketplace transaction per Claims 16-17).

 The receiving account must have already associated the token.

 Args:
 token_id: Memory module token ID
 to_account: Destination Hedera account ID string
 amount: Number of modules to transfer
 """
 client = get_client()
 treasury_id, treasury_key = get_treasury()

 (
 TransferTransaction()
 .add_token_transfer(TokenId.from_string(token_id), treasury_id, -amount)
 .add_token_transfer(TokenId.from_string(token_id), AccountId.from_string(to_account), amount)
 .freeze_with(client)
 .sign(treasury_key)
 .execute(client)
 )

 log_event(
 event_type="MEMORY_TRANSFERRED",
 payload={
 "token_id": token_id,
 "to_account": to_account,
 "amount": amount,
 },
 )


def associate_memory_token(token_id: str, account_id: str, account_key_hex: str) -> None:
 """
 Associate the memory token with a new account before transfers can occur.

 Args:
 token_id: Memory module token ID
 account_id: Account that needs to associate
 account_key_hex: Private key of that account (DER hex)
 """
 from hiero_sdk_python import PrivateKey

 client = get_client()
 account_key = PrivateKey.from_string(account_key_hex)

 (
 TokenAssociateTransaction()
 .set_account_id(AccountId.from_string(account_id))
 .set_token_ids([TokenId.from_string(token_id)])
 .freeze_with(client)
 .sign(account_key)
 .execute(client)
 )
