# Sovereign AI Context

**The backend and patent reference implementation powering [Arty Fitchel's](https://artyfitchels.ai).**

Your AI companion's context is encrypted, stored on Hedera Hashgraph, and cryptographically bound to your wallet — making it impossible to steal, corrupt, or access without your explicit consent. The architecture is the subject of US provisional patents P1–P3 (filed 2026).

## The Problem

When you build a personalized AI assistant:
- Your context sits on someone else's server
- The platform can read, modify, or sell your data
- You can't prove your data hasn't been tampered with
- You're locked into one model — switch models, lose memory
- If the platform shuts down, your AI's memory is gone forever

## The Solution

Sovereign AI Context uses Hedera Hashgraph to give you cryptographic proof of ownership and tamper-proof storage:

- **Theft-Proof**: Context is encrypted with a key derived from your wallet signature — only you can decrypt it
- **Corruption-Proof**: Hedera's consensus service creates an immutable audit trail of every change
- **Model-Agnostic**: Load your context into Claude, GPT-4, Gemini, or any AI model
- **Verifiable Ownership**: Your soul token NFT proves cryptographic ownership on-chain
- **Permanent**: Memory persists on Hedera's decentralized network, not a company's server
- **Intelligent Retrieval**: TF-IDF RAG surfaces relevant memory packages by semantic similarity

---

## Architecture

### Hedera Layers

**HTS (Hedera Token Service)** — Soul token NFT, proof of ownership. Your wallet signature is the only way to decrypt your data. Non-custodial, transferable, costs fractions of a cent to mint.

**HFS (Hedera File Service)** — Encrypted context storage. Immutable by default, decentralized, verifiable via content hashes.

**HCS (Hedera Consensus Service)** — Immutable audit trail. Every context update is logged with a timestamp and content hash. Nanosecond-precision timestamps from Hedera consensus.

**Smart Contracts (Hedera EVM)** — Access control. Trustless validation, programmable sharing rules, all access attempts recorded on-chain.

### Key Derivation

The encryption key is never stored. On each session:
1. Wallet signs a challenge
2. HKDF-SHA256 derives AES-256-GCM key from `token_id + wallet_signature`
3. Context is decrypted locally — plaintext never leaves the client
4. After the session, context is re-encrypted and written back to HFS
5. Update event logged to HCS with content hash

---

## How It Works

### Setup (Once)
1. Mint your soul token NFT on Hedera
2. Encrypt your AI's context with your wallet-derived key
3. Upload encrypted context to HFS, linked to your token via smart contract
4. Creation event logged to HCS

### Every Session
1. Sign a challenge with your wallet to prove token ownership
2. HKDF regenerates your decryption key from the signature
3. Smart contract returns the HFS file ID — download and decrypt
4. Load context into any AI model
5. Updated context re-encrypted and stored back to HFS, HCS logged

---

## Project Structure

```
sovereign-ai-context/
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── routes/             # billing, context, auth, companion endpoints
│   └── services/           # Hedera, Supabase, encryption services
├── src/                    # Core Hedera integrations
│   ├── crypto.py           # HKDF + AES-256-GCM
│   ├── context_token.py    # HTS NFT minting
│   ├── vault.py            # HFS storage
│   └── memory_packages.py  # Modular memory / RAG
├── frontend/               # React SPA (web demo)
├── frontend-src/           # Tauri desktop app (Arty Fitchel's)
│   └── src-tauri/          # Rust shell, tauri.conf.json, icons
├── mobile/                 # Expo React Native app
├── contracts/              # Solidity smart contracts (Hedera EVM)
├── scripts/                # Admin tools (award badges, generate promo keys)
└── tests/                  # Test suite
```

---

## Quick Start

**For full setup instructions see [SETUP.md](SETUP.md)**

### Prerequisites
- Python 3.10+
- Hedera testnet account (free at [portal.hedera.com](https://portal.hedera.com))

### Installation

```bash
git clone https://github.com/gamilu/context-sovereignty.git
cd context-sovereignty

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Add your Hedera testnet credentials
```

### Run the API

```bash
uvicorn api.main:app --reload --port 8000
# Demo: http://localhost:8000/demo  (testnet, no paywall)
```

### Run Tests

```bash
pytest tests/ -v

# Crypto tests only (no network required)
pytest tests/test_crypto.py -v
```

---

## Desktop App

The Arty Fitchel's desktop app is built with Tauri (Rust + React). Multi-platform releases are built via GitHub Actions on `desktop-v*` tags for:
- Windows (x64, MSVC)
- macOS (Apple Silicon + Intel)
- Linux (AppImage + deb)

Download releases: [Releases](https://github.com/gamilu/context-sovereignty/releases)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python) |
| Web frontend | React SPA |
| Desktop | Tauri (Rust) |
| Mobile | Expo (React Native) |
| Blockchain | Hedera (HTS, HFS, HCS, EVM) |
| Encryption | HKDF-SHA256 + AES-256-GCM |
| Auth | Supabase |
| CI/CD | GitHub Actions |

---

## Patents

The core architecture is the subject of three US provisional patent applications filed in 2026:

- **P1** (64/007,132) — Sovereign AI context system, HKDF key derivation, skill packages
- **P2** (64/007,190) — Proof-of-concept material, dual gate, dual audit trail
- **P3** (64/008,810) — Browser session security: wallet-sig HKDF, AES-GCM AEAD, NFT gate, HCS audit, coordinated zeroing

*Patent Pending.*

---

## Roadmap

- [x] Core encryption and key derivation (HKDF + AES-256-GCM)
- [x] Hedera integration (HTS, HFS, HCS, Smart Contracts)
- [x] FastAPI backend with auth, billing, companion endpoints
- [x] Web demo interface
- [x] Supabase auth integration
- [x] CI/CD pipeline (GitHub Actions)
- [x] Docker containerization
- [x] Production deployment (Railway)
- [x] Desktop app (Tauri — Windows, macOS, Linux)
- [x] Mobile app (Expo — iOS/Android)
- [ ] Memory package marketplace
- [ ] Multi-operator support

---

## License

Apache License 2.0 — see LICENSE file for details.

This license includes explicit patent grant provisions protecting both contributors and users.
