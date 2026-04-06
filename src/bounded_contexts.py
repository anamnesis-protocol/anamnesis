"""
bounded_contexts.py — Bounded Context Organization for Memory Packages

Implements domain-driven design bounded contexts for organizing memory packages.
Uses 9 bounded contexts for comprehensive knowledge organization.

Bounded Contexts:
- ai_engineering: MCP, Agentic AI, RAG, LLM, Prompts, GenAI
- architecture: Software Architecture, DDD, Microservices, Design Patterns
- python: Python Core, OOP, Clean Code, Testing
- hedera: Hedera Hashgraph, HTS, HFS, HCS, Smart Contracts
- web3: Blockchain, DeFi, NFTs, Wallets
- frontend: React, UI/UX, JavaScript, CSS
- backend: APIs, Databases, Authentication, Deployment
- devops: CI/CD, Docker, Kubernetes, Monitoring
- security: Cryptography, Authentication, Authorization, Auditing

Each package can belong to one or more contexts for cross-domain knowledge.
"""

from dataclasses import dataclass, field
from typing import List, Set, Optional
from enum import Enum


class BoundedContext(str, Enum):
    """Enumeration of available bounded contexts."""

    AI_ENGINEERING = "ai_engineering"
    ARCHITECTURE = "architecture"
    PYTHON = "python"
    HEDERA = "hedera"
    WEB3 = "web3"
    FRONTEND = "frontend"
    BACKEND = "backend"
    DEVOPS = "devops"
    SECURITY = "security"
    GENERAL = "general"  # Catch-all for uncategorized

    @classmethod
    def from_string(cls, value: str) -> "BoundedContext":
        """Convert string to BoundedContext enum."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.GENERAL

    def get_keywords(self) -> Set[str]:
        """Get keywords associated with this context."""
        keywords_map = {
            BoundedContext.AI_ENGINEERING: {
                "ai",
                "llm",
                "rag",
                "mcp",
                "agentic",
                "prompt",
                "genai",
                "embedding",
                "vector",
                "semantic",
                "claude",
                "gpt",
                "gemini",
                "langchain",
                "llamaindex",
                "agent",
                "reasoning",
            },
            BoundedContext.ARCHITECTURE: {
                "architecture",
                "ddd",
                "microservices",
                "design",
                "pattern",
                "solid",
                "clean",
                "hexagonal",
                "event",
                "driven",
                "cqrs",
                "saga",
                "domain",
                "bounded",
                "context",
            },
            BoundedContext.PYTHON: {
                "python",
                "oop",
                "class",
                "function",
                "async",
                "await",
                "decorator",
                "generator",
                "pytest",
                "unittest",
                "typing",
                "dataclass",
                "pydantic",
                "fastapi",
                "django",
                "flask",
            },
            BoundedContext.HEDERA: {
                "hedera",
                "hashgraph",
                "hts",
                "hfs",
                "hcs",
                "hbar",
                "consensus",
                "token",
                "nft",
                "smart",
                "contract",
                "solidity",
                "testnet",
                "mainnet",
                "account",
                "transaction",
            },
            BoundedContext.WEB3: {
                "blockchain",
                "web3",
                "ethereum",
                "defi",
                "nft",
                "wallet",
                "metamask",
                "crypto",
                "cryptocurrency",
                "decentralized",
                "dapp",
                "smart",
                "contract",
                "token",
                "evm",
            },
            BoundedContext.FRONTEND: {
                "react",
                "vue",
                "angular",
                "javascript",
                "typescript",
                "html",
                "css",
                "tailwind",
                "ui",
                "ux",
                "component",
                "frontend",
                "browser",
                "dom",
                "responsive",
            },
            BoundedContext.BACKEND: {
                "api",
                "rest",
                "graphql",
                "database",
                "sql",
                "postgres",
                "mongodb",
                "redis",
                "authentication",
                "authorization",
                "jwt",
                "oauth",
                "backend",
                "server",
                "endpoint",
            },
            BoundedContext.DEVOPS: {
                "docker",
                "kubernetes",
                "cicd",
                "github",
                "actions",
                "deployment",
                "monitoring",
                "logging",
                "prometheus",
                "grafana",
                "terraform",
                "ansible",
                "devops",
                "infrastructure",
            },
            BoundedContext.SECURITY: {
                "security",
                "encryption",
                "cryptography",
                "aes",
                "rsa",
                "hash",
                "signature",
                "authentication",
                "authorization",
                "owasp",
                "vulnerability",
                "audit",
                "penetration",
                "testing",
            },
            BoundedContext.GENERAL: set(),
        }
        return keywords_map.get(self, set())

    def get_description(self) -> str:
        """Get human-readable description of this context."""
        descriptions = {
            BoundedContext.AI_ENGINEERING: "AI/ML, LLMs, RAG, Agentic Systems",
            BoundedContext.ARCHITECTURE: "Software Architecture, Design Patterns, DDD",
            BoundedContext.PYTHON: "Python Programming, OOP, Testing",
            BoundedContext.HEDERA: "Hedera Hashgraph, HTS, HFS, HCS, Smart Contracts",
            BoundedContext.WEB3: "Blockchain, Web3, DeFi, NFTs",
            BoundedContext.FRONTEND: "React, UI/UX, JavaScript, Frontend Development",
            BoundedContext.BACKEND: "APIs, Databases, Backend Services",
            BoundedContext.DEVOPS: "CI/CD, Docker, Kubernetes, Infrastructure",
            BoundedContext.SECURITY: "Cryptography, Security, Authentication",
            BoundedContext.GENERAL: "General/Uncategorized",
        }
        return descriptions.get(self, "Unknown")


@dataclass
class ContextMapping:
    """Mapping of package to bounded contexts."""

    package_name: str
    contexts: List[BoundedContext] = field(default_factory=list)
    confidence: float = 1.0  # 0.0-1.0, how confident the mapping is

    def add_context(self, context: BoundedContext, confidence: float = 1.0) -> None:
        """Add a context to this mapping."""
        if context not in self.contexts:
            self.contexts.append(context)
            self.confidence = min(self.confidence, confidence)

    def has_context(self, context: BoundedContext) -> bool:
        """Check if package belongs to a context."""
        return context in self.contexts

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "package_name": self.package_name,
            "contexts": [c.value for c in self.contexts],
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextMapping":
        """Create from dict."""
        return cls(
            package_name=data["package_name"],
            contexts=[BoundedContext.from_string(c) for c in data.get("contexts", [])],
            confidence=data.get("confidence", 1.0),
        )


def infer_contexts_from_keywords(
    package_name: str, keywords: List[str], description: str = ""
) -> List[BoundedContext]:
    """
    Infer bounded contexts from package keywords and description.

    Args:
        package_name: Package name
        keywords: List of keywords
        description: Package description

    Returns:
        List of inferred bounded contexts
    """
    # Combine all text for analysis
    text = " ".join([package_name, description] + keywords).lower()
    tokens = set(text.split())

    # Score each context
    context_scores = {}
    for context in BoundedContext:
        if context == BoundedContext.GENERAL:
            continue

        context_keywords = context.get_keywords()
        if not context_keywords:
            continue

        # Count keyword matches
        matches = tokens & context_keywords
        if matches:
            context_scores[context] = len(matches)

    # Return contexts with matches, sorted by score
    if not context_scores:
        return [BoundedContext.GENERAL]

    sorted_contexts = sorted(context_scores.items(), key=lambda x: x[1], reverse=True)

    # Return top contexts (at least 1, max 3)
    return [ctx for ctx, score in sorted_contexts[:3]]


def filter_packages_by_context(
    packages: List,  # List of PackageMetadata
    contexts: List[BoundedContext],
    context_mappings: dict[str, ContextMapping],
) -> List:
    """
    Filter packages by bounded contexts.

    Args:
        packages: List of PackageMetadata objects
        contexts: List of contexts to filter by
        context_mappings: Dict of {package_name: ContextMapping}

    Returns:
        Filtered list of packages
    """
    if not contexts:
        return packages

    filtered = []
    for pkg in packages:
        mapping = context_mappings.get(pkg.name)
        if not mapping:
            # No mapping - infer from keywords
            inferred = infer_contexts_from_keywords(pkg.name, pkg.keywords, pkg.description)
            # Check if any inferred context matches filter
            if any(ctx in contexts for ctx in inferred):
                filtered.append(pkg)
        else:
            # Use existing mapping
            if any(mapping.has_context(ctx) for ctx in contexts):
                filtered.append(pkg)

    return filtered


def get_context_summary(context_mappings: dict[str, ContextMapping]) -> dict:
    """
    Get summary statistics for bounded contexts.

    Args:
        context_mappings: Dict of {package_name: ContextMapping}

    Returns:
        Dict with context statistics
    """
    context_counts = {ctx: 0 for ctx in BoundedContext}
    total_packages = len(context_mappings)

    for mapping in context_mappings.values():
        for context in mapping.contexts:
            context_counts[context] += 1

    # Sort by count
    sorted_contexts = sorted(context_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "total_packages": total_packages,
        "context_distribution": {
            ctx.value: {
                "count": count,
                "percentage": round(count / total_packages * 100, 1) if total_packages > 0 else 0,
                "description": ctx.get_description(),
            }
            for ctx, count in sorted_contexts
            if count > 0
        },
    }


def suggest_context_for_package(
    package_name: str, keywords: List[str], description: str = ""
) -> ContextMapping:
    """
    Suggest bounded contexts for a package.

    Args:
        package_name: Package name
        keywords: Package keywords
        description: Package description

    Returns:
        ContextMapping with suggested contexts
    """
    contexts = infer_contexts_from_keywords(package_name, keywords, description)

    # Calculate confidence based on keyword overlap
    confidence = 0.8 if len(contexts) <= 2 else 0.6

    mapping = ContextMapping(
        package_name=package_name,
        contexts=contexts,
        confidence=confidence,
    )

    return mapping
