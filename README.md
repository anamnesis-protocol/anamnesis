# Anamnesis Protocol

*an-am-NEE-sis* — from the Greek, meaning "unforgetting."

**Sovereign AI memory. Yours forever.**

Anamnesis is an open protocol for persistent, encrypted, user-owned AI context. Your conversation history, knowledge, and relationship with AI lives on infrastructure you control — not on a company's server.

When you talk to an AI, it forgets you the moment the session ends. You start over every time. Anamnesis is the fix: your context persists across every session, every model, every platform. Encrypted with a key derived from a token you own. Readable only by you.

This is a basic human right — the right to your own memory.

---

## What Becomes Possible

### Your AI relationship survives everything

If OpenAI shuts down tomorrow, your context is on Hedera. Plug it into the next provider. Nothing lost. Your AI knows you the same way it did yesterday — because the memory was never theirs to begin with.

### Switch AI models without losing yourself

The same encrypted vault works with any provider. Use GPT today, Claude tomorrow, a model that doesn't exist yet in five years. Your AI relationship is not tied to any company. It travels with you.

### Transfer complete AI expertise as a token

Your accumulated context — everything your AI has learned about you, your domain, your work — is transferable. Sell your expertise. Gift your knowledge to a successor. Pass your AI relationship to your heirs. This is digital inheritance. It has never existed before.

### AI that acts in your life without exposing your life

Anamnesis includes agentic tools: your AI can retrieve your passwords, create calendar events, send encrypted messages, manage your files — all within cryptographic session boundaries. It acts on your behalf without any platform seeing the data it touches.

### Prove your context hasn't been tampered with

Every context update is logged to Hedera Consensus Service with a timestamp and content hash. Your AI's memory is not just private — it's verifiable. Cryptographic proof that no one has touched it.

### Institutional memory with consent

When an employee leaves, their accumulated AI context — their domain knowledge, their reasoning patterns, their work history — can be retained and transferred with their consent. Not lost, not stolen. Transferred.

### Private AI, finally

Every AI platform today can read your context, train on it, sell it, or hand it to a government. With Anamnesis, there is no plaintext on any server. The provider receives your context for one session and nothing more. Your AI relationship is yours — not a service you rent from a company that owns everything you tell it.

---

## The Problem

Every AI platform today owns your context:

- Your history lives on OpenAI's servers, Google's servers, Anthropic's servers
- They can read it, train on it, sell it, or delete it
- Switch providers and lose everything
- Platform shuts down — your AI relationship is gone
- No cryptographic proof your data hasn't been tampered with

This is not how it should work.

---

## The Protocol

Anamnesis solves this with three components:

### 1. Token-Derived Encryption

Your encryption key is never stored anywhere. It is derived fresh each session using HKDF-SHA256 from:

```
key = HKDF(token_id + wallet_signature)
```

Your Hedera HTS token is the proof of ownership. Your wallet signature is the proof of presence. No one else can produce this key — not the server, not us, not anyone.

### 2. Decentralized Storage

Encrypted context lives on Hedera File Service (HFS) — an immutable, decentralized ledger. It survives:

- Platform shutdowns
- Terms of service changes
- Company acquisitions
- Government subpoenas (no plaintext to hand over)

Every context update is logged to Hedera Consensus Service (HCS) with a timestamp and content hash — a permanent, tamper-proof audit trail.

### 3. Model Agnosticism

The same encrypted vault works with any AI provider:

