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

### 4.2 Reference Implementation: Hedera File Service (HFS)

The reference implementation uses Hedera File Service:
- Files are addressed by a stable `FileId` (e.g., `0.0.1234567`)
- Updates append to the file with a new version
- Files are stored across the Hedera network nodes
- Governed by Hedera Hashgraph consensus

### 4.3 Alternative Storage Backends

The protocol is storage-agnostic. Any backend satisfying the requirements above is valid:

| Backend | Immutability | Persistence | Notes |
|---------|-------------|-------------|-------|
| Hedera HFS | ✅ | ✅ | Reference implementation |
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
| Ethereum ERC-721 | Most widely supported NFT standard |
| Polygon ERC-721 | Lower gas cost Ethereum-compatible |
| Solana SPL Token | Fast, low cost |
| Base ERC-721 | Emerging L2, very low cost |

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

## 7. Session Protocol

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

## 8. Context Format

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

## 9. Model Agnosticism

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

## 10. Prior Art Statement

This specification is published as prior art under Apache 2.0. The author held US provisional patent applications covering aspects of this architecture. Those applications will not be pursued as non-provisional patents. This publication is an intentional dedication of the described methods to the public domain, establishing prior art against any future patent claims on the same methods by any party.

The methods described in this document — specifically the derivation of encryption keys from blockchain token identifiers and wallet signatures using HKDF, and the storage of AI context encrypted with such keys on decentralized storage — are hereby placed in the public domain irrevocably.

No permission is required to implement, use, modify, or commercialize this protocol. No royalties are owed to anyone.

---

## 11. Reference Implementation

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

## 12. Versioning

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
