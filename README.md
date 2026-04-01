# Sovereign AI Context

**Train your AI securely. Own your data completely. Protected by Hedera Hashgraph.**

This is a proof-of-concept demonstrating how blockchain technology can solve the fundamental problem of AI training data ownership and security. Your AI's training context is encrypted, stored on Hedera Hashgraph, and cryptographically bound to your wallet—making it impossible to steal, corrupt, or access without your explicit consent.

## The Problem

When you train an AI model or build a personalized AI assistant:
- Your training data sits on someone else's server
- The platform can read, modify, or sell your data
- You can't prove your data hasn't been tampered with
- You're locked into one platform or model
- If the platform shuts down, your AI's memory is gone

## The Solution

Sovereign AI Context uses Hedera Hashgraph to give you cryptographic proof of ownership and tamper-proof storage:

- **Theft-Proof**: Your context is encrypted with a key derived from your wallet signature—only you can decrypt it
- **Corruption-Proof**: Hedera's consensus service creates an immutable audit trail of every change
- **Platform-Independent**: Load your context into any AI model (Claude, GPT-4, Gemini, etc.)
- **Verifiable Ownership**: Your context token NFT proves cryptographic ownership on-chain
- **Permanent**: Your AI's memory persists on Hedera's decentralized network, not a company's server
- **Intelligent Search**: TF-IDF RAG finds relevant memory packages by semantic similarity, not just keywords

---

## How Hedera Protects Your AI Training Data

Hedera Hashgraph provides four critical security guarantees that traditional cloud storage cannot:

### 🔐 **Hedera Token Service (HTS) - Proof of Ownership**
Your AI's context is bound to a unique NFT "context token" that only you control:
- **Cryptographic Ownership**: Your wallet signature is the only way to decrypt your data
- **Non-Custodial**: No platform, company, or third party can access your context
- **Transferable**: You can sell, gift, or bequeath your AI's trained context as an asset
- **Low Cost**: Mint tokens for fractions of a cent (vs. $50-100 on Ethereum)

### 📁 **Hedera File Service (HFS) - Tamper-Proof Storage**
Your encrypted context is stored on Hedera's decentralized network:
- **Immutable by Default**: Once written, files cannot be altered without your signature
- **Decentralized**: No single point of failure—your data persists even if nodes go offline
- **Verifiable Integrity**: Content hashes prove your data hasn't been corrupted
- **Affordable**: Store megabytes of training data for pennies

### 📜 **Hedera Consensus Service (HCS) - Audit Trail**
Every change to your AI's context is logged on an immutable ledger:
- **Tamper Detection**: Instantly detect if someone tries to modify your data
- **Provable History**: Cryptographic proof of when and how your AI was trained
- **Compliance Ready**: Auditable trail for regulatory requirements
- **Timestamped**: Hedera's consensus timestamps every update with nanosecond precision

### 🔗 **Hedera Smart Contract Service (EVM) - Access Control**
Smart contracts enforce who can access your encrypted context:
- **Trustless Validation**: Code, not companies, controls access to your data
- **Programmable Rules**: Set conditions for sharing (time-limited, usage-based, etc.)
- **Interoperable**: Works with any EVM-compatible wallet (MetaMask, HashPack, etc.)
- **Transparent**: All access attempts are recorded on-chain

---

## How It Works

### Training Phase (One-Time Setup)
1. **Mint Your Context Token**: Create an NFT on Hedera that serves as the cryptographic anchor for your AI's context
2. **Derive Encryption Key**: Your wallet signs a challenge, and HKDF-SHA256 derives a unique AES-256-GCM key from your signature
3. **Encrypt Your Context**: Your AI's training data, personality, and memory are encrypted with your derived key
4. **Store on Hedera**: Encrypted context is uploaded to Hedera File Service (HFS) and linked to your context token via smart contract
5. **Audit Log**: The creation event is recorded on Hedera Consensus Service (HCS) with a cryptographic hash

