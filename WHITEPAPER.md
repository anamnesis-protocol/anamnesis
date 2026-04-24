# Anamnesis Protocol: A Specification for Sovereign AI Context

**Version:** 1.0.0
**Date:** 2026-04-24
**Author:** Luther Lee Pollok III
**Repository:** https://github.com/anamnesis-protocol/anamnesis
**License:** Apache 2.0

---

## Abstract

This document specifies the Anamnesis Protocol — an open standard for persistent, encrypted, user-owned AI context. The protocol enables individuals to maintain a continuous AI relationship across sessions, models, and platforms without delegating custody of their context to any third party. The encryption key is never stored; it is derived fresh each session from a token the user owns. Encrypted context lives on decentralized storage. The protocol is chain-agnostic and model-agnostic.

This specification is published as prior art. No patents are claimed or will be claimed on the methods described herein. The protocol is irrevocably dedicated to the public domain under Apache 2.0.

---

## 1. Problem Statement

### 1.1 The Custody Problem

Every major AI platform today maintains custody of user context. A user's conversation history, preferences, and accumulated AI relationship live on the platform's servers. This arrangement has several structural problems:

1. **Readability** — The platform can read, analyze, and train on user context at any time.
2. **Mutability** — The platform can modify or delete user context without notice.
3. **Lock-in** — Switching AI providers requires abandoning accumulated context.
4. **Fragility** — Platform shutdown, acquisition, or terms-of-service changes terminate the user's AI relationship.
5. **Compellability** — Governments can compel platforms to produce user context.

### 1.2 The Key Storage Problem

Existing encrypted storage solutions typically store encryption keys server-side, delegate key management to a trusted third party, or require users to manage keys directly. Server-side key storage negates the privacy benefit. Trusted third parties introduce custody risk. Direct key management is impractical for most users.

### 1.3 The Portability Problem

AI context is model-specific in existing systems. A user's context with GPT-4 cannot be transferred to Claude or Gemini. This creates dependency on a single provider's model roadmap.

---

## 2. Protocol Overview

The Anamnesis Protocol solves these problems through three mechanisms:

1. **Token-Derived Key Derivation** — The encryption key is derived from a blockchain token the user owns plus their wallet signature. It is never stored anywhere.
2. **Decentralized Encrypted Storage** — Encrypted context lives on decentralized storage infrastructure, not on any company's server.
3. **Model-Agnostic Context Injection** — The decrypted context is injected into any AI provider's API call, making the vault provider-independent.

---

## 3. Cryptographic Specification

### 3.1 Key Derivation

The encryption key `K` for a given session is derived as follows:

```
input_material = token_id || wallet_signature
K = HKDF-SHA256(IKM=input_material, salt=None, info="anamnesis-v1", length=32)
```

Where:
- `token_id` — the unique identifier of the user's ownership token on the blockchain (UTF-8 encoded)
- `wallet_signature` — the user's Ed25519 or ECDSA signature over a server-issued challenge (bytes)
- `||` — concatenation
- `HKDF-SHA256` — HMAC-based Key Derivation Function per RFC 5869, using SHA-256
- `length=32` — produces a 256-bit key

**Properties:**
- The key is deterministic: the same token and signature always produce the same key.
- The key is never stored on any server or in any persistent medium.
- A different challenge per session produces a different signature, and therefore a different key — providing session isolation.
- Without both `token_id` and the corresponding `wallet_signature`, the key cannot be produced.

### 3.2 Encryption

Context is encrypted using AES-256-GCM:

```
nonce = random_bytes(12)
ciphertext, tag = AES-256-GCM-Encrypt(key=K, plaintext=context, nonce=nonce, aad=token_id)
stored = nonce || tag || ciphertext
```

Where:
- `nonce` — 96-bit random nonce, unique per encryption operation
- `aad` — Additional Authenticated Data; binding the ciphertext to the token prevents ciphertext transplant attacks
- `tag` — 128-bit authentication tag

**Properties:**
- Authenticated encryption: any tampering with the ciphertext is detectable.
- The `token_id` as AAD binds the ciphertext to its owner's token — a ciphertext encrypted for token A cannot be decrypted as if it belonged to token B.

### 3.3 Decryption

```
nonce = stored[:12]
tag = stored[12:28]
ciphertext = stored[28:]
context = AES-256-GCM-Decrypt(key=K, ciphertext=ciphertext, nonce=nonce, tag=tag, aad=token_id)
```

