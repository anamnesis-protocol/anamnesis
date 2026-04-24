# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

**Support Timeline:**
- **1.0.x:** Security updates for 12 months from release
- **Future versions:** Will be announced with each major release

## Reporting a Vulnerability

**We take security seriously.** If you discover a security vulnerability, please report it responsibly.

### Contact Method

**Email:** security@[project-domain].com *(Update with actual security contact)*

**GitHub Security Advisory:** [Create a private security advisory](https://github.com/anamnesis-protocol/anamnesis/security/advisories/new)

### What to Include

Please provide:

1. **Description** of the vulnerability
2. **Steps to reproduce** the issue
3. **Potential impact** assessment
4. **Suggested fix** (if you have one)
5. **Your contact information** for follow-up

### Response Timeline

- **Initial Response:** Within 48 hours
- **Status Update:** Within 7 days
- **Fix Timeline:** Depends on severity
  - Critical: 7-14 days
  - High: 14-30 days
  - Medium: 30-60 days
  - Low: 60-90 days

### Disclosure Timeline

We follow **coordinated disclosure**:

1. **Day 0:** Vulnerability reported
2. **Day 1-7:** Verification and assessment
3. **Day 7-30:** Develop and test fix
4. **Day 30:** Public disclosure (if fix is ready)
5. **Day 90:** Public disclosure (maximum, even if unpatched)

We will credit reporters in the security advisory unless you prefer to remain anonymous.

## Security Best Practices

### Key Management

**Never commit private keys to the repository:**

```bash
# ❌ NEVER DO THIS
OPERATOR_KEY=302e020100300506032b657004220420abc123...

# ✅ DO THIS
OPERATOR_KEY=${OPERATOR_KEY}  # Load from environment
```

**Use `.env` files (gitignored):**

```bash
# .env (never commit this file)
OPERATOR_ID=0.0.123456
OPERATOR_KEY=302e020100300506032b657004220420...
TREASURY_ID=0.0.123456
TREASURY_KEY=302e020100300506032b657004220420...
```

**Rotate keys regularly:**
- Development keys: Monthly
- Production keys: Quarterly
- Immediately after suspected compromise

### Environment Variable Security

**Secure storage:**
- Use secret management tools (AWS Secrets Manager, HashiCorp Vault)
- Never log environment variables
- Restrict access to `.env` files (chmod 600)

**Validation:**
```python
import os

# Validate required environment variables
required_vars = ["OPERATOR_ID", "OPERATOR_KEY", "TREASURY_ID", "TREASURY_KEY"]
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required environment variables: {missing}")
```

### Hedera Account Protection

**Testnet vs Mainnet:**
- Use testnet for development
- Never use mainnet credentials in test code
- Separate accounts for dev/staging/production

**Account Security:**
- Enable 2FA on Hedera portal account
- Use hardware wallets for production keys
- Monitor account activity regularly
- Set up spending limits where possible

**Key Derivation:**
```python
# ✅ Secure: Keys derived on-demand, never stored
key = derive_key(token_id, wallet_signature)
ciphertext = encrypt_context(key, plaintext)
del key  # Explicitly delete after use

# ❌ Insecure: Storing derived keys
self.encryption_key = derive_key(...)  # Don't do this
```

## Known Security Considerations

### Encryption Architecture

**HKDF-SHA256 + AES-256-GCM:**

- **Key Derivation:** HKDF-SHA256 (RFC 5869)
  - Input: `token_id + wallet_signature`
  - Salt: `SHA256(token_id)`
  - Info: `b"anamnesis-v1"`
  - Output: 32-byte AES-256 key

- **Encryption:** AES-256-GCM
  - Authenticated encryption
  - 12-byte random nonce (prepended to ciphertext)
  - 16-byte authentication tag
  - Associated data (AAD) for context binding

**Security Properties:**
- ✅ Keys never stored (derived on-demand)
- ✅ Forward secrecy (new nonce per encryption)
- ✅ Tamper detection (GCM authentication)
- ✅ Deterministic key derivation (same inputs = same key)

### Wallet Signature Security

**Challenge-Response Flow:**

```python
# 1. Generate challenge
challenge = b"anamnesis-challenge-" + token_id.encode()

# 2. User signs with wallet (off-chain)
wallet_signature = wallet.sign(challenge)

# 3. Derive encryption key
key = derive_key(token_id, wallet_signature)
```

**Security Considerations:**
- Challenge includes token_id (prevents replay attacks)
- Signature proves wallet ownership
- Same signature decrypts context (no separate credentials)
- Wallet private key never leaves user's device

### HCS Audit Trail Immutability

**Hedera Consensus Service (HCS):**

- **Immutable Logging:** All context operations logged to HCS topic
- **Tamper Detection:** Content hashes verify data integrity
- **Timestamping:** Nanosecond-precision consensus timestamps
- **Audit Compliance:** Cryptographic proof of all changes

**What's Logged:**
```json
{
  "event_type": "CONTEXT_STORED",
  "timestamp": "2026-04-02T00:00:00.000000000Z",
  "payload": {
    "token_id": "0.0.67890",
    "file_id": "0.0.12345",
    "content_hash": "sha256:abc123..."
  }
}
```

**Security Properties:**
- ✅ Cannot modify past events
- ✅ Cannot delete audit trail
- ✅ Cryptographic proof of event order
- ✅ Distributed consensus (no single point of failure)

## Threat Model

### In Scope

- Encryption key derivation vulnerabilities
- Wallet signature replay attacks
- HCS audit log tampering
- Smart contract access control bypasses
- API authentication weaknesses

### Out of Scope

- Hedera network consensus vulnerabilities (report to Hedera)
- Wallet software vulnerabilities (report to wallet provider)
- Physical access to user's device
- Social engineering attacks
- DDoS attacks on public endpoints

## Bug Bounty Program

**Status:** Not currently active

We plan to launch a bug bounty program after v1.0.0 stable release. Details will be announced on:
- GitHub repository
- Project website
- Security mailing list

**Scope (Planned):**
- Critical: $500-$2,000
- High: $250-$500
- Medium: $100-$250
- Low: Recognition in SECURITY.md

## Security Audit History

**v1.0.0:** No formal security audit yet

We plan to conduct a professional security audit before production deployment. Audit reports will be published here.

## Compliance

**Data Protection:**
- User data encrypted at rest (AES-256-GCM)
- User controls decryption keys (wallet signature)
- No plaintext data stored on servers
- Audit trail for compliance (HCS)

**Regulatory Considerations:**
- GDPR: User owns and controls their data
- CCPA: User can delete their context token
- SOC 2: Immutable audit trail (HCS)

## Security Contacts

- **General Security:** security@[project-domain].com
- **GitHub Security:** [Security Advisories](https://github.com/anamnesis-protocol/anamnesis/security/advisories)
- **Urgent Issues:** Tag with `security` label in GitHub Issues (for non-sensitive reports)

---

**Last Updated:** 2026-04-02  
**Version:** 1.0.0
