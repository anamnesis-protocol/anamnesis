// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * ContextValidator.sol — Sovereign AI Context Registry (v2)
 *
 * PoC version: pure registry mapping (tokenAddress, serial) -> HFS fileId.
 * Ownership restriction enforced at application layer via KDF ().
 *
 * v2 changes (security audit Phase B):
 * - registerContextFile() now differentiates new registrations from updates:
 * ContextRegistered (new) vs ContextUpdated (overwrite) events
 * - validateAndGetFileId() signature parameter explicitly marked NOT VERIFIED ON-CHAIN
 * - Contract memo updated to v2
 *
 * Production upgrade path:
 * - Add HTS precompile call (0x167) for on-chain NFT ownership verification
 * - Replace deployer single-key with two-step ownership transfer (OZ Ownable2Step)
 * - Add ECDSA ecrecover() verification of wallet signature in validateAndGetFileId()
 * - The KDF proof and the contract proof become two independent ownership layers
 *
 * Flow (PoC):
 * 1. Treasury calls registerContextFile() after minting context token
 * 2. Any caller can call validateAndGetFileId() to get the file_id
 * 3. Without the KDF key, the file_id alone is useless — ciphertext is unreadable
 * 4. The cryptographic gate is the KDF(token_id + wallet_sig), not this contract
 */

contract ContextValidator {

 // Emitted when a context file is accessed via validateAndGetFileId
 event ContextAccess(
 address indexed caller,
 address indexed tokenAddress,
 uint64 serial,
 string fileId,
 uint256 timestamp
 );

 // Emitted when a NEW context file mapping is registered (no prior entry)
 event ContextRegistered(
 address indexed tokenAddress,
 uint64 serial,
 string fileId
 );

 // Emitted when an EXISTING mapping is overwritten with a new file ID
 // Auditors can distinguish migrations from initial registrations
 event ContextUpdated(
 address indexed tokenAddress,
 uint64 serial,
 string oldFileId,
 string newFileId
 );

 // Maps (token_address, serial) -> HFS file_id
 mapping(address => mapping(uint64 => string)) private _contextFiles;

 // Owner who registered each mapping (for future ownership-gating upgrade)
 mapping(address => mapping(uint64 => address)) private _registeredOwners;

 // Contract deployer — only deployer can register files in PoC
 // Production: replace with two-step ownership transfer (OZ Ownable2Step)
 address public immutable deployer;

 constructor() {
 deployer = msg.sender;
 }

 /**
 * Register the HFS file ID for a context token NFT.
 * PoC: only the deployer (treasury/operator) can register.
 *
 * Emits ContextRegistered for new entries, ContextUpdated for overwrites.
 * This distinction is auditable on-chain without reading state history.
 *
 * @param tokenAddress EVM address of the HTS token
 * @param serial NFT serial number (typically 1)
 * @param fileId HFS file ID string (e.g. "0.0.8252159")
 */
 function registerContextFile(
 address tokenAddress,
 uint64 serial,
 string calldata fileId
 ) external {
 require(
 msg.sender == deployer,
 "ContextValidator: only deployer can register in PoC"
 );

 string memory existing = _contextFiles[tokenAddress][serial];

 _contextFiles[tokenAddress][serial] = fileId;
 _registeredOwners[tokenAddress][serial] = msg.sender;

 if (bytes(existing).length == 0) {
 // New registration — no prior entry
 emit ContextRegistered(tokenAddress, serial, fileId);
 } else {
 // Overwrite — preserve old file ID in event for full auditability
 emit ContextUpdated(tokenAddress, serial, existing, fileId);
 }
 }

 /**
 * Return the HFS file ID for a context token and emit an access event.
 * The cryptographic gate is the off-chain KDF — this call alone is not sufficient
 * to decrypt the context (ciphertext is useless without the derived key).
 *
 * @param tokenAddress EVM address of the HTS token
 * @param serial NFT serial number
 * @param signature Reserved for future on-chain ECDSA verification.
 * NOT VERIFIED ON-CHAIN IN THIS POC VERSION.
 * Production upgrade: add ecrecover() here to verify
 * the caller signed the challenge from makeChallenge().
 *
 * @return fileId HFS file ID string
 */
 function validateAndGetFileId(
 address tokenAddress,
 uint64 serial,
 bytes calldata signature // NOT VERIFIED ON-CHAIN (PoC) — reserved for production ecrecover()
 ) external returns (string memory fileId) {
 fileId = _contextFiles[tokenAddress][serial];
 require(
 bytes(fileId).length > 0,
 "ContextValidator: no context file registered for this token"
 );

 emit ContextAccess(
 msg.sender,
 tokenAddress,
 serial,
 fileId,
 block.timestamp
 );

 return fileId;
 }

 /**
 * Read-only view of the registered file ID (no event emission).
 * Returns empty string if not registered.
 */
 function getRegisteredFileId(
 address tokenAddress,
 uint64 serial
 ) external view returns (string memory) {
 return _contextFiles[tokenAddress][serial];
 }

 /**
 * Produce the deterministic challenge bytes a wallet should sign.
 * Mirrors the off-chain make_challenge() function in crypto.py.
 *
 * Production use: pass the resulting signature to validateAndGetFileId()
 * once on-chain ecrecover() verification is added.
 */
 function makeChallenge(string calldata tokenId) external pure returns (bytes32) {
 return keccak256(
 abi.encodePacked("sovereign-ai-context-challenge-", tokenId)
 );
 }
}