Decryption fails with an authentication error if the ciphertext has been tampered with or the wrong key is used.

### 3.4 Key Lifecycle

```
Session Start:
  1. Server issues challenge = random_bytes(32)
  2. User signs challenge with wallet private key → wallet_signature
  3. K = HKDF(token_id || wallet_signature)
  4. Download encrypted_context from storage
  5. context = Decrypt(K, encrypted_context)
  6. Inject context into AI provider call

Session End:
  1. context' = updated context after AI interaction
  2. encrypted_context' = Encrypt(K, context')
  3. Upload encrypted_context' to storage
  4. Log content_hash = SHA256(encrypted_context') to audit trail
  5. K is discarded — never written to disk or database
```

---

## 4. Storage Layer

### 4.1 Requirements

The storage layer must satisfy:

1. **Immutability** — Once written, data cannot be silently modified.
2. **Persistence** — Data survives the shutdown of any single provider.
3. **Addressability** — Data must be retrievable by a stable identifier.
4. **Availability** — Data must be retrievable within a reasonable time for interactive use.

### 4.2 Recommended Hedera Implementation: HCS-1 via Standards SDK

For Hedera deployments, **HCS-1** is the recommended storage backend over HFS. HCS-1 is an open standard published by Hashgraph Online (HOL) that stores content as chunked HCS messages, reconstructed on demand.

**Why HCS-1 over HFS:**
- HCS messages cost ~$0.0001 each — orders of magnitude cheaper than HFS file operations
- Designed for content that updates frequently (e.g., AI context updated every session)
- Built-in chunking and compression for larger context windows
- Returns a stable Topic ID used as the vault reference

**Implementation using the Standards SDK:**

```javascript
import { inscribe, retrieveInscription } from '@hashgraphonline/standards-sdk';

// Store encrypted context
const result = await inscribe(
  { type: 'buffer', content: encryptedContext, fileName: 'context.enc' },
  { accountId: operatorId, privateKey: operatorKey, network: 'mainnet' },
  { mode: 'file', waitForConfirmation: true }
);
const topicId = result.inscription.topic_id; // store this as vault reference

// Retrieve encrypted context
const inscription = await retrieveInscription(transactionId);
const encryptedContext = inscription.content;
```

Standards SDK: `npm install @hashgraphonline/standards-sdk`
Documentation: https://hol.org/docs/libraries/standards-sdk/inscribe/

### 4.3 Reference Implementation: Hedera File Service (HFS)

The current code reference implementation uses Hedera File Service (`src/vault.py`). HFS is suitable for low-frequency updates but becomes expensive for daily or per-session context writes. Migration to HCS-1 is recommended for production deployments.

### 4.4 Alternative Storage Backends

The protocol is storage-agnostic. Any backend satisfying the requirements above is valid:

| Backend | Immutability | Persistence | Notes |
|---------|-------------|-------------|-------|
| Hedera HCS-1 | ✅ | ✅ | **Recommended for Hedera** — cheap, frequent updates |
| Hedera HFS | ✅ | ✅ | Current reference implementation — better for static files |
| Arweave | ✅ | ✅ | Pay-once permanent storage; no governance council |
| IPFS + Filecoin | Partial | Conditional | Content-addressed; persistence requires pinning |
| Ethereum calldata | ✅ | ✅ | Expensive; suitable for small contexts |

---

## 5. Ownership Layer

### 5.1 Requirements

The ownership layer establishes which wallet controls which encrypted context. It must:

1. **Prove ownership** — Only the token holder can authorize decryption.
2. **Support transfer** — Ownership can be transferred by transferring the token.
3. **Be non-custodial** — No third party holds the private key.

### 5.2 Reference Implementation: Hedera Token Service (HTS)

The reference implementation uses an HTS NFT (non-fungible token):
- Each user mints a unique token
- The `token_id` is the stable identifier used in key derivation
- Transfer of the token transfers the ability to derive the decryption key
- Treasury account manages supply; user wallet holds the token

### 5.3 Alternative Ownership Backends

Any NFT or token standard on any chain is a valid ownership layer:

