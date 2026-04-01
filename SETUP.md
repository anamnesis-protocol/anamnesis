# Setup Guide

Complete guide to running Sovereign AI Context locally.

## Prerequisites

- **Python 3.10+** - [Download](https://www.python.org/downloads/)
- **Hedera Testnet Account** - [Get free account](https://portal.hedera.com) (comes with 10,000 test HBAR)
- **Git** - [Download](https://git-scm.com/downloads)

## 1. Clone the Repository

```bash
git clone https://github.com/gamilu/context-sovereignty.git
cd context-sovereignty
```

## 2. Set Up Python Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 3. Configure Hedera Credentials

### Get Your Testnet Account

1. Go to [portal.hedera.com](https://portal.hedera.com)
2. Sign up for a free testnet account
3. You'll receive:
   - Account ID (format: `0.0.XXXXXX`)
   - Private Key (ED25519 key in DER hex format)
   - 10,000 test HBAR

### Create `.env` File

```bash
# Copy the example file
cp .env.testnet.example .env

# Edit .env with your credentials
```

Your `.env` should look like:

```bash
HEDERA_NETWORK=testnet

# Your testnet account from portal.hedera.com
OPERATOR_ID=0.0.YOUR_ACCOUNT_ID
OPERATOR_KEY=302e020100300506032b657004220420YOUR_PRIVATE_KEY_HERE

# Can be the same as operator for testing
TREASURY_ID=0.0.YOUR_ACCOUNT_ID
TREASURY_KEY=302e020100300506032b657004220420YOUR_PRIVATE_KEY_HERE

# These will be filled in after initialization
HCS_TOPIC_ID=0.0.XXXXX
VALIDATOR_CONTRACT_ID=0.0.XXXXX
```

## 4. Initialize Hedera Resources

This creates the HCS topic and deploys the smart contract:

```bash
python scripts/init_testnet.py
```

This will:
- Create an HCS topic for audit logs
- Deploy the `ContextValidator.sol` smart contract
- Update your `.env` file with the created resource IDs

## 5. Create Your First Context Token

```bash
# Mint a context token NFT
python -c "
from src.context_token import mint_context_token
token_id = mint_context_token()
print(f'Context Token Created: {token_id}')
"
```

Save the token ID - you'll need it for the next steps.

## 6. Create and Encrypt Your AI Context

Create a file called `my_context.json`:

```json
{
  "identity": {
    "name": "Your Name",
    "role": "Your preferred AI assistant role",
    "personality": "Describe your AI's personality"
  },
  "directives": {
    "core": "Your core instructions for the AI",
    "preferences": "Communication style, tone, etc."
  },
  "memory": {
    "facts": ["Important fact 1", "Important fact 2"],
    "context": "Background information the AI should know"
  }
}
```

Upload to Hedera:

```bash
# Set your context token ID
export CONTEXT_TOKEN_ID=0.0.YOUR_TOKEN_ID  # Windows: set CONTEXT_TOKEN_ID=0.0.YOUR_TOKEN_ID

# Push your context to Hedera
python scripts/vault_push.py my_context.json
```

## 7. Run the API Server

```bash
uvicorn api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

## 8. Open the Web Interface

Open your browser to `http://localhost:8000`

You'll see the Sovereign AI Context interface where you can:
1. Connect your wallet (or use demo mode)
2. Sign to decrypt your context
3. Chat with AI models using your encrypted context

## API Endpoints

### Session Management

```bash
# Get challenge to sign
POST /session/challenge
{
  "token_id": "0.0.YOUR_TOKEN_ID",
  "serial": 1
}

# Open session (decrypt context)
POST /session/open
{
  "token_id": "0.0.YOUR_TOKEN_ID",
  "serial": 1,
  "wallet_signature_hex": "YOUR_WALLET_SIGNATURE"
}

# Close session
POST /session/close
{
  "session_id": "SESSION_UUID"
}
```

### Chat

```bash
# List available AI models
GET /chat/models?session_id=SESSION_UUID

# Send message (streaming response)
POST /chat/message
{
  "session_id": "SESSION_UUID",
  "message": "Your message here",
  "model_id": "claude-3-5-sonnet-20241022"
}
```

## Testing

Run the test suite:

```bash
# All tests
pytest tests/ -v

# Crypto tests only (no network required)
pytest tests/test_crypto.py -v

# Specific test file
pytest tests/test_vault.py -v
```

## Common Issues

### "OPERATOR_ID not found"
Make sure your `.env` file exists and contains your Hedera credentials.

### "InvalidTag" error when opening session
Your wallet signature doesn't match the context token owner. Make sure you're signing with the correct wallet.

### "File not found" when pulling vault
Run `vault_push.py` first to create your encrypted context on Hedera.

### Rate limit errors
Hedera testnet has rate limits. Wait a few seconds between transactions.

## Advanced Usage

### RAG-Based Memory Package Search

The system uses TF-IDF (Term Frequency-Inverse Document Frequency) to intelligently search your encrypted memory packages by relevance:

```python
from src.memory_packages import query_packages, pull_package_index
from src.vault import get_package_key, CONTEXT_TOKEN_ID

# Load your package index
package_key = get_package_key(CONTEXT_TOKEN_ID)
packages = pull_package_index(package_key, CONTEXT_TOKEN_ID)

# Query by natural language
results = query_packages(
    "hedera smart contract deployment",
    packages,
    top_n=5,           # Return top 5 matches
    threshold=0.05,    # Minimum relevance score
    use_rag=True       # Use TF-IDF scoring (default)
)

# View results
for score, pkg in results:
    print(f"{score:.3f} - {pkg.name}")
    print(f"  Category: {pkg.category}")
    print(f"  Keywords: {', '.join(pkg.keywords)}")
```

**How it works:**
- Builds TF-IDF vectors from package metadata (name, description, keywords)
- Computes cosine similarity between query and each package
- Returns packages ranked by relevance
- Keywords are weighted 2x for better matching

**Tips:**
- Use natural language queries: "blockchain development session"
- Lower threshold (0.01-0.05) for broader results
- Higher threshold (0.1-0.3) for precise matches
- Set `use_rag=False` for simple keyword matching (faster but less accurate)

### Session State Tracking

Track work continuity across sessions with persistent session state:

```bash
# Start a new session
python scripts/session_manager.py start "Implementing features" "Working on context-sovereignty"

# Check current status
python scripts/session_manager.py status

# Add a project
python scripts/session_manager.py add-project "context-sovereignty" --priority 1

# Update next actions
python scripts/session_manager.py next-actions "Complete tests" "Update docs" "Deploy"

# End session
python scripts/session_manager.py end "Completed feature implementation" --duration 120

# Get continuity summary for next session
python scripts/session_manager.py continuity
```

**Session State Includes:**
- Current task and context
- Next actions list
- Active projects with priorities
- Recent session history
- Total session count and hours

**Benefits:**
- Seamless continuity between sessions
- Track project progress over time
- Never lose context on what you were doing
- Automatic session history archiving

### Vault Section Metadata

Track vault section health with YAML frontmatter metadata:

```bash
# Check vault health
python scripts/vault_health.py

# Add metadata to sections without it
python scripts/vault_health.py --add-metadata

# Mark all sections as reviewed today
python scripts/vault_health.py --mark-reviewed

# Show only stale sections
python scripts/vault_health.py --stale
```

**Metadata Format:**
```yaml
---
tags: ["#type/identity", "#status/active"]
created: "2026-03-01"
last_updated: "2026-04-01"
last_reviewed: "2026-04-01"
status: "active"
version: "1.0"
---
```

**Benefits:**
- Detect stale content (not reviewed in 90+ days)
- Track section lifecycle (created, updated, reviewed)
- Tag-based organization
- Health monitoring and reporting

### Using Different AI Models

Add API keys to your `.env`:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Google (Gemini)
GOOGLE_API_KEY=...
```

The system will automatically detect available models.

### Multi-User Setup

For production deployment with multiple users:

1. Set up PostgreSQL database
2. Configure Supabase for authentication
3. Add environment variables:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

### Custom Smart Contract

To deploy your own validator contract:

```bash
# Edit contracts/ContextValidator.sol
# Then deploy:
python scripts/deploy_contract.py
```

## Security Best Practices

1. **Never commit `.env` files** - They contain your private keys
2. **Use testnet for development** - Mainnet costs real money
3. **Rotate keys if exposed** - If you accidentally commit keys, create new accounts
4. **Verify contract addresses** - Always check deployed contract IDs match expectations

## Next Steps

- Read the [README.md](README.md) for architecture details
- Explore the [API documentation](http://localhost:8000/docs) (when server is running)
- Check out example scripts in `scripts/` directory
- Review test files in `tests/` for usage examples

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/gamilu/context-sovereignty/issues)
- **Hedera Docs**: [docs.hedera.com](https://docs.hedera.com)
- **Hedera Discord**: [hedera.com/discord](https://hedera.com/discord)