- OpenAI, Anthropic, Google, Mistral, Groq, Ollama
- Switch models without losing context
- Bring your own API keys
- Your context is injected identically to every provider

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Your Device                     │
│                                                     │
│  wallet_signature + token_id                        │
│         │                                           │
│         ▼                                           │
│  HKDF-SHA256 ──► AES-256-GCM key (never stored)    │
│         │                                           │
│         ▼                                           │
│  Decrypt context ◄──────────────────────────────┐  │
│         │                                        │  │
│         ▼                                        │  │
│  [AI Provider of your choice]                   │  │
│         │                                        │  │
│         ▼                                        │  │
│  Re-encrypt ────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                  Hedera Hashgraph                   │
│                                                     │
│  HTS — Token ownership proof                        │
│  HFS — Encrypted context storage                    │
│  HCS — Immutable audit log                          │
│  EVM — Access control smart contracts               │
└─────────────────────────────────────────────────────┘
```

### Key Derivation (Session Flow)

1. Wallet signs a server-issued challenge
2. HKDF-SHA256 derives AES-256-GCM key from `token_id + signature`
3. Encrypted context downloaded from HFS and decrypted locally
4. Plaintext never leaves your device — only injected into AI provider call
5. After session: re-encrypted, written back to HFS, update logged to HCS

---

## What's Included

This repository is the reference implementation:

```
anamnesis/
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── routes/             # auth, context, companion, suite endpoints
│   └── services/           # Hedera, encryption, RAG services
├── src/                    # Core protocol
│   ├── crypto.py           # HKDF + AES-256-GCM
│   ├── context_token.py    # HTS token minting
│   ├── vault.py            # HFS storage
│   └── memory_packages.py  # Modular context / RAG
├── frontend/               # React web interface
├── frontend-src/           # Tauri desktop app (reference implementation)
├── mobile/                 # Expo React Native app
├── contracts/              # Solidity smart contracts (Hedera EVM)
├── scripts/                # Admin and setup tools
└── tests/                  # Test suite
```

### Encrypted Suite (reference implementation)

The reference implementation includes a full encrypted personal suite, all keyed to the same token:

| Service | What it stores |
|---------|---------------|
| AI Companion | Persistent conversation context |
| Pass | Passwords, secure notes, TOTP codes |
| Drive | Encrypted file storage |
| Mail | End-to-end encrypted messaging between token holders |
| Calendar | Encrypted calendar events |
| Knowledge | Personal knowledge base, RAG-indexed for AI context |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Hedera testnet account — free at [portal.hedera.com](https://portal.hedera.com)

### Install

```bash
git clone https://github.com/anamnesis-protocol/anamnesis.git
cd anamnesis

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Add your Hedera testnet credentials to .env
```

### Run

```bash
uvicorn api.main:app --reload --port 8000
# Open http://localhost:8000/demo
```

### Test

```bash
pytest tests/ -v

# Crypto tests only (no network required)
pytest tests/test_crypto.py -v
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.11+) |
| AI Providers | OpenAI, Anthropic, Google, Mistral, Groq, Ollama |
| Desktop | Tauri (Rust + React + TypeScript) |
| Mobile | Expo (React Native) |
| Blockchain | Hedera (HTS, HFS, HCS, EVM) |
| Encryption | AES-256-GCM, HKDF-SHA256, WebAuthn PRF |
| Database | Supabase (optional BYOK storage) |
| Build | Vite, TypeScript 5 |

---

## Hosted Implementation

[Arty Fitchels](https://artyfitchels.ai) is the hosted consumer implementation of this protocol — a managed service for users who want sovereign AI context without running their own infrastructure.

The protocol is open. The hosted service is separate.

---

## Contributing

Anamnesis is a public good. Contributions are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas where help is most needed:

- Additional AI provider integrations
- Mobile apps (iOS/Android)
- Browser extension
- Alternative storage backends (IPFS, Arweave)
- Client libraries (JS, Rust, Go)
- Documentation and translations

---

## Why Anamnesis

From the Greek — *unforgetting*. Plato's concept that learning is the recovery of knowledge the soul already possessed.

Your AI context was always yours. We just gave it back.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

This means you can use, modify, and distribute this freely — commercially or otherwise — with no royalties and no restrictions beyond attribution. No one, including the original authors, can ever patent-trap you on this protocol.
