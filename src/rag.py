"""
rag.py — TF-IDF based RAG for memory package relevance scoring

Implements relevance-gated memory package loading using TF-IDF vectorization.
Adapted for encrypted Hedera-stored packages.

Architecture:
- Build TF-IDF vectors from package metadata (name, description, keywords)
- Query with natural language task description
- Return top N packages above relevance threshold
- No persistent index needed — vectors computed on-demand from package list

This is a lightweight implementation suitable for <1000 packages.
For larger scales, consider upgrading to embedding-based search (sentence-transformers).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass
class PackageMetadata:
    """Mirror of src.memory_packages.PackageMetadata for type hints."""
    name: str
    category: str
    description: str
    keywords: list[str]
    date: str
    size: int
    file_id: str
    bounded_context: str = "general"


def tokenize(text: str) -> list[str]:
    """
    Extract lowercase alphanumeric tokens from text.
    
    Filters:
    - Minimum 2 characters (allows numbers like "26")
    - Alphanumeric only (no punctuation)
    - Lowercase normalized
    
    Args:
        text: Input text to tokenize
        
    Returns:
        List of normalized tokens
    """
    return re.findall(r'\b[a-z0-9][a-z0-9]+\b', text.lower())


def build_package_text(pkg: PackageMetadata) -> str:
    """
    Concatenate all searchable text from a package.
    
    Combines: name, description, keywords, category
    Keywords are weighted 2x by including them twice.
    
    Args:
        pkg: Package metadata
        
    Returns:
        Concatenated searchable text
    """
    return " ".join([
        pkg.name,
        pkg.description,
        pkg.category,
        " ".join(pkg.keywords),
        " ".join(pkg.keywords),  # 2x weight for keywords
    ])


def compute_tf(tokens: list[str]) -> dict[str, float]:
    """
    Compute term frequency for a token list.
    
    TF = (count of term in document) / (total terms in document)
    
    Args:
        tokens: List of tokens from a document
        
    Returns:
        Dict of {term: tf_score}
    """
    if not tokens:
        return {}
    
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


def compute_idf(documents: list[list[str]]) -> dict[str, float]:
    """
    Compute inverse document frequency across all documents.
    
    IDF = log(total_docs / docs_containing_term)
    
    Args:
        documents: List of tokenized documents
        
    Returns:
        Dict of {term: idf_score}
    """
    if not documents:
        return {}
    
    total_docs = len(documents)
    term_doc_count: dict[str, int] = Counter()
    
    for doc in documents:
        unique_terms = set(doc)
        for term in unique_terms:
            term_doc_count[term] += 1
    
    return {
        term: math.log(total_docs / count)
        for term, count in term_doc_count.items()
    }


def compute_tfidf_vector(
    tokens: list[str],
    idf: dict[str, float]
) -> dict[str, float]:
    """
    Compute TF-IDF vector for a document.
    
    TF-IDF = TF * IDF for each term
    
    Args:
        tokens: Tokenized document
        idf: Pre-computed IDF scores
        
    Returns:
        Dict of {term: tfidf_score}
    """
    tf = compute_tf(tokens)
    return {
        term: tf_score * idf.get(term, 0.0)
        for term, tf_score in tf.items()
    }


def cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """
    Compute cosine similarity between two TF-IDF vectors.
    
    Similarity = dot_product / (magnitude1 * magnitude2)
    
    Args:
        vec1: First TF-IDF vector
        vec2: Second TF-IDF vector
        
    Returns:
        Similarity score [0.0, 1.0]
    """
    # Dot product
    common_terms = set(vec1.keys()) & set(vec2.keys())
    dot_product = sum(vec1[term] * vec2[term] for term in common_terms)
    
    # Magnitudes
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)


def rag_query_packages(
    query: str,
    packages: list[PackageMetadata],
    top_n: int = 5,
    threshold: float = 0.05,
    contexts: Optional[list[str]] = None,
) -> list[tuple[float, PackageMetadata]]:
    """
    Query packages using TF-IDF relevance scoring.
    
    Process:
    1. Filter by bounded contexts if specified
    2. Tokenize all packages and the query
    3. Compute IDF across all packages
    4. Build TF-IDF vectors for query and each package
    5. Rank packages by cosine similarity to query
    6. Filter by threshold and return top N
    
    Args:
        query: Natural language task description
        packages: List of package metadata to search
        top_n: Maximum results to return
        threshold: Minimum similarity score (0.0-1.0)
        contexts: Optional list of bounded context names to filter by
        
    Returns:
        List of (similarity_score, package) tuples, sorted by score descending
        
    Example:
        >>> packages = [...]
        >>> results = rag_query_packages("hedera smart contract deployment", packages)
        >>> for score, pkg in results:
        ...     print(f"{score:.3f} - {pkg.name}")
        0.847 - session_2026-03-16_hedera-contract-deploy
        0.623 - research_smart-contracts-hedera
        
        >>> # Filter by context
        >>> results = rag_query_packages("deployment", packages, contexts=["hedera"])
    """
    if not packages:
        return []
    
    # Filter by bounded contexts if specified
    if contexts:
        packages = [
            pkg for pkg in packages
            if pkg.bounded_context in contexts
        ]
        if not packages:
            return []
    
    # Tokenize query
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    
    # Tokenize all packages
    package_docs = [tokenize(build_package_text(pkg)) for pkg in packages]
    
    # Compute IDF across all documents (packages + query)
    all_docs = package_docs + [query_tokens]
    idf = compute_idf(all_docs)
    
    # Build TF-IDF vector for query
    query_vector = compute_tfidf_vector(query_tokens, idf)
    
    # Score each package
    scored = []
    for pkg, pkg_tokens in zip(packages, package_docs):
        pkg_vector = compute_tfidf_vector(pkg_tokens, idf)
        similarity = cosine_similarity(query_vector, pkg_vector)
        
        if similarity >= threshold:
            scored.append((similarity, pkg))
    
    # Sort by similarity descending
    scored.sort(key=lambda x: x[0], reverse=True)
    
    return scored[:top_n]


def explain_match(
    query: str,
    pkg: PackageMetadata,
    similarity: float
) -> dict:
    """
    Explain why a package matched the query (for debugging/transparency).
    
    Args:
        query: The query string
        pkg: The matched package
        similarity: The similarity score
        
    Returns:
        Dict with match explanation details
    """
    query_tokens = set(tokenize(query))
    pkg_tokens = set(tokenize(build_package_text(pkg)))
    
    matching_terms = query_tokens & pkg_tokens
    query_only = query_tokens - pkg_tokens
    pkg_only = pkg_tokens - query_tokens
    
    return {
        "similarity": similarity,
        "package_name": pkg.name,
        "matching_terms": sorted(matching_terms),
        "query_only_terms": sorted(query_only),
        "package_only_terms": sorted(list(pkg_only)[:10]),  # limit output
        "match_ratio": len(matching_terms) / len(query_tokens) if query_tokens else 0.0,
    }