| Backend | Notes |
|---------|-------|
| Hedera HTS | Reference implementation |
| Ethereum ERC-721 | Most widely supported NFT standard; widest wallet support |
| Polygon ERC-721 | Lower gas cost Ethereum-compatible |
| Base ERC-721 | Very low cost L2; rapidly growing ecosystem |
| Solana SPL Token | Fast, low cost |

---

## 6. Audit Trail

### 6.1 Purpose

Every context update should be logged to an append-only, tamper-evident audit trail. This provides:

- Cryptographic proof that context has not been modified without the user's knowledge
- A recovery mechanism — any version of the context can be reconstructed from the audit log
- Transparency — the user can verify the full history of their context

### 6.2 Log Entry Format

Each audit entry contains:

```json
{
  "token_id": "<token identifier>",
  "timestamp": "<consensus timestamp>",
  "content_hash": "<SHA-256 of encrypted context>",
  "operation": "update | create | delete",
  "sequence": <monotonically increasing integer>
}
```

### 6.3 Reference Implementation: Hedera Consensus Service (HCS)

The reference implementation uses HCS:
- Each log entry is submitted as an HCS message to a dedicated topic
- Hedera consensus provides nanosecond-precision timestamps
- Messages are ordered and immutable once consensus is reached

### 6.4 Alternative Audit Backends

Any append-only, tamper-evident log is valid:
- Ethereum event logs
- Arweave transactions
- Any blockchain transaction log

---

## 7. Recommended Stack for Maximum Accessibility

The Anamnesis Protocol is chain-agnostic by design. However, implementors focused on maximum humanitarian accessibility — lowest cost, no governance risk, widest reach — should consider the following analysis.

### 7.1 Storage: Arweave

Arweave is the most aligned storage backend for a protocol intended as a public good:

- **Pay-once, permanent** — A single payment stores data forever. There are no recurring fees, no subscription, no risk of expiry.
- **No governance council** — Arweave has no equivalent of a board that could change terms. The storage incentive is baked into the protocol's endowment model.
- **Truly decentralized** — Data is replicated across independent miners with no central coordinator.

For a user in a low-income context minting once and storing their AI context permanently, Arweave's economic model is the most aligned with "this is yours, no strings attached."

### 7.2 Ownership: Ethereum L2 (Base or Polygon)

For token ownership, an Ethereum L2 offers the best combination of accessibility and trust:

- **Widest wallet support** — More people have Ethereum-compatible wallets (MetaMask, Coinbase Wallet, Rainbow) than any other ecosystem.
- **Low cost** — Base and Polygon reduce gas costs to fractions of a cent, making minting accessible globally.
- **Deep trust** — Ethereum's security model is the most battle-tested in the industry.
- **ERC-721 is universal** — Any developer can implement ownership without learning a new token standard.

### 7.3 Recommended Humanitarian Stack

| Layer | Recommendation | Rationale |
|-------|---------------|-----------|
| Token ownership | Base or Polygon ERC-721 | Widest wallets, lowest cost, deep trust |
| Encrypted storage | Arweave | Pay-once, permanent, no governance risk |
| Audit trail | Arweave transactions | Same infrastructure, no additional cost |

### 7.4 Reference Implementation Stack (Hedera)

The reference implementation uses Hedera (HTS + HFS + HCS). Hedera offers faster finality (3–5 seconds), low per-transaction fees, and an elegant unified ecosystem for token, storage, and audit in one place. It is a strong production choice. The governance council (Google, IBM, Boeing, and others) is a trust consideration some deployments may wish to avoid — which is why the protocol explicitly supports the alternatives above.

The ideal stack depends on the deployment context. For consumer products prioritizing accessibility: Ethereum L2 + Arweave. For enterprise deployments prioritizing speed and integrated tooling: Hedera.

---

## 8. Session Protocol

### 7.1 Full Session Flow

