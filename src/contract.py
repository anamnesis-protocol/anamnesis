"""
contract.py — ContextValidator EVM Contract

Compiles, deploys, and interacts with ContextValidator.sol on Hedera.

The validator contract is the on-chain ownership gate:
registerContextFile(tokenAddress, serial, fileId) -> owner registers their file
validateAndGetFileId(tokenAddress, serial, sig) -> returns fileId if caller owns NFT

Hedera EVM notes:
- Hedera account ID 0.0.X maps to EVM address via: pad to 20 bytes (shard=0, realm=0, num=X)
- HTS token ID 0.0.X has the same EVM address mapping
- ContractFunctionParameters uses ABI encoding matching Solidity types exactly

Usage:
from src.contract import compile_contract, deploy_contract, register_file, validate_and_get_file_id

contract_id = deploy_contract()
register_file(contract_id, token_evm_address, serial=1, file_id="0.0.8252159")
file_id = validate_and_get_file_id(contract_id, token_evm_address, serial=1)
"""

import os
from pathlib import Path

import solcx

from hiero_sdk_python import (
    ContractCreateTransaction,
    ContractExecuteTransaction,
    ContractCallQuery,
    ContractFunctionParameters,
    Hbar,
    )
from hiero_sdk_python.contract.contract_id import ContractId
from src.config import get_client, get_treasury
from src.event_log import log_event

CONTRACT_PATH = Path(__file__).parent.parent / "contracts" / "ContextValidator.sol"
SOLC_VERSION = "0.8.20"


def token_id_to_evm_address(token_id_str: str) -> str:
    """
    Convert a Hedera token ID (0.0.X) to its EVM address.
    Hedera EVM maps 0.0.X -> 0x000...0000XXXX (20 bytes, num padded to right).

    Args:
    token_id_str: e.g. "0.0.8252163"

    Returns:
    40-char hex EVM address (without 0x prefix)
    """
    parts = token_id_str.split(".")
    num = int(parts[2])
    return num.to_bytes(20, "big").hex()


def compile_contract() -> tuple[str, str]:
    """
    Compile ContextValidator.sol and return (abi, bytecode).

    Returns:
    (abi_json_str, bytecode_hex)
    """
    import json

    solcx.set_solc_version(SOLC_VERSION)
    source = CONTRACT_PATH.read_text(encoding="utf-8")

    compiled = solcx.compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        )

    # compiled keys look like: '<stdin>:ContextValidator'
    contract_key = next(k for k in compiled if "ContextValidator" in k)
    abi = json.dumps(compiled[contract_key]["abi"])
    bytecode = compiled[contract_key]["bin"]
    return abi, bytecode


def deploy_contract() -> str:
    """
    Compile and deploy ContextValidator.sol to the configured Hedera network.

    Returns:
    contract_id as string (e.g. "0.0.8999999")
    """
    client = get_client()
    _, treasury_key = get_treasury()

    print("Compiling ContextValidator.sol...")
    _, bytecode = compile_contract()
    bytecode_bytes = bytes.fromhex(bytecode)

    print(f"Bytecode size: {len(bytecode_bytes)} bytes")
    print("Deploying to Hedera EVM...")

    tx = (
        ContractCreateTransaction()
        .set_bytecode(bytecode_bytes)
        .set_gas(2_000_000)
        .set_contract_memo("sovereign-ai-context validator v2")
        .freeze_with(client)
        .sign(treasury_key)
        )

    receipt = tx.execute(client)
    from hiero_sdk_python import ResponseCode
    status = ResponseCode(receipt.status).name
    if status != "SUCCESS":
        raise RuntimeError(f"Contract deployment failed: {status}")

    contract_id = str(receipt.contract_id)

    log_event(
        event_type="CONTRACT_DEPLOYED",
        payload={"contract_id": contract_id},
        )

    print(f"Contract deployed: {contract_id}")
    return contract_id


def register_file(
    contract_id: str,
    token_evm_address: str,
    serial: int,
    file_id: str,
    ) -> None:
    """
    Call registerContextFile() on the deployed contract.
    Only the NFT owner can call this — treasury is the initial owner post-mint.

    Args:
    contract_id: Deployed contract ID (e.g. "0.0.8999999")
    token_evm_address: EVM address of the HTS token (use token_id_to_evm_address())
    serial: NFT serial number (1)
    file_id: HFS file ID string to register (e.g. "0.0.8252159")
    """
    client = get_client()
    _, treasury_key = get_treasury()

    params = (
        ContractFunctionParameters()
        .add_address(token_evm_address)
        .add_uint64(serial)
        .add_string(file_id)
        )

    (
        ContractExecuteTransaction()
        .set_contract_id(ContractId.from_string(contract_id))
        .set_gas(200_000)
        .set_function("registerContextFile", params)
        .freeze_with(client)
        .sign(treasury_key)
        .execute(client)
        )

    log_event(
        event_type="FILE_REGISTERED",
        payload={
        "contract_id": contract_id,
        "token_evm_address": token_evm_address,
        "serial": serial,
        "file_id": file_id,
        },
        )

    print(f"File {file_id} registered for token {token_evm_address} serial {serial}")


def validate_and_get_file_id(
    contract_id: str,
    token_evm_address: str,
    serial: int,
    ) -> str:
    """
    Call validateAndGetFileId() — proves ownership and returns the HFS file ID.

    This is the patent's core validation gate. If the caller does not own the NFT,
    the contract reverts. If they do, the file_id is returned and a ContextAccess
    event is emitted on-chain.

    Args:
    contract_id: Deployed contract ID
    token_evm_address: EVM address of the HTS token
    serial: NFT serial number (1)

    Returns:
    HFS file_id string (e.g. "0.0.8252159")
    """
    client = get_client()
    _, treasury_key = get_treasury()

    # Use ContractExecuteTransaction (state-changing call — emits event)
    params = (
        ContractFunctionParameters()
        .add_address(token_evm_address)
        .add_uint64(serial)
        .add_bytes(b"") # signature placeholder (PoC — msg.sender check is sufficient)
        )

    receipt = (
        ContractExecuteTransaction()
        .set_contract_id(ContractId.from_string(contract_id))
        .set_gas(200_000)
        .set_function("validateAndGetFileId", params)
        .freeze_with(client)
        .sign(treasury_key)
        .execute(client)
        )

    log_event(
        event_type="CONTEXT_VALIDATED",
        payload={
        "contract_id": contract_id,
        "token_evm_address": token_evm_address,
        "serial": serial,
        },
        )

    # The file_id is returned from the contract — read via ContractCallQuery for the return value
    return get_registered_file_id(contract_id, token_evm_address, serial)


def get_registered_file_id(
    contract_id: str,
    token_evm_address: str,
    serial: int,
    ) -> str:
    """
    Read-only view: get the registered file ID without emitting an event.
    Uses ContractCallQuery (no gas cost, no state change).

    Args:
    contract_id: Deployed contract ID
    token_evm_address: EVM address of the HTS token
    serial: NFT serial number

    Returns:
    HFS file_id string, or empty string if not registered
    """
    client = get_client()

    params = (
        ContractFunctionParameters()
        .add_address(token_evm_address)
        .add_uint64(serial)
        )

    result = (
        ContractCallQuery()
        .set_contract_id(ContractId.from_string(contract_id))
        .set_gas(100_000)
        .set_function("getRegisteredFileId", params)
        .execute(client)
        )

    return result.get_string(0)