### Usage Phase (Every Session)
1. **Prove Ownership**: Sign a challenge with your wallet to prove you own the context token
2. **Derive Decryption Key**: The same HKDF process regenerates your encryption key from your signature
3. **Retrieve & Decrypt**: Smart contract returns the HFS file ID, you download and decrypt your context
4. **Load Into Any Model**: Decrypted context loads into Claude, GPT-4, Gemini, or any AI model
5. **Update & Re-Encrypt**: After the session, updated context is re-encrypted and stored back to HFS
6. **Audit Trail**: Every update is logged to HCS with a timestamp and content hash

### Security Guarantees

**No Key Storage**: Your decryption key is never stored anywhere—it's derived on-demand from your wallet signature
**No Escrow**: No third party ever has access to your plaintext data
**Tamper Detection**: Content hashes in HCS let you verify your data hasn't been corrupted
**Theft-Proof**: Without your wallet's private key, your encrypted context is mathematically unbreakable (AES-256-GCM)

---

## Project Structure

```
sovereign-ai-context/
├── api/ # FastAPI backend
├── frontend/ # Web interface
├── src/ # Core Hedera integrations
│ ├── crypto.py # Encryption (HKDF + AES-256-GCM)
│ ├── context_token.py # HTS NFT minting
│ ├── vault.py # Context storage on HFS
│ └── memory_packages.py # Modular memory system
├── contracts/ # Solidity smart contracts
└── tests/ # Test suite
```

---

## Quick Start

**📖 For detailed setup instructions, see [SETUP.md](SETUP.md)**

### Prerequisites
- Python 3.10+
- Hedera testnet account (free at [portal.hedera.com](https://portal.hedera.com))

### Installation

```bash
# Clone repository
git clone https://github.com/gamilu/context-sovereignty.git
cd context-sovereignty

# Create virtual environment
python -m venv .venv
source .venv/bin/activate # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Hedera testnet credentials
```

### Run the Demo

```bash
# Start the API server
uvicorn api.main:app --reload --port 8000

# Open browser to http://localhost:8000
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Crypto tests only (no network required)
pytest tests/test_crypto.py -v
```

---

## Use Cases

### Personal AI Companion
Build a long-term AI companion that remembers your conversations, preferences, and goals. Switch between Claude, GPT-4, or Gemini while maintaining the same personality and memory.

### AI Skill Marketplace
Create specialized AI "skill packages" (e.g., "Python Expert," "Creative Writer") and sell them as tokens. Buyers can load these skills into their own AI companions.

### Enterprise AI Agents
Deploy AI agents with encrypted, auditable context. Prove compliance with immutable HCS audit logs. Transfer agents between employees without losing institutional knowledge.

### AI Inheritance
Your AI companion can outlive you. Designate beneficiaries in your smart contract to inherit your AI's context and memories.

---

## Tech Stack

**Backend**: FastAPI (Python)
**Frontend**: Vanilla JavaScript SPA
**Blockchain**: Hedera Hashgraph (HTS, HFS, HCS, Smart Contracts)
**Encryption**: HKDF-SHA256 + AES-256-GCM
**Smart Contracts**: Solidity (Hedera EVM)
**Database**: PostgreSQL (planned)

---

## Roadmap

- [x] Core encryption and key derivation
- [x] Hedera integration (HTS, HFS, HCS)
- [x] Smart contract deployment
- [x] Web interface demo
- [ ] Docker containerization
- [ ] PostgreSQL migration
- [ ] CI/CD pipeline
- [ ] Production deployment
- [ ] Mobile app (iOS/Android)
- [ ] Memory package marketplace

---

## Contributing

This is a proof-of-concept demonstrating the technical feasibility of sovereign AI context ownership. Contributions, feedback, and collaboration are welcome.

## License

Apache License 2.0 - see LICENSE file for details

This license includes explicit patent grant provisions, protecting both contributors and users.