```
Client                          Server                    Blockchain
  |                               |                           |
  |--- GET /session/challenge ---->|                           |
  |<-- {challenge, session_id} ----|                           |
  |                               |                           |
  | [sign challenge with wallet]  |                           |
  |                               |                           |
  |--- POST /session/init -------->|                           |
  |    {token_id, signature}      |                           |
  |                               |--- verify token owner --->|
  |                               |<-- {owner: wallet_addr} --|
  |                               |                           |
  |                               | [verify signature matches |
  |                               |  wallet_addr]             |
  |                               |                           |
  |<-- {session_token} ------------|                           |
  |                               |                           |
  | [derive K = HKDF(token_id     |                           |
  |   || signature)]              |                           |
  |                               |                           |
  |--- GET /vault/context -------->|                           |
  |<-- {encrypted_context,        |                           |
  |     file_id} -----------------|                           |
  |                               |                           |
  | [decrypt context with K]      |                           |
  | [inject into AI call]         |                           |
  | [re-encrypt updated context]  |                           |
  |                               |                           |
  |--- PUT /vault/context -------->|                           |
  |    {encrypted_context}        |--- write to HFS --------->|
  |                               |--- log to HCS ----------->|
  |<-- {file_id, content_hash} ---|                           |
```

### 7.2 Security Properties

- **Forward secrecy** — Each session uses a different challenge, producing a different signature and therefore a different derived key. Compromise of one session key does not compromise past sessions.
- **Non-repudiation** — The audit trail cryptographically links every update to a valid wallet signature.
- **Zero server-side plaintext** — The server handles only ciphertext. Plaintext is produced and consumed exclusively on the client.
- **Replay resistance** — Challenges are single-use. A replayed signature cannot be used to open a new session.

---

## 9. Context Format

Context is a structured JSON document. Implementations may extend this schema.

```json
{
  "version": "1.0",
  "token_id": "<token identifier>",
  "created_at": "<ISO 8601 timestamp>",
  "updated_at": "<ISO 8601 timestamp>",
  "messages": [
    {
      "role": "user | assistant | system",
      "content": "<message content>",
      "timestamp": "<ISO 8601 timestamp>",
      "provider": "<ai provider used>"
    }
  ],
  "knowledge": [
    {
      "id": "<uuid>",
      "content": "<knowledge chunk>",
      "source": "<source identifier>",
      "created_at": "<ISO 8601 timestamp>"
    }
  ],
  "preferences": {
    "default_provider": "<provider name>",
    "custom_fields": {}
  }
}
```

---

## 10. Model Agnosticism

The protocol is AI-provider-agnostic. The decrypted context is injected into any provider's API call as a system prompt or context window prefix. The provider receives the context for the duration of one session and nothing more.

### 9.1 Provider Injection Pattern

```python
system_prompt = f"""You are a persistent AI assistant. 
The following is your context with this user:

{decrypted_context}

Continue from this context."""

response = ai_provider.chat(
    model=user_preferred_model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
)
```

### 9.2 Supported Provider Interfaces

Any provider with a chat completion API is compatible:
- OpenAI (GPT-4, GPT-4o, o1)
- Anthropic (Claude)
- Google (Gemini)
- Mistral
- Groq
- Ollama (local models)
- Any OpenAI-compatible endpoint

---

## 11. Prior Art Statement

This specification is published as prior art under Apache 2.0. The author held US provisional patent applications covering aspects of this architecture. Those applications will not be pursued as non-provisional patents. This publication is an intentional dedication of the described methods to the public domain, establishing prior art against any future patent claims on the same methods by any party.

The methods described in this document — specifically the derivation of encryption keys from blockchain token identifiers and wallet signatures using HKDF, and the storage of AI context encrypted with such keys on decentralized storage — are hereby placed in the public domain irrevocably.

No permission is required to implement, use, modify, or commercialize this protocol. No royalties are owed to anyone.

---

## 12. Reference Implementation

A complete reference implementation is available at:

**https://github.com/anamnesis-protocol/anamnesis**

The implementation includes:
- FastAPI backend (`api/`)
- Core cryptographic primitives (`src/crypto.py`)
- Hedera HTS/HFS/HCS integration (`src/`)
- React web interface (`frontend/`)
- Tauri desktop application (`frontend-src/`)
- Expo mobile application (`mobile/`)
- Full test suite (`tests/`)

---

## 13. Versioning

This document describes Anamnesis Protocol version 1.0.0.

Future versions will be published in this repository. Breaking changes increment the major version. The `info` parameter in HKDF includes the version string (`"anamnesis-v1"`) to ensure keys derived under different protocol versions are distinct.

---

## References

- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)
- NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC
- Hedera Hashgraph Technical Documentation — https://docs.hedera.com
- Arweave Yellow Paper — https://www.arweave.org/yellow-paper.pdf

---

*Anamnesis Protocol v1.0.0 — Published 2026-04-24 — Apache 2.0*
