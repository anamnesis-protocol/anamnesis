# Contributing to Sovereign AI Context

Thank you for your interest in contributing to Sovereign AI Context! This project demonstrates how blockchain technology can solve the fundamental problem of AI training data ownership and security.

## Getting Started

### Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/context-sovereignty.git
cd context-sovereignty

# Add upstream remote
git remote add upstream https://github.com/gamilu/context-sovereignty.git
```

### Development Environment Setup

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

# Install development dependencies
pip install pytest-cov black flake8 mypy
```

### Running Tests Locally

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term --cov-report=html

# Run specific test file
pytest tests/test_vault_enhancements.py -v

# Run new feature tests only
pytest tests/test_vault_enhancements.py tests/test_bounded_contexts.py tests/test_metadata.py tests/test_rag.py tests/test_session_state.py tests/test_vault_monitor.py -v
```

## Development Workflow

### Branch Naming Conventions

Use descriptive branch names with prefixes:

- `feature/` - New features (e.g., `feature/vault-search`)
- `bugfix/` - Bug fixes (e.g., `bugfix/indentation-error`)
- `docs/` - Documentation updates (e.g., `docs/api-examples`)
- `refactor/` - Code refactoring (e.g., `refactor/crypto-module`)
- `test/` - Test additions/improvements (e.g., `test/coverage-improvement`)

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(vault): add automated metadata generation

Implements smart tag suggestions and cross-reference detection.
Includes CLI tool for batch processing.

Closes #42
```

```
fix(crypto): correct indentation in decompress function

Fixes IndentationError that prevented module import.
```

### Code Style

We use industry-standard Python tools:

- **Black** - Code formatting (line length: 100)
- **flake8** - Style guide enforcement (PEP 8)
- **mypy** - Static type checking

Run before committing:

```bash
# Format code
black src/ tests/

# Check style
flake8 src/ tests/

# Type check
mypy src/
```

## Pull Request Process

### Before Submitting

1. **Update from upstream:**
   ```bash
   git fetch upstream
   git rebase upstream/master
   ```

2. **Run tests:**
   ```bash
   pytest tests/ --cov=src --cov-report=term
   ```

3. **Check coverage:** Ensure coverage is ≥95%

4. **Format code:**
   ```bash
   black src/ tests/
   flake8 src/ tests/
   ```

### PR Template

When creating a PR, include:

**Description:**
- What does this PR do?
- Why is this change needed?
- What issue does it fix? (use `Closes #123`)

**Type of Change:**
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

**Testing:**
- [ ] All tests pass
- [ ] Coverage ≥95%
- [ ] Added tests for new functionality

**Checklist:**
- [ ] Code follows project style (Black, flake8)
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] No breaking changes (or documented)

### Review Process

1. **Automated Checks:** CI runs tests, linting, coverage
2. **Code Review:** Maintainer reviews code quality, design
3. **Feedback:** Address review comments
4. **Approval:** Maintainer approves and merges

**CI Checks That Must Pass:**
- ✅ All tests passing
- ✅ Coverage ≥95%
- ✅ Black formatting
- ✅ flake8 style check
- ✅ mypy type check

## Code Standards

### Python Style Guide

Follow [PEP 8](https://peps.python.org/pep-0008/) with these specifics:

- **Line length:** 100 characters (Black default)
- **Indentation:** 4 spaces (no tabs)
- **Quotes:** Double quotes for strings
- **Imports:** Grouped (stdlib, third-party, local)

### Test Coverage Requirements

- **Minimum:** 95% coverage for all new code
- **Target:** 97%+ coverage for production features
- **New features:** Must include comprehensive tests

### Documentation Requirements

**Docstrings:**
```python
def enhance_vault_file(
    file_path: Path,
    all_section_names: List[str],
    add_xrefs: bool = True,
    update_metadata: bool = True
) -> Tuple[str, Dict[str, any]]:
    """
    Enhance a vault file with automated metadata and cross-references.
    
    Performs full enhancement:
    1. Generate/update metadata from content
    2. Detect cross-references
    3. Add cross-reference links (optional)
    
    Args:
        file_path: Path to vault markdown file
        all_section_names: List of all vault section names
        add_xrefs: Whether to add cross-reference section
        update_metadata: Whether to update/generate metadata
        
    Returns:
        Tuple of (enhanced_content, enhancement_info)
        enhancement_info contains: tags, references, metadata_generated
    """
```

**README Updates:**
- Update README.md for new features
- Add usage examples
- Update roadmap if applicable

## Testing Guidelines

### Unit Test Structure

```python
def test_feature_name():
    """Test description of what is being tested."""
    # Arrange - Set up test data
    sections = {"test": "content"}
    
    # Act - Execute the function
    result = function_under_test(sections)
    
    # Assert - Verify the result
    assert result == expected_value
```

### Integration Test Approach

For features that interact with Hedera:

```python
@pytest.mark.integration
def test_hedera_integration():
    """Test actual Hedera network interaction."""
    # Use testnet for integration tests
    # Clean up resources after test
```

### Coverage Reporting

```bash
# Generate HTML coverage report
pytest tests/ --cov=src --cov-report=html

# View report
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

## Project-Specific Guidelines

### Hedera Integration

- Use testnet for development
- Never commit private keys
- Use environment variables for credentials
- Test with small HBAR amounts

### Encryption

- Follow HKDF-SHA256 + AES-256-GCM pattern
- Never store decryption keys
- Use purpose-separated key derivation

### Vault Structure

- Maintain YAML frontmatter format
- Use 4-space indentation
- Follow metadata schema

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/gamilu/context-sovereignty/issues)
- **Discussions:** [GitHub Discussions](https://github.com/gamilu/context-sovereignty/discussions)
- **Security:** See [SECURITY.md](SECURITY.md)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0 with explicit patent grant provisions.

---

**Thank you for contributing to Sovereign AI Context!** 🚀
