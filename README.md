# Sovereign AI Context

**The first cryptographically-owned AI companion platform. Production-ready.**

Your AI companion's context is encrypted, stored on Hedera Hashgraph, and cryptographically bound to your NFT — making it impossible to steal, corrupt, or access without your explicit consent. Unlike ChatGPT, Claude, or Gemini where the platform owns your context, **you own your AI relationship forever**.

**Status:** Production deployment with desktop app (Windows/macOS/Linux), full suite integration, and agentic tool execution.

## The Problem

Current AI companions are **rented, not owned**:
- Your context sits on someone else's server (OpenAI, Anthropic, Google)
- The platform can read, modify, train on, or sell your data
- You're locked into one model — switch providers, lose all context
- No cryptographic proof your data hasn't been tampered with
- If the platform shuts down or changes terms, your AI relationship is gone
- AI can't act autonomously on your behalf (security constraints)

## The Solution

Sovereign AI Context is **infrastructure for individual sovereignty in the AI age**:

### Core Innovations

**1. NFT-Gated Vault Storage**
- Context encrypted with AES-256-GCM, stored on Hedera File Service (HFS)
- Soul Token NFT proves ownership — transfer NFT = transfer complete AI relationship
- Immutable storage survives platform changes, company shutdowns
- Zero-knowledge architecture: server never persistently stores decryption keys

**2. Multi-Provider AI Routing**
- Works with **6 AI providers**: OpenAI, Anthropic, Google, Mistral, Groq, Ollama
- Same vault context injected to all providers (model-agnostic)
- BYOK (Bring Your Own Keys): use your API keys, not platform's
- Task-aware model recommendation (coding → Claude, vision → GPT-4o, etc.)

**3. Agentic Tool Execution**
- **20 tools** across local file system and encrypted backend services
- **Tauri tools (7)**: read_file, write_file, list_directory, search_files, execute_command, open_file_dialog, open_folder_dialog
- **API tools (13)**: password management, secure notes, TOTP/2FA, encrypted messaging, file storage, calendar
- Session-bound security: tools only execute within cryptographic session boundaries
- AI can autonomously manage your digital life (retrieve passwords, send encrypted mail, manage calendar)

**4. Cryptographic Knowledge Transfer**
- Complete AI context transferable via NFT ownership
- Digital inheritance: pass AI companion to heirs
- Expertise transfer: sell/gift domain knowledge
- Institutional memory: retain employee knowledge (with consent)

### What This Enables

- **True Ownership**: Your AI relationship is yours forever (not rental)
- **No Platform Lock-In**: Switch AI providers without losing context
- **Autonomous Operations**: AI manages passwords, calendar, mail, files
- **Privacy**: Zero-knowledge architecture (cryptographic, not trust-based)
- **Persistence**: Immutable ledger storage (survives any platform change)
- **Knowledge Compounding**: Transfer complete expertise across generations

---

## Features

### AI Companion Suite
- **AI Chat**: Multi-provider routing with streaming responses (OpenAI, Anthropic, Google, Mistral, Groq, Ollama)
- **Password Manager**: Encrypted password storage with CSV import/export (Proton Pass, Bitwarden, LastPass, Chrome)
- **Secure Notes**: Credit card, document, and custom note templates with field masking
- **Authenticator**: RFC 6238 TOTP generation with countdown timer
- **Encrypted Mail**: End-to-end encrypted messaging between Soul Tokens
- **File Storage**: Encrypted file vault with upload/download
- **Calendar**: Event management with color coding
- **Knowledge Base**: Import and search domain knowledge for AI context

### Agentic Capabilities (NEW)
AI can autonomously execute **20 tools** during conversations:

**File System Operations (Tauri):**
- Read/write files on local system
- List directories and search files
- Execute shell commands
- Open file/folder dialogs

**Vault Operations (API):**
- Retrieve passwords and TOTP codes
- Manage secure notes
- Send encrypted messages
- Create calendar events
- Access knowledge base

