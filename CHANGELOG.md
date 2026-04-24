# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- PostgreSQL database integration
- Mobile app (iOS/Android)
- Memory package marketplace
- Enhanced RAG with semantic search
- Multi-language support

## [1.0.0] - 2026-04-02

### Added
- **Vault Enhancements System** - Comprehensive vault content management
  - Automated metadata generation from content analysis
  - Smart tag suggestions (type/domain/status/keywords)
  - Cross-reference detection (wiki links, markdown links, direct mentions)
  - Batch processing with dry-run mode
  - CLI tool: `scripts/enhance_vault.py`
- **Bounded Contexts** - Domain-driven design for memory package organization
  - 9 bounded contexts: ai_engineering, architecture, python, hedera, web3, frontend, backend, devops, security
  - Context suggestion based on content analysis
  - 99% test coverage
- **Metadata Management** - YAML frontmatter-based vault section tracking
  - Staleness detection (90-day threshold)
  - Health scoring algorithm
  - Status tracking (active/archived/draft)
  - Parse and manipulate frontmatter
  - 99% test coverage
- **Vault Health Monitoring** - Automated health checks and alerts
  - Critical alerts (health score < 50%)
  - Warning alerts (health score < 70%, 3+ stale sections)
  - Trend analysis (improving/degrading/stable)
  - Metrics history tracking
  - 96% test coverage
- **RAG Query System** - TF-IDF based relevance scoring for memory packages
  - Semantic matching with threshold filtering
  - Context-aware query processing
  - Top-N result ranking
  - 93% test coverage
- **Session State Tracking** - Work continuity across sessions
  - Current task and project status tracking
  - Next actions management
  - Session history with timestamps
  - JSON and Markdown persistence
  - 91% test coverage
- **Documentation** - Comprehensive project documentation
  - CONTRIBUTING.md - Development workflow and standards
  - SECURITY.md - Security policy and best practices
  - DEPLOYMENT_GUIDE.md - Testing and integration guide
  - API.md - Complete endpoint documentation
- **CI/CD Pipeline** - Automated testing and quality checks
  - GitHub Actions workflows for testing
  - Multi-version Python support (3.10, 3.11, 3.12)
  - Code quality checks (Black, flake8, mypy)
  - Coverage reporting (95% threshold)
- **Docker Support** - Containerized deployment
  - Multi-stage Dockerfile for optimized builds
  - docker-compose.yml for service orchestration
  - Non-root user security
  - Health checks

### Changed
- **Naming Consistency** - Renamed `mint_soul_token` → `mint_context_token`
  - Updated `src/context_token.py`
  - Updated `api/routes/user.py`
  - Maintains "soul" as vault section name only
- **Test Coverage** - Improved from 94% to 97% overall
  - New feature modules: 97% average coverage
  - Added 102 new tests for vault enhancements
  - Strategic exception handler coverage
- **Code Quality** - Systematic indentation fixes
  - Converted all files to 4-space indentation
  - Fixed 13 legacy test files
  - Fixed `src/event_log.py`, `src/crypto.py`, `src/vault.py`

### Fixed
- **Indentation Issues** - Resolved all IndentationError instances
  - Legacy source files (event_log.py, crypto.py, vault.py)
  - Legacy test files (13 files)
  - Test collection now works correctly
- **Test Failures** - Fixed failing test assertions
  - `test_generate_alerts_warning` - Added 3rd stale section for threshold
  - All 102 new feature tests passing

### Removed
- **Obsolete Files** - Cleaned up temporary and generated files
  - `fix_crypto.py` - One-time indentation fix script
  - `htmlcov/` - Generated coverage reports (now gitignored)
- **Legacy References** - Removed "Symbiote" and "Symbiosis" references
  - Cleaned from all new feature modules
  - Updated DEPLOYMENT_GUIDE.md
  - Maintained project-agnostic naming

### Security
- **Encryption** - HKDF-SHA256 + AES-256-GCM implementation
  - Wallet-signature based key derivation
  - No key storage (derived on-demand)
  - Purpose-separated keys for sections and index
- **Audit Trail** - Hedera Consensus Service (HCS) integration
  - Immutable event logging
  - Tamper detection with content hashes
  - Nanosecond-precision timestamps

## [0.9.0] - 2026-03-15

### Added
- Initial proof-of-concept implementation
- Hedera integration (HTS, HFS, HCS, Smart Contracts)
- Core encryption and key derivation
- FastAPI backend
- Web interface demo
- Basic test suite

### Security
- Security audit completed
- Fixed H2: HCS topic submit key restriction

## [0.1.0] - 2026-01-10

### Added
- Project initialization
- Basic repository structure
- License (Apache 2.0 with patent grant)

---

## Version History

- **1.0.0** (2026-04-02) - Production release with vault enhancements
- **0.9.0** (2026-03-15) - Proof-of-concept with Hedera integration
- **0.1.0** (2026-01-10) - Initial project setup

## Links

- [GitHub Repository](https://github.com/anamnesis-protocol/anamnesis)
- [Issue Tracker](https://github.com/anamnesis-protocol/anamnesis/issues)
- [Security Policy](SECURITY.md)
- [Contributing Guide](CONTRIBUTING.md)
