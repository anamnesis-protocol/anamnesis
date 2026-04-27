# Anamnesis Protocol — Developer Onboarding Guide

*15 minutes from zero to first working implementation.*

---

## What You're Building

A persistence layer for AI context that:
- Encrypts conversation history with a key the user owns
- Stores it on Hedera (or any compatible chain)
- Injects it into any AI provider call
- Means your server never touches plaintext

---

## Prerequisites

- Python 3.10+
- A free Hedera testnet account — [portal.hedera.com](https://portal.hedera.com)
- An API key for any AI provider (OpenAI, Anthropic, etc.)

---

## Step 1 — Clone and Install

```bash
git clone https://github.com/anamnesis-protocol/anamnesis.git
cd anamnesis
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 2 — Configure

Copy `.env.example` to `.env` and fill in:

```
HEDERA_OPERATOR_ID=0.0.XXXXXX       # your testnet account ID
HEDERA_OPERATOR_KEY=302e...          # your testnet private key
HEDERA_NETWORK=testnet
OPENAI_API_KEY=sk-...                # or any provider you prefer
```

---

## Step 3 — Run the Demo

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/demo`

This gives you a working AI companion with persistent encrypted context. Under the hood:
1. An HTS token is minted — this is the ownership token
2. A wallet signature is used to derive the AES-256-GCM key via HKDF-SHA256
3. Your conversation is encrypted and stored on Hedera HFS
4. Next session: signature → key → decrypt → inject into AI call

---

## Step 4 — Understand the Key Derivation

The core cryptographic operation:

```
key = HKDF-SHA256(token_id + wallet_signature, info="anamnesis-v1", length=32)
```

- `token_id` — the HTS token identifier (e.g. `"0.0.12345"`)
- `wallet_signature` — your Ed25519 signature over a server-issued challenge
- The key is **never stored** — derived fresh each session
- Without your wallet private key, the key cannot be derived

See `src/crypto.py` for the full implementation.

---

## Step 5 — Run the Tests

```bash
pytest tests/ -v

# Crypto only (no network required):
pytest tests/test_crypto.py -v
```

---

## What to Build Next

### Option A: Add Anamnesis to an existing AI app

The minimal integration is in `api/routes/context.py` — three endpoints:
- `POST /session/init` — verify token ownership, return session token
- `GET /vault/context` — return encrypted context
- `PUT /vault/context` — store updated encrypted context

Your app derives the key client-side, decrypts, injects into your AI call, re-encrypts, stores back.

### Option B: Build on a different chain

The protocol is chain-agnostic. You need:
1. A token ownership layer (any NFT standard — ERC-721 works)
2. A storage layer (Arweave recommended for permanence)
3. The same HKDF-SHA256 key derivation

The cryptographic spec is in `WHITEPAPER.md` — sections 3 and 4.

### Option C: Implement the HCS standard

A formal Hiero standard (HCS-XX) is in review at [hiero-ledger/hiero-consensus-specifications](https://github.com/hiero-ledger/hiero-consensus-specifications/pull/35). Implementing the message formats and audit trail pattern makes your implementation interoperable with any other conforming implementation.

---

## Reference

- Full protocol spec: `WHITEPAPER.md`
- Crypto implementation: `src/crypto.py`
- Session protocol: `api/routes/auth.py`
- Vault storage: `src/vault.py`
- HCS standard PR: github.com/hiero-ledger/hiero-consensus-specifications/pull/35

---

## Questions?

Open an issue at [github.com/anamnesis-protocol/anamnesis](https://github.com/anamnesis-protocol/anamnesis).