**Example:** "What's my GitHub password?" → AI retrieves it from encrypted vault  
**Example:** "Schedule a meeting for tomorrow at 2pm" → AI creates calendar event  
**Example:** "Send an encrypted message to token 0.0.12345" → AI composes and sends

### Multi-Provider AI Routing
- **6 providers supported**: OpenAI, Anthropic, Google, Mistral, Groq, Ollama
- **BYOK**: Use your own API keys (not platform's)
- **Task-aware**: Auto-recommends best model for task (coding, vision, reasoning, etc.)
- **Same context**: Vault injected identically to all providers
- **No lock-in**: Switch providers without losing context

### Security & Privacy
- **Zero-knowledge**: Server never persistently stores decryption keys
- **AES-256-GCM**: Military-grade encryption
- **Session-bound**: Tools only execute within cryptographic session boundaries
- **Immutable storage**: Vault on Hedera Hashgraph (survives platform changes)
- **NFT ownership**: Soul Token proves cryptographic ownership

---

## Architecture

### Hedera Layers

**HTS (Hedera Token Service)** — Companion token NFT, proof of ownership. Your wallet signature is the only way to decrypt your data. Non-custodial, transferable, costs fractions of a cent to mint.

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
1. Mint your companion token NFT on Hedera
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
| Backend | FastAPI (Python 3.11+) |
| AI Providers | OpenAI, Anthropic, Google, Mistral, Groq, Ollama |
| Desktop | Tauri 1.x (Rust + React + TypeScript) |
| Mobile | Expo (React Native) |
| Web | React SPA |
| Blockchain | Hedera (HTS, HFS, HCS) |
| Encryption | AES-256-GCM, PBKDF2/WebAuthn PRF |
| Database | Supabase (optional BYOK storage) |
| Styling | TailwindCSS |
| State | Zustand |
| Build | Vite, TypeScript 5 |
| CI/CD | GitHub Actions, Vercel |

---

## Patents

The core architecture is the subject of three US provisional patent applications filed in 2026:

- **P1** (64/007,132) — Sovereign AI context system, HKDF key derivation, skill packages
- **P2** (64/007,190) — Proof-of-concept material, dual gate, dual audit trail
- **P3** (64/008,810) — Browser session security: wallet-sig HKDF, AES-GCM AEAD, NFT gate, HCS audit, coordinated zeroing

*Patent Pending.*

---

## Roadmap

### Completed ✅
- [x] Core encryption and key derivation (AES-256-GCM, PBKDF2/WebAuthn PRF)
- [x] Hedera integration (HTS, HFS, HCS)
- [x] FastAPI backend with session management, vault operations
- [x] Multi-provider AI routing (OpenAI, Anthropic, Google, Mistral, Groq, Ollama)
- [x] BYOK credential management
- [x] RAG-gated context retrieval (TF-IDF)
- [x] Task-aware model recommendation
- [x] **Agentic tool execution (20 tools: Tauri + API)**
- [x] **Full suite integration (Pass, Notes, Authenticator, Drive, Mail, Calendar, Knowledge)**
- [x] Desktop app (Tauri — Windows, macOS, Linux)
- [x] Mobile app (Expo — iOS/Android)
- [x] Web interface
- [x] CI/CD pipeline (GitHub Actions)
- [x] Docker containerization
- [x] Production deployment

### In Progress 🚧
- [ ] Knowledge marketplace (skill packages, expertise transfer)
- [ ] AI-to-AI delegation
- [ ] Enhanced RAG (semantic search, better chunking)
- [ ] Enterprise features (SSO, RBAC, audit logs)

### Planned 📋
- [ ] Decentralized vault storage (IPFS + Hedera)
- [ ] Cross-chain NFT support
- [ ] Federated learning (privacy-preserving model training)
- [ ] Browser extension
- [ ] API marketplace (AI-to-AI services)

---

## License

**Copyright © 2026 Arty Fitchel's LLC. All Rights Reserved.**

This software is proprietary and confidential. See [LICENSE](LICENSE) for details.

**Patent Notice:** This software implements inventions covered by pending US patent applications.
